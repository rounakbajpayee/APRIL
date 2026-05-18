"""
media_intent.py - Media handling for APRIL phase 1.
"""

from __future__ import annotations

from typing import Any

from media import handle_media


def handle(action: dict[str, Any], config: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    reply = handle_media(action, config)
    lowered = str(reply or "").lower()
    ok = "not configured yet" not in lowered
    return {
        "reply": reply,
        "config_changed": False,
        "ok": ok,
        "error_kind": None if ok else "media_failed",
    }
