"""Rule-based advice used when the LLM is switched off or unavailable (English only)."""
from __future__ import annotations

from ..services.assessment import StudentAnalysis
from .schemas import AdviceBundle, AdviceItem, PlanStep

_SUMMARY = {
    "low": "Your records look healthy. Keep your current habits and stay ahead of upcoming deadlines.",
    "moderate": "A few warning signs need attention now, while there is still time to fix them.",
    "high": "Several indicators put your term at risk. Acting this week can still change the outcome.",
    "critical": "Your records show serious risk in multiple areas. Please act now and talk to your advisor.",
}

_TEMPLATES = {
    "standing": ("Focus on your weakest course", "Spend extra study blocks on the course with the lowest standing."),
    "attendance": ("Fix your attendance", "Attend every lecture of the courses below the minimum attendance."),
    "missing_work": ("Submit missing and late work", "Hand in what is still open, even partially, and start earlier next time."),
    "trend": ("Stop the score decline", "Review the last quiz and assignment mistakes and ask the instructor for feedback."),
    "gpa": ("Raise your GPA", "Prioritise courses with the most credit hours and plan weekly revision."),
    "past_failures": ("Close old gaps", "Revisit topics from failed courses that current courses build on."),
    "overdue_tasks": ("Clear overdue tasks", "Finish or reschedule overdue tasks, starting with the highest severity."),
}


def rule_based_advice(a: StudentAnalysis) -> AdviceBundle:
    risk, snap = a.risk, a.snapshot
    items: list[AdviceItem] = []
    for i, f in enumerate([f for f in risk.factors if f.contribution > 0][:4], start=1):
        title, action = _TEMPLATES[f.key]
        items.append(AdviceItem(priority=i, title=title, action=action, why=f.evidence))
    if risk.level.value in ("high", "critical"):
        items.append(AdviceItem(priority=len(items) + 1, title="Talk to your academic advisor",
                                action="Book a meeting with your advisor or instructor this week.",
                                why=f"Risk level is {risk.level.value}."))
    if not items:
        items.append(AdviceItem(priority=1, title="Keep going", action="Keep attending and submitting on time.",
                                why="No risk factors were found."))

    plan = [PlanStep(when=f"{t.deadline:%a %d %b}", step=f"Finish: {t.description}")
            for t in (snap.overdue_tasks + snap.upcoming_tasks)[:7]]
    return AdviceBundle(summary=_SUMMARY[risk.level.value], advice=items, weekly_plan=plan,
                        encouragement="Small, consistent steps this week make the biggest difference.")
