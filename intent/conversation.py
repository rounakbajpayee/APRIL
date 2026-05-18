"""
conversation.py - Conversational fallback handling.
"""

from __future__ import annotations

from typing import Any

from brain import respond


def handle(action: dict[str, Any], config: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    context = context or {}
    if str(action.get("mode", "") or "").strip().lower() == "direct_reply":
        reply = str(action.get("reply", "") or "").strip()
        return {"reply": reply, "config_changed": False}
    text = str(action.get("text") or context.get("text") or "").strip()
    return {"reply": respond(text, config), "config_changed": False}
