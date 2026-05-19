"""
device.py - Device control intent handling.
"""

from __future__ import annotations

import re
from typing import Any

from device_control import perform
from .tool_interface import IntentPlan, IntentResult


INTENT_NAME = "device"
TRIGGERS = [
    "set volume",
    "volume up",
    "volume down",
    "mute",
    "unmute",
    "set brightness",
    "increase brightness",
    "decrease brightness",
    "play pause",
    "pause music",
    "resume music",
    "next track",
    "previous track",
    "open",
    "launch",
    "start",
]
OLLAMA_DESCRIPTION = "Control device settings, media keys, brightness, volume, or open local apps"

APP_ALIASES = {
    "spotify",
    "terminal",
    "powershell",
    "cmd",
    "notepad",
    "calculator",
    "settings",
    "explorer",
    "vscode",
    "visual studio code",
    "chrome",
}


def match(text: str, lowered: str) -> IntentPlan | None:
    volume_match = re.search(r"(?:set )?volume(?: to)? (\d{1,3})", lowered)
    if volume_match:
        level = max(0, min(100, int(volume_match.group(1))))
        return {
            "intent": INTENT_NAME,
            "response_preview": f"Setting volume to {level} percent.",
            "action": {"mode": "set_volume", "level": level, "text": text},
        }

    if "mute" in lowered and "unmute" not in lowered:
        return {
            "intent": INTENT_NAME,
            "response_preview": "Muting audio.",
            "action": {"mode": "media_key", "key": "mute", "text": text},
        }
    if "unmute" in lowered:
        return {
            "intent": INTENT_NAME,
            "response_preview": "Toggling mute.",
            "action": {"mode": "media_key", "key": "mute", "text": text},
        }
    if "volume up" in lowered or "increase volume" in lowered:
        return {
            "intent": INTENT_NAME,
            "response_preview": "Turning the volume up.",
            "action": {"mode": "adjust_volume", "delta": 10, "text": text},
        }
    if "volume down" in lowered or "decrease volume" in lowered or "lower volume" in lowered:
        return {
            "intent": INTENT_NAME,
            "response_preview": "Turning the volume down.",
            "action": {"mode": "adjust_volume", "delta": -10, "text": text},
        }

    brightness_match = re.search(r"(?:set )?brightness(?: to)? (\d{1,3})", lowered)
    if brightness_match:
        level = max(0, min(100, int(brightness_match.group(1))))
        return {
            "intent": INTENT_NAME,
            "response_preview": f"Setting brightness to {level} percent.",
            "action": {"mode": "set_brightness", "level": level, "text": text},
        }
    if "increase brightness" in lowered:
        return {
            "intent": INTENT_NAME,
            "response_preview": "Increasing brightness.",
            "action": {"mode": "adjust_brightness", "delta": 10, "text": text},
        }
    if "decrease brightness" in lowered or "lower brightness" in lowered:
        return {
            "intent": INTENT_NAME,
            "response_preview": "Decreasing brightness.",
            "action": {"mode": "adjust_brightness", "delta": -10, "text": text},
        }

    if "play pause" in lowered or "pause music" in lowered or "resume music" in lowered:
        return {
            "intent": INTENT_NAME,
            "response_preview": "Toggling playback.",
            "action": {"mode": "media_key", "key": "play_pause", "text": text},
        }
    if "next track" in lowered or "skip track" in lowered:
        return {
            "intent": INTENT_NAME,
            "response_preview": "Skipping to the next track.",
            "action": {"mode": "media_key", "key": "next", "text": text},
        }
    if "previous track" in lowered or "last track" in lowered:
        return {
            "intent": INTENT_NAME,
            "response_preview": "Going back a track.",
            "action": {"mode": "media_key", "key": "prev", "text": text},
        }

    open_match = re.match(r"(?:open|launch|start) (.+)", lowered)
    if open_match:
        target = open_match.group(1).strip(" .")
        if target in APP_ALIASES:
            return {
                "intent": INTENT_NAME,
                "response_preview": f"Opening {target}.",
                "action": {"mode": "open_app", "app": target, "text": text},
            }

    return None


def execute(action: dict[str, Any], _config: dict[str, Any], context: dict[str, Any] | None = None) -> IntentResult:
    reply = perform(action)
    lowered = str(reply or "").lower()
    ok = not any(marker in lowered for marker in ("couldn't", "not installed", "not available yet", "don't have"))
    return {
        "reply": reply,
        "config_changed": False,
        "ok": ok,
        "error_kind": None if ok else "device_failed",
    }


def handle(action: dict[str, Any], _config: dict[str, Any], context: dict[str, Any] | None = None) -> IntentResult:
    return execute(action, _config, context)
