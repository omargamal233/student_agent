"""Agent tests that run without the Groq API (stubbed LLM)."""
import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from student_agent.agent.llm import MissingApiKeyError, build_advice_chain, build_chat_model
from student_agent.agent.student_agent import StudentAgent
from student_agent.config import Settings


def test_assess_with_stubbed_llm(service, settings, stub_bundle):
    captured = {}

    def fake_chain(inputs):
        captured.update(inputs)
        return stub_bundle

    agent = StudentAgent(service, settings, advice_chain=RunnableLambda(fake_chain))
    report = agent.assess(1003, language="ar")

    assert report.risk_level.value == "high" and report.advice_source == "llm"
    assert [a.priority for a in report.advice] == [1, 2]            # sorted
    assert "Arabic" in captured["language_name"]
    assert "Mona Adel" in captured["facts"]
    assert "password" not in captured["facts"].lower() and "email" not in captured["facts"].lower()
    assert report.resources and "# Dropout-risk report" in report.to_markdown()


def test_llm_failure_falls_back_to_rule_based(service, settings):
    def boom(_):
        raise TimeoutError("network down")

    agent = StudentAgent(service, settings, advice_chain=RunnableLambda(boom))
    report = agent.assess(1004)
    assert report.advice_source == "rule_based" and report.warnings
    assert any("advisor" in a.title.lower() for a in report.advice)   # critical -> talk to advisor


def test_no_llm_mode_needs_no_key(service, settings):
    report = StudentAgent(service, settings).assess(1001, use_llm=False)
    assert report.risk_level.value == "low" and report.advice


def test_missing_key_is_a_clear_error(service, settings):
    with pytest.raises(MissingApiKeyError):
        StudentAgent(service, settings).assess(1001)


def test_invalid_language(service, settings):
    with pytest.raises(ValueError):
        StudentAgent(service, settings).assess(1001, language="fr", use_llm=False)


def test_groq_wiring_builds_without_network():
    s = Settings(_env_file=None, groq_api_key="test-key")
    model = build_chat_model(s)
    assert model.model_name == "openai/gpt-oss-120b" and model.reasoning_effort == "medium"
    assert build_advice_chain(model) is not None


class _ToolModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def test_chat_loop_calls_a_tool_then_answers(service, settings):
    call = AIMessage(content="", tool_calls=[{"name": "get_risk_overview", "args": {}, "id": "c1"}])
    final = AIMessage(content="You are at HIGH risk; Databases needs most attention.")
    agent = StudentAgent(service, settings, chat_model=_ToolModel(messages=iter([call, final])))

    reply, history = agent.chat(1003, "How am I doing?")
    assert "HIGH" in reply
    tool_msgs = [m for m in history if m.type == "tool"]
    assert tool_msgs and "Mona Adel" in tool_msgs[0].content
    assert history[0].type == "human"
