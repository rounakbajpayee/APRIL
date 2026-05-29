"""
event_ledger.py - Minimal canonical event ledger for APRIL.

This is the first thin slice of the vNext stateful architecture:
- append-only JSONL event storage
- stable top-level event shape
- prompt-safe helpers for recent timeline reads
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

BASE_DIR = Path(__file__).resolve().parent
STATE_DIR = BASE_DIR / "state"
LEDGER_PATH = STATE_DIR / "events.jsonl"
SCHEMA_VERSION = 1
_lock = Lock()


def append_event(
    event_type: str,
    *,
    source: str = "april",
    domain: str = "april",
    state: str = "observed",
    entity_id: str | None = None,
    sensitivity: str = "low",
    prompt_safe: bool = True,
    retention_class: str = "default",
    birth_ts: str | None = None,
    age_hint_seconds: int = 0,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = {
        "id": f"evt_{uuid4().hex}",
        "schema_version": SCHEMA_VERSION,
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "domain": domain,
        "event_type": event_type,
        "entity_id": entity_id or "",
        "state": state,
        "sensitivity": sensitivity,
        "prompt_safe": bool(prompt_safe),
        "retention_class": retention_class,
        "birth_ts": birth_ts,
        "age_hint_seconds": int(age_hint_seconds or 0),
        "payload": payload or {},
    }
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with _lock:
        with LEDGER_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def read_events(limit: int | None = None) -> list[dict[str, Any]]:
    if not LEDGER_PATH.exists():
        return []
    try:
        with _lock:
            lines = LEDGER_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    if limit is not None and limit > 0:
        lines = lines[-limit:]

    events: list[dict[str, Any]] = []
    for line in lines:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def recent_prompt_safe_events(limit: int = 20) -> list[dict[str, Any]]:
    safe_events: list[dict[str, Any]] = []
    for event in reversed(read_events(limit=max(limit * 3, limit))):
        if not bool(event.get("prompt_safe", False)):
            continue
        safe_events.append(event)
        if len(safe_events) >= limit:
            break
    safe_events.reverse()
    return safe_events
