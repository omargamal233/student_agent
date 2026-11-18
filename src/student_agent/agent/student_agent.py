"""The Student Intelligence agent: risk report (structured) and chat (tool-calling)."""
from __future__ import annotations

import json
import logging
from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import Runnable

from ..config import Settings, get_settings
from ..services.assessment import AssessmentService, StudentAnalysis, course_status
from .facts import analysis_to_facts
from .fallback import rule_based_advice
from .llm import build_advice_chain, build_chat_model
from .prompts import CHAT_SYSTEM, LANGUAGE_NAMES
from .schemas import AdviceBundle, CourseInsight, DropoutReport
from .tools import make_tools

log = logging.getLogger(__name__)


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)


class StudentAgent:
    def __init__(self, service: AssessmentService, settings: Settings | None = None, *,
                 chat_model: BaseChatModel | None = None, advice_chain: Runnable | None = None):
        self._service = service
        self._settings = settings or get_settings()
        self._chat_model = chat_model
        self._advice_chain = advice_chain
        self._chat_agents: dict[int, Any] = {}

    # -- lazy LLM parts (so offline commands never need an API key) -----------------
    @property
    def chat_model(self) -> BaseChatModel:
        if self._chat_model is None:
            self._chat_model = build_chat_model(self._settings)
        return self._chat_model

    @property
    def advice_chain(self) -> Runnable:
        if self._advice_chain is None:
            self._advice_chain = build_advice_chain(self.chat_model)
        return self._advice_chain

    # -- 1) deterministic analysis (no LLM) ---------------------------------------------
    def analyze(self, student_id: int) -> StudentAnalysis:
        return self._service.analyze(student_id)

    # -- 2) the main output: dropout-risk report ---------------------------------------
    def assess(self, student_id: int, language: str = "en", use_llm: bool = True) -> DropoutReport:
        if language not in LANGUAGE_NAMES:
            raise ValueError(f"language must be one of {sorted(LANGUAGE_NAMES)}")
        analysis = self.analyze(student_id)
        warnings: list[str] = []
        source = "llm"

        if use_llm:
            facts = analysis_to_facts(analysis, self._service.policy)
            chain = self.advice_chain                      # raises MissingApiKeyError if no key
            try:
                bundle = chain.invoke({"facts": json.dumps(facts, ensure_ascii=False, indent=1),
                                       "language_name": LANGUAGE_NAMES[language]})
                if not isinstance(bundle, AdviceBundle):
                    bundle = AdviceBundle.model_validate(bundle)
            except Exception as exc:                       # network, quota, schema errors
                log.warning("LLM advice failed: %s", exc)
                bundle, source = rule_based_advice(analysis), "rule_based"
                warnings.append(f"The language model was unavailable ({type(exc).__name__}); "
                                "rule-based advice is shown instead.")
        else:
            bundle, source = rule_based_advice(analysis), "rule_based"
        return self._report(analysis, bundle, language, source, warnings)

    # -- 3) conversational follow-up --------------------------------------------------------
    def chat(self, student_id: int, message: str,
             history: list[BaseMessage] | None = None) -> tuple[str, list[BaseMessage]]:
        """Answer one message. Pass the returned history back in to keep the conversation."""
        agent = self._chat_agents.get(student_id) or self._build_chat_agent(student_id)
        self._chat_agents[student_id] = agent
        messages = list(history or []) + [HumanMessage(content=message)]
        result = agent.invoke({"messages": messages})
        out: list[BaseMessage] = result["messages"]
        reply = next((_text(m.content) for m in reversed(out) if isinstance(m, AIMessage) and m.content), "")
        return reply, out

    # -- internals ------------------------------------------------------------------------
    def _build_chat_agent(self, student_id: int):
        profile = self._service.analyze(student_id).snapshot.profile   # also validates the id
        prompt = CHAT_SYSTEM.format(student_id=student_id, student_name=profile.name,
                                    as_of=self._service.as_of.isoformat())
        return create_agent(self.chat_model, tools=make_tools(self._service, student_id),
                            system_prompt=prompt)

    def _report(self, a: StudentAnalysis, bundle: AdviceBundle, language: str, source: str,
                warnings: list[str]) -> DropoutReport:
        policy = self._service.policy
        courses = [CourseInsight(
            course=c.name, status=course_status(c, policy), standing_pct=c.standing_pct,
            attendance_pct=None if c.attendance_rate is None else c.attendance_rate * 100,
            missed_work=c.missing_count, late_work=c.late_count,
            needed_on_remaining_pct=c.needed_on_remaining_pct) for c in a.snapshot.current]
        return DropoutReport(
            student_id=a.snapshot.profile.student_id, student_name=a.snapshot.profile.name,
            as_of=a.snapshot.as_of, language=language, risk_level=a.risk.level,
            risk_score=a.risk.score, data_coverage=a.risk.data_coverage, flags=a.risk.flags,
            factors=a.risk.factors, courses=courses, summary=bundle.summary,
            advice=sorted(bundle.advice, key=lambda x: x.priority), weekly_plan=bundle.weekly_plan,
            resources=a.resources, encouragement=bundle.encouragement, data_gaps=a.snapshot.data_gaps,
            advice_source=source, warnings=warnings)
