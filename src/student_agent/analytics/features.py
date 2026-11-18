"""Turn raw records into a StudentSnapshot: plain numbers the risk model and the LLM can use.

Everything here is deterministic. The LLM never computes grades or attendance.
"""
from __future__ import annotations

from datetime import date, timedelta
from statistics import mean

from pydantic import BaseModel, Field

from ..config import GradingPolicy
from ..domain.models import Assessment, StudentProfile, StudentRecords


# ---- snapshot models ------------------------------------------------------------
class CourseSnapshot(BaseModel):
    course_id: int
    name: str
    credit_hours: float | None = None
    finished: bool = False

    coursework_pct: float | None = None
    midterm_pct: float | None = None
    final_pct: float | None = None
    standing_pct: float | None = None          # blend of the components known so far

    earned_points: float = 0.0                 # points (out of 100) already secured
    remaining_weight: float = 0.0              # share of the course mark still to be earned
    remaining_components: list[str] = Field(default_factory=list)
    needed_on_remaining_pct: float | None = None   # average % needed on what is left to pass
    can_still_pass: bool | None = None
    passed: bool | None = None                 # only when every component is known

    attendance_rate: float | None = None       # 0..1, from recorded lectures
    lectures_recorded: int = 0
    lectures_attended: int = 0

    due_count: int = 0
    graded_count: int = 0
    missing_count: int = 0
    late_count: int = 0
    missing_titles: list[str] = Field(default_factory=list)
    trend_points: float | None = None          # later scores minus earlier scores (percentage points)


class TaskView(BaseModel):
    description: str
    severity: str
    deadline: date
    days_left: int  # negative = overdue


class StudentSnapshot(BaseModel):
    profile: StudentProfile
    as_of: date
    current: list[CourseSnapshot] = Field(default_factory=list)
    finished: list[CourseSnapshot] = Field(default_factory=list)
    past_failures: int = 0
    gpa: float | None = None
    total_tasks: int = 0
    overdue_tasks: list[TaskView] = Field(default_factory=list)
    upcoming_tasks: list[TaskView] = Field(default_factory=list)   # next 14 days
    data_gaps: list[str] = Field(default_factory=list)

    def find_course(self, query: str) -> list[CourseSnapshot]:
        q = query.strip().lower()
        exact = [c for c in self.current + self.finished if c.name.lower() == q]
        if exact:
            return exact
        return [c for c in self.current + self.finished if q and q in c.name.lower()]


# ---- helpers --------------------------------------------------------------------
def needed_on_remaining(course: CourseSnapshot, target_pct: float) -> float | None:
    """Average % needed on the remaining components to reach ``target_pct`` overall.

    0.0 means the target is already secured; > 100 means it is out of reach.
    None means nothing is left to earn.
    """
    if course.remaining_weight <= 0:
        return None
    return max(0.0, (target_pct - course.earned_points) / course.remaining_weight)


def _pct(a: Assessment) -> float | None:
    if a.score is None or not a.max_score:
        return None
    return 100.0 * a.score / a.max_score


