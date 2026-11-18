"""HTTP API (replaces the old command line).

The caller sends a student id and gets that student's data back:

    GET  /health
    GET  /students/<student_id>                 numbers + risk, no LLM (offline)
    GET  /students/<student_id>/assessment      full report with advice
                                                ?lang=en|ar   ?use_llm=true|false
    POST /students/<student_id>/chat            {"message": "...", "history": [...]}

Run it with ``python -m student_agent`` (or ``flask --app student_agent.api:create_app run``).
"""
from __future__ import annotations

import logging
from typing import Any

from flask import Flask, jsonify, request, Response
from langchain_core.messages import AIMessage, HumanMessage

from .agent.llm import MissingApiKeyError
from .agent.prompts import LANGUAGE_NAMES
from .agent.student_agent import StudentAgent
from .app import build_agent
from .data.repository import StudentNotFound

log = logging.getLogger(__name__)

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _parse_student_id(raw: str) -> int:
    try:
        student_id = int(raw)
    except (TypeError, ValueError):
        raise ApiError(400, f"student_id must be an integer, got {raw!r}") from None
    if student_id <= 0:
        raise ApiError(400, "student_id must be a positive integer")
    return student_id


def _parse_bool(raw: str | None, default: bool, name: str) -> bool:
    if raw is None or raw == "":
        return default
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ApiError(400, f"{name} must be true or false")


def _history_to_messages(history: Any) -> list:
    """[{"role": "user"|"assistant", "content": "..."}] -> LangChain messages."""
    if history is None:
        return []
    if not isinstance(history, list):
        raise ApiError(400, "history must be a list of {role, content} objects")
    out = []
    for item in history:
        if not isinstance(item, dict) or not isinstance(item.get("content"), str):
            raise ApiError(400, "each history item must be an object with a string 'content'")
        role = item.get("role")
        if role == "user":
            out.append(HumanMessage(content=item["content"]))
        elif role == "assistant":
            out.append(AIMessage(content=item["content"]))
        else:
            raise ApiError(400, "history role must be 'user' or 'assistant'")
    return out


def _messages_to_history(messages: list) -> list[dict[str, str]]:
    """Keep only the human/assistant text turns (tool calls are an internal detail)."""
    out = []
    for m in messages:
        if isinstance(m, HumanMessage):
            role = "user"
        elif isinstance(m, AIMessage) and m.content and not getattr(m, "tool_calls", None):
            role = "assistant"
        else:
            continue
        content = m.content if isinstance(m.content, str) else "".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in m.content)
        out.append({"role": role, "content": content})
    return out


