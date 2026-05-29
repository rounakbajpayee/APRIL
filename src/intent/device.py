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
    "pause media",
    "resume media",
    "play media",
    "next track",
    "previous track",
    "open",
    "launch",
    "start",
]
OLLAMA_DESCRIPTION = (
    "Control device settings, media keys, brightness, volume, or open local apps"
)
EXAMPLES = [
    {
        "text": "set volume to 40",
        "response_preview": "Setting volume to 40 percent.",
        "action": {"mode": "set_volume", "level": 40},
    },
    {
        "text": "volume up",
        "response_preview": "Turning the volume up.",
        "action": {"mode": "adjust_volume", "delta": 10},
    },
    {
        "text": "mute audio",
        "response_preview": "Muting audio.",
        "action": {"mode": "media_key", "key": "mute"},
    },
    {
        "text": "increase brightness",
        "response_preview": "Increasing brightness.",
        "action": {"mode": "adjust_brightness", "delta": 10},
    },
    {
        "text": "open notepad",
        "response_preview": "Opening notepad.",
        "action": {"mode": "open_app", "app": "notepad"},
    },
    {
        "text": "bring up spotify",
        "response_preview": "Opening spotify.",
        "action": {"mode": "open_app", "app": "spotify"},
    },
    {
        "text": "pause media",
        "response_preview": "Toggling playback.",
        "action": {"mode": "media_key", "key": "play_pause"},
    },
]

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
    if (
        "volume down" in lowered
        or "decrease volume" in lowered
        or "lower volume" in lowered
    ):
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

    if (
        "play pause" in lowered
        or "pause music" in lowered
        or "resume music" in lowered
        or "pause media" in lowered
        or "resume media" in lowered
    ):
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

    open_match = re.match(
        r"(?:open|launch|start|pull up|bring up|open up) (.+)", lowered
    )
    if open_match:
        target = open_match.group(1).strip(" .")
        if target in APP_ALIASES:
            return {
                "intent": INTENT_NAME,
                "response_preview": f"Opening {target}.",
                "action": {"mode": "open_app", "app": target, "text": text},
            }

    return None


def execute(
    action: dict[str, Any],
    _config: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> IntentResult:
    try:
        reply = perform(action)
    except Exception as exc:
        import runtime_trace

        runtime_trace.trace_event(
            "device_execute_error",
            subsystem="intent.device",
            severity=runtime_trace.ERROR,
            payload={"error": str(exc), "action": str(action.get("mode", ""))},
        )
        return {
            "reply": f"Device control failed: {exc}",
            "config_changed": False,
            "ok": False,
            "error_kind": "device_error",
        }
    lowered = str(reply or "").lower()
    ok = not any(
        marker in lowered
        for marker in ("couldn't", "not installed", "not available yet", "don't have")
    )
    return {
        "reply": reply,
        "config_changed": False,
        "ok": ok,
        "error_kind": None if ok else "device_failed",
    }


def handle(
    action: dict[str, Any],
    _config: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> IntentResult:
    return execute(action, _config, context)