def _course_snapshot(records: StudentRecords, enrollment, policy: GradingPolicy, as_of: date) -> CourseSnapshot:
    course = records.courses[enrollment.course_id]
    grade = records.grades.get(enrollment.user_course_id)
    snap = CourseSnapshot(
        course_id=course.course_id,
        name=course.name,
        credit_hours=course.credit_hours,
        finished=enrollment.completed,
    )

    # --- assessments (only those already due) ---
    due = [a for a in records.assessments
           if a.user_course_id == enrollment.user_course_id and a.due_date <= as_of]
    items: list[tuple[Assessment, float]] = []
    for a in sorted(due, key=lambda x: x.due_date):
        pct = _pct(a)
        if pct is not None:
            items.append((a, pct))
        elif a.submitted_at is None:           # due, nothing handed in: counts as zero
            items.append((a, 0.0))
            snap.missing_count += 1
            snap.missing_titles.append(a.name)
        # submitted but not graded yet: ignored until graded
    snap.due_count = len(due)
    snap.graded_count = sum(1 for a in due if a.score is not None)
    snap.late_count = sum(1 for a in due if a.submitted_at and a.submitted_at.date() > a.due_date)

    if items:
        weights = [a.weight if a.weight > 0 else 1.0 for a, _ in items]
        snap.coursework_pct = sum(p * w for (_, p), w in zip(items, weights)) / sum(weights)
    if len(items) >= 4:                         # trend needs enough points
        half = len(items) // 2
        first = mean(p for _, p in items[:half])
        second = mean(p for _, p in items[-half:])
        snap.trend_points = second - first

    snap.midterm_pct = grade.midterm if grade else None
    snap.final_pct = grade.final if grade else None

    # --- course standing and what is still needed to pass ---
    components = {
        "coursework": (snap.coursework_pct, policy.coursework_weight),
        "midterm": (snap.midterm_pct, policy.midterm_weight),
        "final": (snap.final_pct, policy.final_weight),
    }
    known = {k: v for k, v in components.items() if v[0] is not None}
    total_weight = sum(w for _, w in components.values())
    if known:
        used = sum(w for _, w in known.values())
        snap.standing_pct = sum(p * w for p, w in known.values()) / used
        snap.earned_points = sum(p * w for p, w in known.values())
        snap.remaining_weight = max(0.0, total_weight - used)
    else:
        snap.remaining_weight = total_weight
    snap.remaining_components = [k for k in components if k not in known]

    if snap.remaining_weight > 1e-9:
        snap.needed_on_remaining_pct = needed_on_remaining(snap, policy.pass_mark)
        snap.can_still_pass = (snap.needed_on_remaining_pct or 0.0) <= 100.0
    else:
        snap.passed = snap.standing_pct is not None and snap.standing_pct >= policy.pass_mark
        snap.can_still_pass = snap.passed

    # --- attendance (recorded lectures that already took place) ---
    held = {l.lecture_id for l in records.lectures
            if l.course_id == course.course_id and l.lecture_date <= as_of}
    rows = [r for r in records.attendance
            if r.user_course_id == enrollment.user_course_id and r.lecture_id in held]
    snap.lectures_recorded = len(rows)
    snap.lectures_attended = sum(1 for r in rows if r.attended)
    if rows:
        snap.attendance_rate = snap.lectures_attended / len(rows)
    return snap


def _gpa(records: StudentRecords, policy: GradingPolicy) -> float | None:
    pts = cr = 0.0
    for e in records.gpa_entries:
        p = policy.gpa_scale.get(e.grade.strip().upper())
        if p is None or e.credit_hours <= 0:
            continue
        pts += p * e.credit_hours
        cr += e.credit_hours
    return pts / cr if cr else None


def build_snapshot(records: StudentRecords, policy: GradingPolicy, as_of: date) -> StudentSnapshot:
    current: list[CourseSnapshot] = []
    finished: list[CourseSnapshot] = []
    for enr in records.enrollments:
        snap = _course_snapshot(records, enr, policy, as_of)
        (finished if enr.completed else current).append(snap)

    tasks_open = [t for t in records.tasks if not t.completed]
    overdue, upcoming = [], []
    for t in tasks_open:
        days = (t.deadline.date() - as_of).days
        view = TaskView(description=t.description, severity=t.severity,
                        deadline=t.deadline.date(), days_left=days)
        if days < 0:
            overdue.append(view)
        elif days <= 14:
            upcoming.append(view)
    overdue.sort(key=lambda v: v.days_left)
    upcoming.sort(key=lambda v: v.days_left)

    gaps: list[str] = []
    for c in current:
        if c.standing_pct is None:
            gaps.append(f"No grades recorded yet for {c.name}")
        if c.attendance_rate is None:
            gaps.append(f"No attendance records for {c.name}")
    gpa = _gpa(records, policy)
    if gpa is None:
        gaps.append("No GPA entries")
    if not records.tasks:
        gaps.append("No tasks recorded")

    return StudentSnapshot(
        profile=records.profile,
        as_of=as_of,
        current=current,
        finished=finished,
        past_failures=sum(1 for c in finished if c.passed is False),
        gpa=gpa,
        total_tasks=len(records.tasks),
        overdue_tasks=overdue,
        upcoming_tasks=upcoming,
        data_gaps=gaps,
    )
