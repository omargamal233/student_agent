"""Dropout-risk scoring.

``HeuristicRiskModel`` is a transparent, rule-based score (0-100) built from weighted
factors. It implements the ``RiskModel`` protocol, so a trained model (XGBoost /
random forest) can replace it later without touching the agent.
"""
from __future__ import annotations

from enum import Enum
from typing import Protocol

from pydantic import BaseModel, Field

from ..config import GradingPolicy, LevelThresholds, RiskWeights
from .features import StudentSnapshot


class RiskLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


_ORDER = [RiskLevel.LOW, RiskLevel.MODERATE, RiskLevel.HIGH, RiskLevel.CRITICAL]


class RiskFactor(BaseModel):
    key: str
    label: str
    severity: float          # 0 (fine) .. 1 (worst)
    weight: float            # configured weight
    contribution: float      # points of the 0-100 score this factor adds
    evidence: str            # human-readable facts behind the number


class RiskAssessment(BaseModel):
    score: float
    level: RiskLevel
    factors: list[RiskFactor] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)     # hard warnings that can raise the level
    data_coverage: float = 1.0                         # share of factor weight that had data


class RiskModel(Protocol):
    def assess(self, snapshot: StudentSnapshot) -> RiskAssessment: ...


def _lin(x: float, good: float, bad: float) -> float:
    """0 when x >= good, 1 when x <= bad, linear in between."""
    if good == bad:
        return 0.0
    return max(0.0, min(1.0, (good - x) / (good - bad)))


def _wavg(items: list[tuple[float, float | None]]) -> float:
    total = sum((w or 1.0) for _, w in items)
    return sum(v * (w or 1.0) for v, w in items) / total


