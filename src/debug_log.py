"""
debug_log.py - Lightweight structured debug logging for APRIL.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_PATH = LOG_DIR / "debug.jsonl"
_lock = Lock()


def log_event(event_type: str, **payload: Any) -> None:
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
        **payload,
    }
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with _lock:
            with LOG_PATH.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        return


def read_recent_events(limit: int = 20) -> list[dict[str, Any]]:
    if limit <= 0 or not LOG_PATH.exists():
        return []
    try:
        with _lock:
            lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    events = []
    for line in lines[-limit:]:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def summarize_recent_activity(limit: int = 12) -> str:
    events = read_recent_events(limit=limit)
    if not events:
        return "I don't have any recent activity logged yet."

    lines: list[str] = []
    for event in events:
        summary = _summarize_event(event)
        if summary:
            lines.append(summary)

    if not lines:
        return (
            "I have recent events, but none of them are in a user-friendly format yet."
        )
    return "\n".join(lines[-limit:])


def latest_event_value(event_type: str, key: str, limit: int = 40) -> str:
    for event in reversed(read_recent_events(limit=limit)):
        if str(event.get("event", "") or "").strip() != event_type:
            continue
        value = str(event.get(key, "") or "").strip()
        if value:
            return value
    return ""


def _summarize_event(event: dict[str, Any]) -> str:
    event_type = str(event.get("event", "") or "").strip()
    if not event_type:
        return ""

    timestamp = _format_timestamp(str(event.get("ts", "") or "").strip())
    prefix = f"[{timestamp}] " if timestamp else ""

    if event_type == "request_begin":
        source = str(event.get("source", "") or "").strip() or "unknown"
        request_id = event.get("request_id")
        request_suffix = f" #{request_id}" if request_id is not None else ""
        return f"{prefix}Request started from {source}{request_suffix}."
    if event_type == "audio_captured":
        duration = event.get("duration")
        size_kb = event.get("size_kb")
        parts = []
        if duration is not None:
            parts.append(f"{float(duration):.1f}s")
        if size_kb is not None:
            parts.append(f"{float(size_kb):.1f} KiB")
        detail = ", ".join(parts) if parts else "audio"
        return f"{prefix}Captured {detail}."
    if event_type == "transcript":
        transcript = str(event.get("transcript", "") or "").strip()
        return f"{prefix}Heard: {transcript}" if transcript else ""
    if event_type == "intent_plan":
        intent = str(event.get("intent", "") or "").strip() or "unknown"
        return f"{prefix}Planned intent: {intent}."
    if event_type == "action_result":
        intent = str(event.get("intent", "") or "").strip() or "unknown"
        ok = event.get("ok")
        status = "completed" if ok is not False else "failed"
        reply = str(event.get("reply", "") or "").strip()
        if reply:
            return f"{prefix}{intent.capitalize()} action {status}: {reply}"
        return f"{prefix}{intent.capitalize()} action {status}."
    if event_type == "assistant_response":
        response = str(event.get("response", "") or "").strip()
        return f"{prefix}Reply: {response}" if response else ""
    if event_type == "transcription_unavailable":
        return f"{prefix}Transcription was unavailable."
    if event_type == "response_discarded":
        return f"{prefix}Discarded an outdated response."
    return f"{prefix}{event_type.replace('_', ' ')}."


def _format_timestamp(raw: str) -> str:
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return ""
    return dt.astimezone().strftime("%I:%M:%S %p").lstrip("0")
