"""
config_intent.py - Voice/text config changes for APRIL.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from learning import remember_phrase
from session_manager import handle_home_change, hide_all_panes, show_all_panes

from .tool_interface import IntentPlan, IntentResult


BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = BASE_DIR / "config.json"
DEFAULT_PATH = BASE_DIR / "config_defaults.json"

INTENT_NAME = "config"
TRIGGERS = [
    "turn off voice",
    "turn on voice",
    "away mode",
    "show terminal",
    "hide terminal",
    "switch to sapi",
    "switch to say",
    "switch to auto voice",
    "switch to wsl voice",
    "learn that",
    "remember that",
    "when i say",
]
OLLAMA_DESCRIPTION = "Update APRIL configuration, voice settings, or teach phrase rewrites"
EXAMPLES = [
    {
        "text": "turn off voice",
        "response_preview": "Turning voice off.",
        "action": {"updates": {"voice": False}},
    },
    {
        "text": "turn on voice",
        "response_preview": "Turning voice on.",
        "action": {"updates": {"voice": True}},
    },
    {
        "text": "show terminal",
        "response_preview": "Showing terminal panes.",
        "action": {"updates": {"terminal_visible": True}},
    },
    {
        "text": "hide terminal",
        "response_preview": "Hiding terminal panes.",
        "action": {"updates": {"terminal_visible": False}},
    },
    {
        "text": "switch to auto voice",
        "response_preview": "Switching voice routing to auto.",
        "action": {"updates": {"tts_engine": "auto"}},
    },
    {
        "text": "switch to say",
        "response_preview": "Switching to say.",
        "action": {"updates": {"tts_engine": "say"}},
    },
    {
        "text": "learn that movie time means open jellyfin",
        "response_preview": "I'll remember that phrasing.",
        "action": {"mode": "teach_phrase", "heard": "movie time", "means": "open jellyfin"},
    },
]


def match(text: str, lowered: str) -> IntentPlan | None:
    teach_match = re.match(r"(?:learn that|remember that)\s+(.+?)\s+means\s+(.+)", text, re.IGNORECASE)
    if not teach_match:
        teach_match = re.match(r"when i say\s+(.+?),?\s+(?:do|mean)\s+(.+)", text, re.IGNORECASE)
    if teach_match:
        heard = teach_match.group(1).strip(" .")
        means = teach_match.group(2).strip(" .")
        if heard and means:
            return {
                "intent": INTENT_NAME,
                "response_preview": "I'll remember that phrasing.",
                "action": {
                    "mode": "teach_phrase",
                    "heard": heard,
                    "means": means,
                    "text": text,
                },
            }

    updates: dict[str, Any] = {}
    preview = ""

    if any(phrase in lowered for phrase in ("turn off voice", "disable voice", "mute yourself", "stop talking")):
        updates["voice"] = False
        preview = "Turning voice off."
    elif any(phrase in lowered for phrase in ("turn on voice", "enable voice", "use voice again", "speak again")):
        updates["voice"] = True
        preview = "Turning voice on."

    if any(phrase in lowered for phrase in ("i'm leaving home", "i am leaving home", "away mode", "not at home")):
        updates["at_home"] = False
        preview = preview or "Switching to away mode."
    elif any(phrase in lowered for phrase in ("i'm home", "i am home", "back home")):
        updates["at_home"] = True
        preview = preview or "Switching to home mode."

    if any(phrase in lowered for phrase in ("show terminal", "show the terminal")):
        updates["terminal_visible"] = True
        preview = preview or "Showing terminal panes."
    elif any(phrase in lowered for phrase in ("hide terminal", "hide the terminal")):
        updates["terminal_visible"] = False
        preview = preview or "Hiding terminal panes."

    if "switch to sapi" in lowered or "use sapi" in lowered:
        updates["tts_engine"] = "sapi"
        preview = preview or "Switching to SAPI voice."
    elif "switch to say" in lowered or "use say" in lowered:
        updates["tts_engine"] = "say"
        preview = preview or "Switching to mac say."
    elif "switch to auto voice" in lowered or "use auto voice" in lowered or "switch to auto" in lowered:
        updates["tts_engine"] = "auto"
        preview = preview or "Switching voice routing to auto."
    elif "switch to wsl voice" in lowered or "use espeak" in lowered:
        updates["tts_engine"] = "espeak"
        preview = preview or "Switching to eSpeak."

    if not updates:
        return None

    return {
        "intent": INTENT_NAME,
        "response_preview": preview,
        "action": {
            "updates": updates,
            "text": text,
        },
    }


def execute(action: dict[str, Any], config: dict[str, Any], context: dict[str, Any] | None = None) -> IntentResult:
    context = context or {}
    mode = str(action.get("mode", "") or "").strip().lower()
    if mode == "teach_phrase":
        heard = str(action.get("heard", "") or "").strip()
        means = str(action.get("means", "") or "").strip()
        if not heard or not means:
            return {
                "reply": "I need both the phrase you said and what it should mean.",
                "config_changed": False,
                "ok": False,
                "error_kind": "config_phrase_missing",
            }
        remember_phrase(heard, means)
        return {
            "reply": f"Got it. When you say {heard}, I'll treat it as {means}.",
            "config_changed": False,
            "ok": True,
            "error_kind": None,
            "updates": {},
        }

    updates = action.get("updates")
    if not isinstance(updates, dict) or not updates:
        return {
            "reply": "I understood that as a config request, but there was nothing to change.",
            "config_changed": False,
            "ok": False,
            "error_kind": "config_updates_missing",
            "updates": {},
        }

    merged = dict(config)
    merged.update(updates)
    _write_user_overrides(merged)

    for key, value in updates.items():
        if key == "at_home":
            handle_home_change(bool(value))
        elif key == "terminal_visible":
            show_all_panes() if value else hide_all_panes()

    callback = context.get("config_callback")
    if callable(callback):
        for key, value in updates.items():
            try:
                callback(key, value)
            except Exception as exc:
                import runtime_trace
                runtime_trace.trace_event(
                    "config_callback_error",
                    subsystem="intent.config",
                    severity=runtime_trace.WARNING,
                    payload={"key": key, "error": str(exc)},
                )

    fragments = [f"{key} set to {value}" for key, value in updates.items()]
    reply = "Done. " + ", ".join(fragments) + "."
    return {"reply": reply, "config_changed": True, "ok": True, "error_kind": None, "updates": updates}


def handle(action: dict[str, Any], config: dict[str, Any], context: dict[str, Any] | None = None) -> IntentResult:
    return execute(action, config, context)


def _write_user_overrides(merged: dict[str, Any]) -> None:
    defaults = _load_defaults()
    overrides = {}
    for key, value in merged.items():
        if key not in defaults or defaults.get(key) != value:
            overrides[key] = value
    try:
        CONFIG_PATH.write_text(json.dumps(overrides, indent=2), encoding="utf-8")
    except OSError as exc:
        import runtime_trace
        runtime_trace.trace_event(
            "config_write_error",
            subsystem="intent.config",
            severity=runtime_trace.ERROR,
            payload={"error": str(exc)},
        )


def _load_defaults() -> dict[str, Any]:
    try:
        payload = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        import runtime_trace
        runtime_trace.trace_event(
            "config_defaults_load_error",
            subsystem="intent.config",
            severity=runtime_trace.WARNING,
            payload={"error": str(exc)},
        )
        return {}
    return payload if isinstance(payload, dict) else {}
