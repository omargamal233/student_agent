"""Groq model and the LangChain chain that produces structured advice."""
from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from langchain_groq import ChatGroq

from ..config import Settings
from .prompts import ADVICE_HUMAN, ADVICE_SYSTEM
from .schemas import AdviceBundle


class MissingApiKeyError(RuntimeError):
    """GROQ_API_KEY is not configured."""


def build_chat_model(settings: Settings) -> BaseChatModel:
    if not settings.groq_api_key:
        raise MissingApiKeyError(
            "GROQ_API_KEY is not set. Copy .env.example to .env and add your key "
            "(or call the offline endpoints: /students/<id>, or /students/<id>/assessment?use_llm=false)."
        )
    return ChatGroq(
        model=settings.groq_model,                 # "openai/gpt-oss-120b"
        api_key=settings.groq_api_key,
        temperature=settings.temperature,
        reasoning_effort=settings.reasoning_effort,
        max_tokens=settings.max_tokens,
        max_retries=2,
    )


def build_advice_chain(model: BaseChatModel) -> Runnable:
    """prompt -> model -> AdviceBundle. Tries strict JSON-schema output first, then tool-calling."""
    prompt = ChatPromptTemplate.from_messages([("system", ADVICE_SYSTEM), ("human", ADVICE_HUMAN)])
    primary = prompt | model.with_structured_output(AdviceBundle, method="json_schema")
    backup = prompt | model.with_structured_output(AdviceBundle, method="function_calling")
    return primary.with_fallbacks([backup])
