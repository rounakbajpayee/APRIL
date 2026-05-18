"""
config_intent.py - Voice/text config changes for APRIL.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from learning import remember_phrase
from session_manager import handle_home_change, hide_all_panes, show_all_panes


BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = BASE_DIR / "config.json"
DEFAULT_PATH = BASE_DIR / "config_defaults.json"


def handle(action: dict[str, Any], config: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    context = context or {}
    mode = str(action.get("mode", "") or "").strip().lower()
    if mode == "teach_phrase":
        heard = str(action.get("heard", "") or "").strip()
        means = str(action.get("means", "") or "").strip()
        if not heard or not means:
            return {"reply": "I need both the phrase you said and what it should mean.", "config_changed": False}
        remember_phrase(heard, means)
        return {
            "reply": f"Got it. When you say {heard}, I'll treat it as {means}.",
            "config_changed": False,
            "updates": {},
        }

    updates = action.get("updates")
    if not isinstance(updates, dict) or not updates:
        return {
            "reply": "I understood that as a config request, but there was nothing to change.",
            "config_changed": False,
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
            except Exception:
                pass

    fragments = [f"{key} set to {value}" for key, value in updates.items()]
    reply = "Done. " + ", ".join(fragments) + "."
    return {"reply": reply, "config_changed": True, "updates": updates}


def _write_user_overrides(merged: dict[str, Any]) -> None:
    defaults = _load_defaults()
    overrides = {}
    for key, value in merged.items():
        if key not in defaults or defaults.get(key) != value:
            overrides[key] = value
    CONFIG_PATH.write_text(json.dumps(overrides, indent=2), encoding="utf-8")


def _load_defaults() -> dict[str, Any]:
    try:
        payload = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}
