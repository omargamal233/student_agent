"""Orchestration without any LLM: repository -> features -> risk -> resources."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from ..analytics.features import CourseSnapshot, StudentSnapshot, build_snapshot
from ..analytics.risk import RiskAssessment, RiskModel
from ..config import GradingPolicy
from ..data.repository import StudentRepository
from ..domain.models import StudentProfile, StudentRecords


class ResourceSuggestion(BaseModel):
    course: str
    kind: str            # "link" | "material"
    title: str
    url: str | None = None   # links only; materials are referenced by title


class StudentAnalysis(BaseModel):
    snapshot: StudentSnapshot
    risk: RiskAssessment
    resources: list[ResourceSuggestion] = Field(default_factory=list)


def course_status(c: CourseSnapshot, policy: GradingPolicy) -> str:
    """One-word status per course, used in reports and prompts."""
    if c.finished:
        return "passed" if c.passed else "failed"
    if c.can_still_pass is False:
        return "cannot_reach_pass_mark"
    if c.standing_pct is None and c.attendance_rate is None:
        return "no_data"
    low_att = c.attendance_rate is not None and c.attendance_rate < policy.min_attendance
    if low_att or (c.standing_pct is not None and c.standing_pct < policy.pass_mark + 10):
        return "at_risk"
    weak_att = c.attendance_rate is not None and c.attendance_rate < 0.85
    if (c.standing_pct is not None and c.standing_pct < 65) or weak_att or c.missing_count >= 2:
        return "needs_attention"
    return "on_track"


class AssessmentService:
    def __init__(self, repo: StudentRepository, policy: GradingPolicy, risk_model: RiskModel,
                 as_of: date | None = None):
        self._repo = repo
        self._policy = policy
        self._risk_model = risk_model
        self._as_of = as_of

    @property
    def policy(self) -> GradingPolicy:
        return self._policy

    @property
    def as_of(self) -> date:
        return self._as_of or self._repo.as_of() or date.today()

    def list_students(self) -> list[StudentProfile]:
        return self._repo.list_students()

    def analyze(self, student_id: int) -> StudentAnalysis:
        records = self._repo.get_student_records(student_id)
        snapshot = build_snapshot(records, self._policy, self.as_of)
        risk = self._risk_model.assess(snapshot)
        return StudentAnalysis(snapshot=snapshot, risk=risk,
                               resources=self._pick_resources(snapshot, records))

    # -- study resources for the courses that need the most help ---------------------
    def _pick_resources(self, snap: StudentSnapshot, records: StudentRecords, max_courses: int = 3):
        ranked = [c for c in snap.current if course_status(c, self._policy) not in ("on_track", "no_data")]
        if not ranked:  # nothing is wrong: offer material for the weakest course only
            ranked = sorted([c for c in snap.current if c.standing_pct is not None],
                            key=lambda c: c.standing_pct)[:1]
        ranked = sorted(ranked, key=lambda c: (c.standing_pct if c.standing_pct is not None else 101))[:max_courses]

        out: list[ResourceSuggestion] = []
        for c in ranked:
            links = [l for l in records.links if l.course_id == c.course_id][:2]
            mats = [m for m in records.materials if m.course_id == c.course_id
                    and m.category in ("sheet", "lecture", "exam")][:1]
            out += [ResourceSuggestion(course=c.name, kind="link", title=l.title, url=l.url) for l in links]
            out += [ResourceSuggestion(course=c.name, kind="material", title=m.title) for m in mats]
        return out
