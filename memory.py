"""
memory.py - Lightweight persistent recent-memory store for APRIL.
"""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
MEMORY_PATH = BASE_DIR / "memory.json"
_lock = Lock()
MAX_TURNS = 20


def append_turn(user_text: str, assistant_text: str, source: str = "text") -> None:
    user_clean = " ".join(str(user_text).strip().split())
    assistant_clean = " ".join(str(assistant_text).strip().split())
    if not user_clean or not assistant_clean:
        return

    with _lock:
        payload = _load_unlocked()
        turns = payload.get("turns")
        if not isinstance(turns, list):
            turns = []
        turns.append(
            {
                "user": user_clean,
                "assistant": assistant_clean,
                "source": source,
            }
        )
        payload["turns"] = turns[-MAX_TURNS:]
        MEMORY_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def recent_turns(limit: int = 6) -> list[dict[str, str]]:
    if limit <= 0:
        return []
    with _lock:
        payload = _load_unlocked()
    turns = payload.get("turns")
    if not isinstance(turns, list):
        return []
    result: list[dict[str, str]] = []
    for item in turns[-limit:]:
        if not isinstance(item, dict):
            continue
        user = " ".join(str(item.get("user", "") or "").strip().split())
        assistant = " ".join(str(item.get("assistant", "") or "").strip().split())
        source = " ".join(str(item.get("source", "") or "").strip().split()) or "text"
        if user and assistant:
            result.append({"user": user, "assistant": assistant, "source": source})
    return result


def summarize_recent(limit: int = 6) -> str:
    turns = recent_turns(limit=limit)
    if not turns:
        return ""
    lines = []
    for item in turns:
        lines.append(f"User: {item['user']}")
        lines.append(f"APRIL: {item['assistant']}")
    return "\n".join(lines)


def _load_unlocked() -> dict[str, Any]:
    try:
        payload = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"turns": []}
    if not isinstance(payload, dict):
        return {"turns": []}
    return payload
