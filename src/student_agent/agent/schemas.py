"""Output schemas. ``AdviceBundle`` is what the LLM fills; ``DropoutReport`` is the final result."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from ..analytics.risk import RiskFactor, RiskLevel
from ..services.assessment import ResourceSuggestion


# ---- produced by the LLM (structured output) -------------------------------------
class AdviceItem(BaseModel):
    priority: int = Field(description="1 = most urgent")
    title: str = Field(description="Short action title")
    action: str = Field(description="What exactly to do, doable within a week")
    why: str = Field(description="Reason, citing the student's own numbers")
    course: str | None = Field(default=None, description="Related course name, if any")


class PlanStep(BaseModel):
    when: str = Field(description="Day or date, e.g. 'Thu 19 Nov' or 'This week'")
    step: str


class AdviceBundle(BaseModel):
    summary: str = Field(description="2-3 sentences explaining the risk level in plain words")
    advice: list[AdviceItem]
    weekly_plan: list[PlanStep] = Field(description="Up to 7 steps tied to real deadlines and lectures")
    encouragement: str = Field(description="One short, honest, supportive sentence")


# ---- final report -----------------------------------------------------------------
class CourseInsight(BaseModel):
    course: str
    status: str
    standing_pct: float | None = None
    attendance_pct: float | None = None
    missed_work: int = 0
    late_work: int = 0
    needed_on_remaining_pct: float | None = None


class DropoutReport(BaseModel):
    student_id: int
    student_name: str
    as_of: date
    language: str
    risk_level: RiskLevel
    risk_score: float
    data_coverage: float
    flags: list[str]
    factors: list[RiskFactor]
    courses: list[CourseInsight]
    summary: str
    advice: list[AdviceItem]
    weekly_plan: list[PlanStep]
    resources: list[ResourceSuggestion]
    encouragement: str
    data_gaps: list[str]
    advice_source: str = "llm"          # "llm" or "rule_based" (fallback when the LLM is unavailable)
    warnings: list[str] = Field(default_factory=list)
    disclaimer: str = ("This is an automated estimate from the data on Eng Hub, not a final decision. "
                       "Talk to your academic advisor for official guidance.")

    def to_markdown(self) -> str:
        L: list[str] = []
        L.append(f"# Dropout-risk report: {self.student_name} (ID {self.student_id})")
        L.append(f"*As of {self.as_of}*\n")
        L.append(f"**Risk level: {self.risk_level.value.upper()}**  (score {self.risk_score:.0f}/100, "
                 f"data coverage {self.data_coverage:.0%})\n")
        L.append(self.summary + "\n")
        if self.flags:
            L.append("## Warnings")
            L += [f"- {f}" for f in self.flags]
            L.append("")
        L.append("## What drives the score")
        for f in self.factors:
            if f.contribution > 0:
                L.append(f"- **{f.label}** (+{f.contribution:.0f}): {f.evidence}")
        L.append("\n## Courses")
        L.append("| Course | Status | Standing | Attendance | Missed/Late | Needed on remaining |")
        L.append("| --- | --- | --- | --- | --- | --- |")
        for c in self.courses:
            st = f"{c.standing_pct:.0f}%" if c.standing_pct is not None else "n/a"
            at = f"{c.attendance_pct:.0f}%" if c.attendance_pct is not None else "n/a"
            nd = f"{c.needed_on_remaining_pct:.0f}%" if c.needed_on_remaining_pct is not None else "-"
            L.append(f"| {c.course} | {c.status} | {st} | {at} | {c.missed_work}/{c.late_work} | {nd} |")
        L.append("\n## Advice")
        for a in sorted(self.advice, key=lambda x: x.priority):
            course = f" [{a.course}]" if a.course else ""
            L.append(f"{a.priority}. **{a.title}**{course}: {a.action} *({a.why})*")
        if self.weekly_plan:
            L.append("\n## Plan for the coming week")
            L += [f"- **{p.when}**: {p.step}" for p in self.weekly_plan]
        if self.resources:
            L.append("\n## Study resources")
            for r in self.resources:
                L.append(f"- {r.course}: {r.title}" + (f" ({r.url})" if r.url else ""))
        if self.data_gaps:
            L.append("\n## Missing data")
            L += [f"- {g}" for g in self.data_gaps]
        L.append(f"\n> {self.encouragement}")
        if self.warnings:
            L.append("\n" + "\n".join(f"> Note: {w}" for w in self.warnings))
        L.append(f"\n_{self.disclaimer}_")
        return "\n".join(L)
