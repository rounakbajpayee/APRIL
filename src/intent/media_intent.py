"""
media_intent.py - Media handling for APRIL phase 1.
"""

from __future__ import annotations

from typing import Any

from media import handle_media
from .tool_interface import IntentPlan, IntentResult

INTENT_NAME = "media"
TRIGGERS = [
    "continue watching",
    "continue what i was watching",
    "jellyfin",
    "play",
    "watch",
]
OLLAMA_DESCRIPTION = "Play or continue media in Jellyfin"
EXAMPLES = [
    {
        "text": "continue watching",
        "response_preview": "Opening Jellyfin.",
        "action": {"mode": "continue"},
    },
    {
        "text": "play family guy",
        "response_preview": "Looking that up in Jellyfin.",
        "action": {"mode": "play", "title": "Family Guy"},
    },
    {
        "text": "watch the office",
        "response_preview": "Looking that up in Jellyfin.",
        "action": {"mode": "play", "title": "The Office"},
    },
    {
        "text": "resume the movie",
        "response_preview": "Opening Jellyfin.",
        "action": {"mode": "continue"},
    },
]


def match(text: str, lowered: str) -> IntentPlan | None:
    if "continue what i was watching" in lowered or "continue watching" in lowered:
        return {
            "intent": INTENT_NAME,
            "response_preview": "Opening Jellyfin.",
            "action": {"mode": "continue", "text": text},
        }
    if "jellyfin" in lowered or lowered.startswith(("play ", "watch ")):
        title = text
        for prefix in ("play ", "watch "):
            if lowered.startswith(prefix):
                title = text[len(prefix) :].strip()
                break
        return {
            "intent": INTENT_NAME,
            "response_preview": "Looking that up in Jellyfin.",
            "action": {"mode": "play", "title": title, "text": text},
        }
    return None


def execute(
    action: dict[str, Any],
    config: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> IntentResult:
    try:
        reply = handle_media(action, config)
    except Exception as exc:
        import runtime_trace

        runtime_trace.trace_event(
            "media_execute_error",
            subsystem="intent.media",
            severity=runtime_trace.ERROR,
            payload={"error": str(exc), "action": str(action.get("mode", ""))},
        )
        return {
            "reply": f"Media action failed: {exc}",
            "config_changed": False,
            "ok": False,
            "error_kind": "media_error",
        }
    lowered = str(reply or "").lower()
    ok = "not configured yet" not in lowered
    return {
        "reply": reply,
        "config_changed": False,
        "ok": ok,
        "error_kind": None if ok else "media_failed",
    }


def handle(
    action: dict[str, Any],
    config: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> IntentResult:
    return execute(action, config, context)
