"""Composition root: wires settings, data source, risk model and agent together."""
from __future__ import annotations

from .agent.student_agent import StudentAgent
from .analytics.risk import HeuristicRiskModel
from .config import Settings, get_settings
from .data.json_repository import JsonRepository
from .services.assessment import AssessmentService


def build_service(settings: Settings | None = None) -> AssessmentService:
    s = settings or get_settings()
    repo = JsonRepository(s.fake_db_path)          # <- swap for the real DB repository later
    risk_model = HeuristicRiskModel(s.policy, s.risk_weights, s.thresholds)   # <- or an ML model
    return AssessmentService(repo, s.policy, risk_model, as_of=s.as_of_date)


def build_agent(settings: Settings | None = None) -> StudentAgent:
    s = settings or get_settings()
    return StudentAgent(build_service(s), s)
