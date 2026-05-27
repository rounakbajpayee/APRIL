"""
vision.py - Screen inspection intent handling.
"""

from __future__ import annotations

import importlib
from typing import Any

from .tool_interface import IntentPlan, IntentResult


INTENT_NAME = "vision"
TRIGGERS = [
    "what's on my screen",
    "what is on my screen",
    "what's this error",
    "what is this error",
    "read this for me",
    "read my screen",
    "take a screenshot",
]
OLLAMA_DESCRIPTION = "Inspect the current screen or answer a question about it"
EXAMPLES = [
    {
        "text": "what's on my screen",
        "response_preview": "Checking the screen.",
        "action": {"question": "what's on my screen"},
    },
    {
        "text": "read my screen",
        "response_preview": "Checking the screen.",
        "action": {"question": "read my screen"},
    },
    {
        "text": "what's this error",
        "response_preview": "Checking the screen.",
        "action": {"question": "what's this error"},
    },
]


def match(text: str, lowered: str) -> IntentPlan | None:
    if any(trigger in lowered for trigger in TRIGGERS):
        return {
            "intent": INTENT_NAME,
            "response_preview": "Checking the screen.",
            "action": {"question": text, "text": text},
        }
    return None


def execute(action: dict[str, Any], config: dict[str, Any], context: dict[str, Any] | None = None) -> IntentResult:
    context = context or {}
    question = str(action.get("question") or action.get("text") or context.get("text") or "").strip()
    try:
        intent_package = importlib.import_module("intent")
        reply = intent_package.capture_and_query(question, config)
    except Exception as exc:
        import runtime_trace
        runtime_trace.trace_event(
            "vision_execute_error",
            subsystem="intent.vision",
            severity=runtime_trace.ERROR,
            payload={"error": str(exc)},
        )
        return {
            "reply": f"Screen inspection failed: {exc}",
            "config_changed": False,
            "ok": False,
            "error_kind": "vision_error",
        }
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
