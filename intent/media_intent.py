"""
media_intent.py - Media handling for APRIL phase 1.
"""

from __future__ import annotations

from typing import Any

from media import handle_media


def handle(action: dict[str, Any], config: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"reply": handle_media(action, config), "config_changed": False}