def create_app(agent: StudentAgent | None = None) -> Flask:
    """Build the Flask app. Tests pass their own ``agent``."""
    app = Flask(__name__)
    app.json.ensure_ascii = False          # keep Arabic readable in responses
    app.json.sort_keys = False
    app.config["agent"] = agent or build_agent()

    def get_agent() -> StudentAgent:
        return app.config["agent"]

    # ---- routes -----------------------------------------------------------------
    @app.get("/")
    def index():
        return Response(
            """<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><title>Student Intelligence Agent</title></head>
  <body>
    <h1>Student Intelligence Agent</h1>
    <p>API is running. Open <a href="/docs">/docs</a> or <a href="/health">/health</a>.</p>
  </body>
</html>""",
            mimetype="text/html",
        )

    @app.get("/docs")
    def docs():
        return Response(
            """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Student Intelligence Agent - Swagger</title>
    <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
  </head>
  <body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script>
      SwaggerUIBundle({
        url: "/openapi.json",
        dom_id: "#swagger-ui",
        deepLinking: true,
        displayRequestDuration: true
      });
    </script>
  </body>
</html>""",
            mimetype="text/html",
        )

    @app.get("/openapi.json")
    def openapi_spec():
        return jsonify(
            openapi="3.0.3",
            info={
                "title": "Student Intelligence Agent",
                "description": "Student risk assessment and advice API",
                "version": "0.1.0",
            },
            servers=[{"url": "http://127.0.0.1:8000"}],
            paths={
                "/health": {
                    "get": {
                        "summary": "Health check",
                        "responses": {
                            "200": {
                                "description": "API is healthy",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {"status": {"type": "string"}},
                                        }
                                    }
                                },
                            }
                        },
                    }
                },
                "/students/{student_id}": {
                    "get": {
                        "summary": "Get student data and risk analysis",
                        "parameters": [
                            {
                                "name": "student_id",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "integer", "minimum": 1},
                            }
                        ],
                        "responses": {"200": {"description": "Student analysis"}, "404": {"description": "Student not found"}},
                    }
                },
                "/students/{student_id}/assessment": {
                    "get": {
                        "summary": "Get a complete student assessment",
                        "parameters": [
                            {
                                "name": "student_id",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "integer", "minimum": 1},
                            },
                            {
                                "name": "lang",
                                "in": "query",
                                "required": False,
                                "schema": {"type": "string", "enum": ["en", "ar"], "default": "en"},
                            },
                            {
                                "name": "use_llm",
                                "in": "query",
                                "required": False,
                                "schema": {"type": "boolean", "default": True},
                                "description": "Set false to use rule-based advice without Groq.",
                            },
                        ],
                        "responses": {
                            "200": {"description": "Student assessment"},
                            "400": {"description": "Invalid request"},
                            "404": {"description": "Student not found"},
                            "503": {"description": "Groq API key is not configured"},
                        },
                    }
                },
                "/students/{student_id}/chat": {
                    "post": {
                        "summary": "Chat with the student agent",
                        "parameters": [
                            {
                                "name": "student_id",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "integer", "minimum": 1},
                            }
                        ],
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["message"],
                                        "properties": {
                                            "message": {"type": "string", "example": "What score do I need in Databases?"},
                                            "history": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "required": ["role", "content"],
                                                    "properties": {
                                                        "role": {"type": "string", "enum": ["user", "assistant"]},
                                                        "content": {"type": "string"},
                                                    },
                                                },
                                            },
                                        },
                                    }
                                }
                            },
                        },
                        "responses": {
                            "200": {"description": "Agent reply"},
                            "400": {"description": "Invalid request"},
                            "404": {"description": "Student not found"},
                            "503": {"description": "Groq API key is not configured"},
                        },
                    }
                },
            },
        )

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.get("/students/<student_id>")
    def student_data(student_id: str):
        analysis = get_agent().analyze(_parse_student_id(student_id))
        return jsonify(analysis.model_dump(mode="json"))

    @app.get("/students/<student_id>/assessment")
    def student_assessment(student_id: str):
        sid = _parse_student_id(student_id)
        language = request.args.get("lang", "en")
        if language not in LANGUAGE_NAMES:
            raise ApiError(400, f"lang must be one of {sorted(LANGUAGE_NAMES)}")
        use_llm = _parse_bool(request.args.get("use_llm"), True, "use_llm")
        report = get_agent().assess(sid, language=language, use_llm=use_llm)
        return jsonify(report.model_dump(mode="json"))

    @app.post("/students/<student_id>/chat")
    def student_chat(student_id: str):
        sid = _parse_student_id(student_id)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ApiError(400, "request body must be a JSON object")
        message = body.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ApiError(400, "'message' is required and must be a non-empty string")
        history = _history_to_messages(body.get("history"))
        reply, messages = get_agent().chat(sid, message.strip(), history or None)
        return jsonify(student_id=sid, reply=reply, history=_messages_to_history(messages))

    # ---- errors -----------------------------------------------------------------
    def _error(status: int, message: str):
        return jsonify(error=message), status

    @app.errorhandler(ApiError)
    def _api_error(exc: ApiError):
        return _error(exc.status, exc.message)

    @app.errorhandler(StudentNotFound)
    def _not_found(exc: StudentNotFound):
        return _error(404, str(exc))

    @app.errorhandler(MissingApiKeyError)
    def _no_key(exc: MissingApiKeyError):
        return _error(503, str(exc))

    @app.errorhandler(404)
    def _no_route(_exc):
        return _error(404, "Not found")

    @app.errorhandler(405)
    def _bad_method(_exc):
        return _error(405, "Method not allowed")

    @app.errorhandler(Exception)
    def _unexpected(exc: Exception):
        log.exception("Unhandled error")
        return _error(500, "Internal server error")

    return app


def main() -> None:
    from .config import get_settings

    settings = get_settings()
    logging.basicConfig(level=logging.INFO)
    create_app().run(host=settings.api_host, port=settings.api_port)
