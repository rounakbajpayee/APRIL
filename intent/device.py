"""
device.py - Device control intent handling.
"""

from __future__ import annotations

from typing import Any

from device_control import perform


def handle(action: dict[str, Any], _config: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"reply": perform(action), "config_changed": False}
