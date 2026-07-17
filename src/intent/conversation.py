"""
conversation.py - Conversational fallback handling.
"""

from __future__ import annotations

from typing import Any

from brain import respond

from .tool_interface import IntentPlan, IntentResult

INTENT_NAME = "conversation"
TRIGGERS: list[str] = []
OLLAMA_DESCRIPTION = "Handle general conversation and fallback replies"
EXAMPLES: list[dict[str, Any]] = []


def match(_text: str, _lowered: str) -> IntentPlan | None:
    return None


def execute(
    action: dict[str, Any],
    config: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> IntentResult:
    context = context or {}
    if str(action.get("mode", "") or "").strip().lower() == "direct_reply":
        reply = str(action.get("reply", "") or "").strip()
        return {"reply": reply, "config_changed": False, "ok": bool(reply)}
    text = str(action.get("text") or context.get("text") or "").strip()
    reply = respond(text, config)
    return {"reply": reply, "config_changed": False, "ok": bool(reply)}


def handle(
    action: dict[str, Any],
    config: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> IntentResult:
    return execute(action, config, context)
