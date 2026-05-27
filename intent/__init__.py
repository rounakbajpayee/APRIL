"""
intent package - APRIL phase 1 execution dispatcher.
"""

from __future__ import annotations

from typing import Any

from screen_capture import capture_and_query

import runtime_trace
from . import registry


def execute_plan(plan: dict[str, Any], config: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    context = context or {}
    intent = str(plan.get("intent", "") or "").strip().lower()
    action = plan.get("action")
    if not isinstance(action, dict):
        action = {}
    tool = registry.get(intent) or registry.get("conversation")
    if tool is None:
        raise RuntimeError("conversation tool is not registered")
    try:
        return tool.execute(action, config, context)
    except Exception as exc:
        runtime_trace.trace_event(
            "intent_execute_error",
            subsystem="intent",
            severity=runtime_trace.ERROR,
            payload={"intent": intent, "error": str(exc), "error_type": type(exc).__name__},
        )
        return {
            "reply": f"Something went wrong while handling that: {exc}",
            "config_changed": False,
            "ok": False,
            "error_kind": "unhandled_exception",
        }
