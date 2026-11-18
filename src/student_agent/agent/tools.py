"""Tools for the chat agent.

They are created per student (``student_id`` is bound in a closure), so the model can
never ask for another student's data: it does not even have a student_id argument.
"""
from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool, tool

from ..analytics.features import needed_on_remaining
from ..services.assessment import AssessmentService
from .facts import analysis_to_facts, course_facts


def make_tools(service: AssessmentService, student_id: int) -> list[BaseTool]:
    policy = service.policy

    def _course_or_error(snapshot, name: str) -> tuple[Any, dict | None]:
        matches = snapshot.find_course(name)
        if len(matches) == 1:
            return matches[0], None
        names = [c.name for c in snapshot.current + snapshot.finished]
        if not matches:
            return None, {"error": f"No course matches '{name}'.", "available_courses": names}
        return None, {"error": f"'{name}' matches several courses; ask the student which one.",
                      "matches": [c.name for c in matches]}

    @tool
    def get_risk_overview() -> dict:
        """Get the student's overall dropout-risk level and score, the main factors behind it,
        warnings, GPA, overdue tasks and the status of every current course.
        Call this first for any question about risk or how the student is doing."""
        return analysis_to_facts(service.analyze(student_id), policy)

    @tool
    def get_course_details(course_name: str) -> dict:
        """Get standing, attendance, missed or late work, score trend and the score still needed
        to pass for ONE course. Argument: the course name (partial names work)."""
        snap = service.analyze(student_id).snapshot
        course, err = _course_or_error(snap, course_name)
        return err or course_facts(course, policy)

    @tool
    def get_tasks() -> dict:
        """List the student's overdue tasks and the tasks due in the next 14 days."""
        snap = service.analyze(student_id).snapshot
        return {
            "as_of": snap.as_of.isoformat(),
            "overdue": [t.model_dump(mode="json") for t in snap.overdue_tasks],
            "due_in_14_days": [t.model_dump(mode="json") for t in snap.upcoming_tasks],
        }

    @tool
    def get_study_resources(course_name: str = "") -> dict:
        """Get study materials and links for the student's weakest courses, or for one course
        if a name is given. Reference materials by title; do not invent links."""
        res = service.analyze(student_id).resources
        if course_name:
            res = [r for r in res if course_name.lower() in r.course.lower()]
        return {"resources": [r.model_dump() for r in res]}

    @tool
    def what_score_do_i_need(course_name: str, target_percent: float = 50.0) -> dict:
        """What average the student needs on the remaining work (usually the final exam) of one
        course to reach a target total, e.g. target_percent=50 for passing or 70 for a better grade."""
        snap = service.analyze(student_id).snapshot
        course, err = _course_or_error(snap, course_name)
        if err:
            return err
        target = max(0.0, min(100.0, float(target_percent)))
        needed = needed_on_remaining(course, target)
        if needed is None:
            return {"course": course.name, "message": "Every component is already graded.",
                    "final_standing_pct": round(course.standing_pct or 0, 1)}
        verdict = "already_secured" if needed <= 0 else "out_of_reach" if needed > 100 else "possible"
        return {"course": course.name, "target_percent": target,
                "needed_on_remaining_pct": round(needed, 1),
                "remaining_components": course.remaining_components, "verdict": verdict}

    return [get_risk_overview, get_course_details, get_tasks, get_study_resources, what_score_do_i_need]
