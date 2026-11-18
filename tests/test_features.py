from datetime import date, datetime

import pytest

from student_agent.analytics.features import build_snapshot, needed_on_remaining
from student_agent.config import GradingPolicy
from student_agent.domain import models as m

AS_OF = date(2026, 11, 18)


def _records(assessments, midterm=60.0, final=None, attendance=()):
    return m.StudentRecords(
        profile=m.StudentProfile(student_id=1, name="T", department="D"),
        enrollments=[m.Enrollment(user_course_id=1, student_id=1, course_id=1)],
        courses={1: m.Course(course_id=1, name="Course", type="specialized", credit_hours=3)},
        grades={1: m.CourseGrade(user_course_id=1, midterm=midterm, final=final)},
        assessments=assessments,
        lectures=[m.Lecture(lecture_id=i, course_id=1, name=f"L{i}", lecture_date=date(2026, 10, i + 1))
                  for i in range(4)],
        attendance=[m.LectureAttendance(user_course_id=1, lecture_id=i, attended=a)
                    for i, a in enumerate(attendance)],
    )


def _a(i, score, due=date(2026, 10, 10), submitted=datetime(2026, 10, 9, 10)):
    return m.Assessment(assessment_id=i, user_course_id=1, type="quiz", name=f"Q{i}", score=score,
                        max_score=100, weight=1, due_date=due, submitted_at=submitted)


def test_standing_and_needed_final():
    policy = GradingPolicy()
    snap = build_snapshot(_records([_a(1, 80), _a(2, 80)]), policy, AS_OF)
    c = snap.current[0]
    # coursework 80 * 0.4 + midterm 60 * 0.2 = 44 points earned out of 60 possible so far
    assert c.earned_points == pytest.approx(44.0)
    assert c.standing_pct == pytest.approx(44 / 0.6)
    assert c.needed_on_remaining_pct == pytest.approx(15.0)      # (50 - 44) / 0.4
    assert needed_on_remaining(c, 70) == pytest.approx(65.0)     # (70 - 44) / 0.4
    assert c.remaining_components == ["final"] and c.can_still_pass is True


def test_missed_work_counts_as_zero_and_late_is_detected():
    late = _a(2, 90, submitted=datetime(2026, 10, 12, 9))
    missed = _a(3, None, submitted=None)
    c = build_snapshot(_records([_a(1, 90), late, missed]), GradingPolicy(), AS_OF).current[0]
    assert c.missing_count == 1 and c.late_count == 1
    assert c.coursework_pct == pytest.approx(60.0)               # (90 + 90 + 0) / 3


def test_future_assessments_are_ignored():
    future = _a(2, None, due=date(2026, 12, 1), submitted=None)
    c = build_snapshot(_records([_a(1, 70), future]), GradingPolicy(), AS_OF).current[0]
    assert c.due_count == 1 and c.missing_count == 0


def test_cannot_pass_when_needed_above_100():
    c = build_snapshot(_records([_a(1, 10)], midterm=10), GradingPolicy(), AS_OF).current[0]
    assert c.needed_on_remaining_pct > 100 and c.can_still_pass is False


def test_attendance_uses_recorded_lectures_only():
    c = build_snapshot(_records([_a(1, 70)], attendance=[True, True, False]), GradingPolicy(), AS_OF).current[0]
    assert c.lectures_recorded == 3 and c.attendance_rate == pytest.approx(2 / 3)


def test_no_data_is_reported_not_guessed():
    snap = build_snapshot(_records([], midterm=None), GradingPolicy(), AS_OF)
    assert snap.current[0].standing_pct is None
    assert any("No grades" in g for g in snap.data_gaps) and "No GPA entries" in snap.data_gaps
