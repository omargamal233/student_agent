"""Compact, LLM-friendly view of a StudentAnalysis (the only thing the LLM sees)."""
from __future__ import annotations

from typing import Any

from ..config import GradingPolicy
from ..services.assessment import StudentAnalysis, course_status


def _r(x: float | None, n: int = 0) -> float | None:
    return None if x is None else round(x, n)


def course_facts(c, policy: GradingPolicy) -> dict[str, Any]:
    return {
        "course": c.name,
        "credit_hours": c.credit_hours,
        "status": course_status(c, policy),
        "standing_pct": _r(c.standing_pct),
        "coursework_pct": _r(c.coursework_pct),
        "midterm_pct": _r(c.midterm_pct),
        "final_pct": _r(c.final_pct),
        "attendance_pct": _r(c.attendance_rate * 100) if c.attendance_rate is not None else None,
        "lectures_recorded": c.lectures_recorded,
        "missed_assessments": c.missing_titles,
        "late_submissions": c.late_count,
        "score_trend_points": _r(c.trend_points),
        "needed_on_remaining_pct": _r(c.needed_on_remaining_pct),
        "remaining_components": c.remaining_components,
    }


def analysis_to_facts(a: StudentAnalysis, policy: GradingPolicy) -> dict[str, Any]:
    s, r = a.snapshot, a.risk
    return {
        "student": {"name": s.profile.name, "department": s.profile.department},
        "as_of": s.as_of.isoformat(),
        "risk_score": r.score,
        "risk_level": r.level.value,
        "data_coverage": r.data_coverage,
        "warnings": r.flags,
        "risk_factors": [{"factor": f.label, "points": f.contribution, "evidence": f.evidence}
                         for f in r.factors if f.contribution > 0],
        "current_courses": [course_facts(c, policy) for c in s.current],
        "gpa": _r(s.gpa, 2),
        "past_failures": s.past_failures,
        "overdue_tasks": [t.model_dump(mode="json") for t in s.overdue_tasks],
        "upcoming_tasks_14_days": [t.model_dump(mode="json") for t in s.upcoming_tasks],
        "data_gaps": s.data_gaps,
        "available_resources": [{"course": x.course, "kind": x.kind, "title": x.title} for x in a.resources],
        "policy": {"pass_mark_pct": policy.pass_mark, "min_attendance_pct": policy.min_attendance * 100},
    }
