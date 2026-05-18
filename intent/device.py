"""
device.py - Device control intent handling.
"""

from __future__ import annotations

from typing import Any

from device_control import perform


def handle(action: dict[str, Any], _config: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    reply = perform(action)
    lowered = str(reply or "").lower()
    ok = not any(marker in lowered for marker in ("couldn't", "not installed", "not available yet", "don't have"))
    return {
        "reply": reply,
        "config_changed": False,
        "ok": ok,
        "error_kind": None if ok else "device_failed",
    }