class HeuristicRiskModel:
    def __init__(self, policy: GradingPolicy, weights: RiskWeights, thresholds: LevelThresholds):
        self.policy = policy
        self.weights = weights
        self.thresholds = thresholds

    # -- public ----------------------------------------------------------------
    def assess(self, s: StudentSnapshot) -> RiskAssessment:
        raw = [
            self._standing(s), self._attendance(s), self._missing_work(s), self._trend(s),
            self._gpa(s), self._past_failures(s), self._overdue(s),
        ]
        available = [f for f in raw if f is not None]
        total_w = sum(f[2] for f in available)
        factors: list[RiskFactor] = []
        score = 0.0
        for key, label, weight, severity, evidence in available:
            contribution = 100.0 * weight * severity / total_w if total_w else 0.0
            score += contribution
            factors.append(RiskFactor(key=key, label=label, severity=round(severity, 3),
                                      weight=weight, contribution=round(contribution, 1),
                                      evidence=evidence))
        factors.sort(key=lambda f: f.contribution, reverse=True)

        flags, floor = self._flags(s)
        level = self._level(score)
        if _ORDER.index(floor) > _ORDER.index(level):
            level = floor
        all_w = sum(self.weights.model_dump().values())
        return RiskAssessment(score=round(score, 1), level=level, factors=factors, flags=flags,
                              data_coverage=round(total_w / all_w, 2) if all_w else 0.0)

    # -- factors: each returns (key, label, weight, severity, evidence) or None -----
    def _standing(self, s):
        cs = [c for c in s.current if c.standing_pct is not None]
        if not cs:
            return None
        avg = _wavg([(c.standing_pct, c.credit_hours) for c in cs])
        worst = min(cs, key=lambda c: c.standing_pct)
        sev = 0.6 * _lin(avg, 65, 30) + 0.4 * _lin(worst.standing_pct, 65, 30)
        ev = (f"Average standing {avg:.0f}% across {len(cs)} courses; weakest is {worst.name} "
              f"at {worst.standing_pct:.0f}% (pass mark {self.policy.pass_mark:.0f}%)")
        return ("standing", "Academic standing", self.weights.standing, sev, ev)

    def _attendance(self, s):
        cs = [c for c in s.current if c.attendance_rate is not None]
        if not cs:
            return None
        avg = _wavg([(c.attendance_rate, c.credit_hours) for c in cs])
        worst = min(cs, key=lambda c: c.attendance_rate)
        sev = 0.5 * _lin(avg, 0.90, 0.50) + 0.5 * _lin(worst.attendance_rate, 0.90, 0.50)
        ev = (f"Average attendance {avg:.0%}; lowest is {worst.name} at {worst.attendance_rate:.0%} "
              f"(minimum {self.policy.min_attendance:.0%})")
        return ("attendance", "Lecture attendance", self.weights.attendance, sev, ev)

    def _missing_work(self, s):
        due = sum(c.due_count for c in s.current)
        if due == 0:
            return None
        missing = sum(c.missing_count for c in s.current)
        late = sum(c.late_count for c in s.current)
        sev = max(0.0, min(1.0, ((missing + 0.5 * late) / due) / 0.5))
        ev = f"{missing} missed and {late} late submissions out of {due} assessments already due"
        return ("missing_work", "Missed and late work", self.weights.missing_work, sev, ev)

    def _trend(self, s):
        ts = [c.trend_points for c in s.current if c.trend_points is not None]
        if not ts:
            return None
        avg = sum(ts) / len(ts)
        sev = max(0.0, min(1.0, -avg / 25.0))
        ev = f"Scores changed by {avg:+.0f} points between the first and second half of the term"
        return ("trend", "Recent score trend", self.weights.trend, sev, ev)

    def _gpa(self, s):
        if s.gpa is None:
            return None
        sev = _lin(s.gpa, 3.0, 1.5)
        return ("gpa", "GPA", self.weights.gpa, sev, f"GPA from recorded entries: {s.gpa:.2f} / 4.0")

    def _past_failures(self, s):
        if not s.finished:
            return None
        sev = max(0.0, min(1.0, s.past_failures / 2.0))
        ev = f"{s.past_failures} failed course(s) out of {len(s.finished)} completed"
        return ("past_failures", "Previous failures", self.weights.past_failures, sev, ev)

    def _overdue(self, s):
        if s.total_tasks == 0:
            return None
        n = len(s.overdue_tasks)
        sev = max(0.0, min(1.0, n / 4.0))
        return ("overdue_tasks", "Overdue tasks", self.weights.overdue_tasks, sev,
                f"{n} task(s) past their deadline")

    # -- hard flags and level floors -------------------------------------------------
    def _flags(self, s: StudentSnapshot) -> tuple[list[str], RiskLevel]:
        flags: list[str] = []
        floor = RiskLevel.LOW

        low_att = [c for c in s.current
                   if c.attendance_rate is not None and c.attendance_rate < self.policy.min_attendance]
        for c in low_att:
            flags.append(f"Attendance in {c.name} is {c.attendance_rate:.0%}, below the "
                         f"{self.policy.min_attendance:.0%} minimum (risk of being barred from the exam)")
        if len(low_att) >= 2:
            floor = RiskLevel.HIGH
        elif len(low_att) == 1:
            floor = RiskLevel.MODERATE

        lost = [c for c in s.current if c.can_still_pass is False]
        for c in lost:
            flags.append(f"Even a perfect result on the remaining work cannot lift {c.name} to the "
                         f"{self.policy.pass_mark:.0f}% pass mark")
        if len(lost) >= 2:
            floor = RiskLevel.CRITICAL
        elif len(lost) == 1 and _ORDER.index(floor) < _ORDER.index(RiskLevel.HIGH):
            floor = RiskLevel.HIGH
        return flags, floor

    def _level(self, score: float) -> RiskLevel:
        t = self.thresholds
        if score >= t.critical:
            return RiskLevel.CRITICAL
        if score >= t.high:
            return RiskLevel.HIGH
        if score >= t.moderate:
            return RiskLevel.MODERATE
        return RiskLevel.LOW
