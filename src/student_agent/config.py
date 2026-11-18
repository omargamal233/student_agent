"""Central configuration: environment settings plus the academic policy assumptions."""
from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class GradingPolicy(BaseModel):
    """How course grades work. These are ASSUMPTIONS: confirm them with the faculty.

    Component weights are fractions of the final course mark (they should sum to 1).
    The assessments table has a ``weight`` column; here it is used only as a
    *relative* weight inside the coursework component.
    """

    pass_mark: float = 50.0            # % needed to pass a course
    coursework_weight: float = 0.40    # quizzes + assignments
    midterm_weight: float = 0.20
    final_weight: float = 0.40
    min_attendance: float = 0.75       # below this the student risks being barred from the exam
    gpa_scale: dict[str, float] = Field(
        default_factory=lambda: {
            "A+": 4.0, "A": 4.0, "A-": 3.7,
            "B+": 3.3, "B": 3.0, "B-": 2.7,
            "C+": 2.3, "C": 2.0, "C-": 1.7,
            "D+": 1.3, "D": 1.0, "F": 0.0,
        }
    )


class RiskWeights(BaseModel):
    """Relative importance of each risk factor (renormalised when a factor has no data)."""

    standing: float = 0.30
    attendance: float = 0.20
    missing_work: float = 0.15
    trend: float = 0.10
    gpa: float = 0.10
    past_failures: float = 0.10
    overdue_tasks: float = 0.05


class LevelThresholds(BaseModel):
    """Lower bound of each level on the 0-100 risk score."""

    moderate: float = 20.0
    high: float = 40.0
    critical: float = 60.0


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    # --- LLM (Groq) ---
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"
    temperature: float = 0.2
    reasoning_effort: Literal["low", "medium", "high"] = "medium"
    max_tokens: int = 4096

    # --- API server ---
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    # --- Data source ---
    fake_db_path: Path = PROJECT_ROOT / "data" / "fake_db.json"
    as_of_date: date | None = None

    # --- Domain rules ---
    policy: GradingPolicy = GradingPolicy()
    risk_weights: RiskWeights = RiskWeights()
    thresholds: LevelThresholds = LevelThresholds()


@lru_cache
def get_settings() -> Settings:
    return Settings()
