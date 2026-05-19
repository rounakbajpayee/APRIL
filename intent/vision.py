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
    intent_package = importlib.import_module("intent")
    reply = intent_package.capture_and_query(question, config)
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
