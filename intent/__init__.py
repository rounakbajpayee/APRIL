"""
intent package - APRIL phase 1 execution dispatcher.
"""

from __future__ import annotations

from typing import Any

from . import browser, config_intent, conversation, device, media_intent, shell
from screen_capture import capture_and_query


def execute_plan(plan: dict[str, Any], config: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    context = context or {}
    intent = str(plan.get("intent", "") or "").strip().lower()
    action = plan.get("action")
    if not isinstance(action, dict):
        action = {}

    if intent == "config":
        return config_intent.handle(action, config, context=context)
    if intent == "device":
        return device.handle(action, config, context=context)
    if intent == "browser":
        return browser.handle(action, config, context=context)
    if intent == "media":
        return media_intent.handle(action, config, context=context)
    if intent == "shell":
        return shell.handle(action, config, context=context)
    if intent == "vision":
        question = str(action.get("question") or action.get("text") or context.get("text") or "").strip()
        reply = capture_and_query(question, config)
        lowered = str(reply or "").lower()
        ok = not any(
            marker in lowered
            for marker in ("not configured yet", "dependencies are not installed", "couldn't capture", "request failed")
        )
        return {
            "reply": reply,
            "config_changed": False,
            "ok": ok,
            "error_kind": None if ok else "vision_failed",
        }
    return conversation.handle(action, config, context=context)
