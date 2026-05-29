"""
state_engine.py - Minimal projection and prompt-safe context builder for APRIL.

This is intentionally simple:
- replay the event ledger
- build small state snapshots
- expose a prompt/context summary that the current MVP can already use
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from event_ledger import STATE_DIR, read_events, recent_prompt_safe_events

SNAPSHOT_PATH = STATE_DIR / "context_snapshot.json"
APRIL_STATE_PATH = STATE_DIR / "april_state.json"
DESKTOP_STATE_PATH = STATE_DIR / "desktop_state.json"


def refresh_state_snapshot(config: dict[str, Any] | None = None) -> dict[str, Any]:
    events = read_events()
    snapshot = build_context_snapshot(events, config=config)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    APRIL_STATE_PATH.write_text(
        json.dumps(snapshot.get("april_state", {}), indent=2), encoding="utf-8"
    )
    DESKTOP_STATE_PATH.write_text(
        json.dumps(snapshot.get("desktop_state", {}), indent=2), encoding="utf-8"
    )
    return snapshot


def load_snapshot() -> dict[str, Any]:
    try:
        payload = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def build_context_snapshot(
    events: list[dict[str, Any]], config: dict[str, Any] | None = None
) -> dict[str, Any]:
    recent_timeline: list[dict[str, Any]] = []
    recent_transcripts: list[str] = []
    recent_replies: list[str] = []
    recent_intents: list[str] = []
    open_loops: list[str] = []
    current_request: dict[str, Any] | None = None
    current_status = "idle"
    active_window = ""
    active_app = ""
    started_at = ""
    last_config_change: dict[str, Any] | None = None

    for event in events:
        event_type = str(event.get("event_type", "") or "").strip()
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        timestamp = str(event.get("ts", "") or "").strip()
        request_id = payload.get("request_id")

        if event_type == "april_started":
            started_at = started_at or timestamp
            current_status = "idle"
        elif event_type == "request_started":
            trigger_kind = str(payload.get("trigger_kind", "") or "").strip()
            current_status = (
                "dictating" if trigger_kind == "voice_dictation" else "listening"
            )
            current_request = {
                "request_id": payload.get("request_id"),
                "source": payload.get("source", ""),
                "trigger_kind": trigger_kind,
                "text": payload.get("text", ""),
                "ts": timestamp,
            }
        elif event_type == "audio_captured":
            current_status = (
                "dictating"
                if payload.get("trigger_kind") == "voice_dictation"
                else "transcribing"
            )
        elif event_type == "transcript_received":
            transcript = str(payload.get("transcript", "") or "").strip()
            if transcript:
                recent_transcripts.append(transcript)
            if (
                current_request
                and request_id == current_request.get("request_id")
                and transcript
            ):
                current_request["text"] = transcript
            current_status = "reasoning"
        elif event_type == "transcript_unavailable":
            current_status = "error"
            open_loops.append("Transcription was unavailable.")
            if current_request and request_id == current_request.get("request_id"):
                current_request["failed"] = "transcript_unavailable"
                current_request = None
        elif event_type == "intent_planned":
            intent = str(payload.get("intent", "") or "").strip()
            if intent:
                recent_intents.append(intent)
            if current_request and request_id == current_request.get("request_id"):
                current_request["intent"] = intent
                if payload.get("text"):
                    current_request["text"] = payload.get("text")
            current_status = "acting"
        elif event_type == "action_completed":
            current_status = "speaking"
            if current_request and payload.get("request_id") == current_request.get(
                "request_id"
            ):
                current_request["intent"] = payload.get("intent", "")
        elif event_type == "action_failed":
            current_status = "error"
            detail = str(
                payload.get("reply", "") or payload.get("error", "") or ""
            ).strip()
            if detail:
                open_loops.append(detail)
            if current_request and request_id == current_request.get("request_id"):
                current_request["failed"] = detail or "action_failed"
                current_request = None
        elif event_type == "request_interrupted":
            current_status = "idle"
            if current_request and request_id == current_request.get("request_id"):
                current_request = None
            open_loops.append("A request was interrupted by a newer request.")
        elif event_type == "assistant_replied":
            current_status = "idle"
            reply = str(payload.get("response", "") or "").strip()
            if reply:
                if not recent_replies or recent_replies[-1] != reply:
                    recent_replies.append(reply)
            if current_request and request_id == current_request.get("request_id"):
                current_request = None
        elif event_type == "action_validated":
            verdict = str(payload.get("verdict", "") or "").strip()
            detail = str(
                payload.get("detail", "") or payload.get("notes", "") or ""
            ).strip()
            if current_request and request_id == current_request.get("request_id"):
                current_request["validation"] = verdict
            if verdict and verdict not in {"auto_pass", "confirmed_correct"} and detail:
                open_loops.append(f"Validation flagged {verdict}: {detail}")
        elif event_type == "response_discarded":
            if current_request and request_id == current_request.get("request_id"):
                current_request = None
        elif event_type == "config_changed":
            last_config_change = {
                "ts": timestamp,
                "updates": payload.get("updates", {}),
            }
        elif event_type == "desktop_observed":
            foreground = (
                payload.get("foreground")
                if isinstance(payload.get("foreground"), dict)
                else {}
            )
            active_window = str(
                foreground.get("window_title", "") or active_window
            ).strip()
            active_app = str(foreground.get("app_hint", "") or active_app).strip()

        summary = _event_summary(event)
        if summary:
            recent_timeline.append({"ts": timestamp, "summary": summary})

    snapshot = {
        "identity": {
            "assistant": "APRIL",
            "host_os": (config or {}).get(
                "host_os", "windows" if Path.cwd().drive else "local"
            ),
        },
        "current_state": {
            "voice_enabled": bool((config or {}).get("voice", True)),
            "at_home": bool((config or {}).get("at_home", True)),
            "tts_engine": str((config or {}).get("tts_engine", "auto") or "auto"),
            "status": current_status,
            "active_window": active_window,
            "active_app": active_app,
            "active_request": current_request,
        },
        "recent_timeline": recent_timeline[-15:],
        "active_entities": [entity for entity in [current_request] if entity],
        "open_loops": open_loops[-10:],
        "domain_summaries": {
            "april": {
                "started_at": started_at,
                "recent_transcripts": recent_transcripts[-5:],
                "recent_replies": recent_replies[-5:],
                "recent_intents": recent_intents[-5:],
                "last_config_change": last_config_change,
            },
            "desktop": {
                "active_window": active_window,
                "active_app": active_app,
            },
        },
        "safety_and_sensitivity": {
            "contains_sensitive_context": any(
                str(event.get("sensitivity", "") or "").strip() not in {"", "low"}
                for event in recent_prompt_safe_events(limit=20)
            ),
        },
        "april_state": {
            "status": current_status,
            "recent_transcripts": recent_transcripts[-5:],
            "recent_replies": recent_replies[-5:],
            "recent_intents": recent_intents[-5:],
            "open_loops": open_loops[-10:],
        },
        "desktop_state": {
            "active_window": active_window,
            "active_app": active_app,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    return snapshot


def get_prompt_context_summary(limit: int = 8) -> str:
    snapshot = load_snapshot()
    if not snapshot:
        snapshot = refresh_state_snapshot()
    if not snapshot:
        return ""

    current_state = snapshot.get("current_state", {})
    timeline = snapshot.get("recent_timeline", [])
    open_loops = snapshot.get("open_loops", [])

    lines = [
        "APRIL runtime context:",
        f"- status: {current_state.get('status', 'unknown')}",
        f"- voice_enabled: {current_state.get('voice_enabled', True)}",
        f"- at_home: {current_state.get('at_home', True)}",
    ]
    active_app = str(current_state.get("active_app", "") or "").strip()
    active_window = str(current_state.get("active_window", "") or "").strip()
    if active_app or active_window:
        lines.append(
            f"- foreground: {active_app or active_window} | {active_window or active_app}"
        )

    active_request = current_state.get("active_request")
    if isinstance(active_request, dict) and active_request:
        lines.append(f"- active_request_source: {active_request.get('source', '')}")
        if active_request.get("text"):
            lines.append(f"- active_request_text: {active_request.get('text')}")

    if timeline:
        lines.append("Recent timeline:")
        for item in timeline[-limit:]:
            summary = str(item.get("summary", "") or "").strip()
            if summary:
                lines.append(f"- {summary}")

    if open_loops:
        lines.append("Open loops:")
        for item in open_loops[-5:]:
            lines.append(f"- {item}")

    return "\n".join(lines).strip()


def get_widget_snapshot_lines(limit: int = 6) -> list[tuple[str, str]]:
    snapshot = load_snapshot()
    if not snapshot:
        snapshot = refresh_state_snapshot()
    if not snapshot:
        return []

    lines: list[tuple[str, str]] = []
    current_state = (
        snapshot.get("current_state", {}) if isinstance(snapshot, dict) else {}
    )
    status = str(current_state.get("status", "") or "").strip()
    active_app = str(current_state.get("active_app", "") or "").strip()
    active_window = str(current_state.get("active_window", "") or "").strip()
    timeline = snapshot.get("recent_timeline", []) if isinstance(snapshot, dict) else []
    open_loops = snapshot.get("open_loops", []) if isinstance(snapshot, dict) else []

    if status:
        lines.append(("system", f"State: {status}"))
    if active_app or active_window:
        lines.append(("system", f"Focus: {active_app or active_window}"))
    for item in timeline[-limit:]:
        if not isinstance(item, dict):
            continue
        summary = str(item.get("summary", "") or "").strip()
        if summary:
            lines.append(("system", summary))
    for item in open_loops[-3:]:
        lines.append(("system", f"Open loop: {item}"))

    deduped: list[tuple[str, str]] = []
    seen = set()
    for role, text in lines:
        key = (role, text)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((role, text))
    return deduped[-max(limit + 2, 4) :]


def get_widget_snapshot_data(limit: int = 6) -> dict[str, Any]:
    snapshot = load_snapshot()
    if not snapshot:
        snapshot = refresh_state_snapshot()
    if not snapshot:
        return {}

    current_state = (
        snapshot.get("current_state", {}) if isinstance(snapshot, dict) else {}
    )
    domain_summaries = (
        snapshot.get("domain_summaries", {}) if isinstance(snapshot, dict) else {}
    )
    april_summary = (
        domain_summaries.get("april", {}) if isinstance(domain_summaries, dict) else {}
    )
    timeline = snapshot.get("recent_timeline", []) if isinstance(snapshot, dict) else []
    open_loops = snapshot.get("open_loops", []) if isinstance(snapshot, dict) else []

    recent_transcripts = (
        april_summary.get("recent_transcripts", [])
        if isinstance(april_summary, dict)
        else []
    )
    recent_replies = (
        april_summary.get("recent_replies", [])
        if isinstance(april_summary, dict)
        else []
    )

    return {
        "status": str(current_state.get("status", "") or "").strip() or "unknown",
        "focus": str(
            current_state.get("active_app", "")
            or current_state.get("active_window", "")
            or ""
        ).strip(),
        "active_window": str(current_state.get("active_window", "") or "").strip(),
        "last_transcript": str(
            recent_transcripts[-1] if recent_transcripts else ""
        ).strip(),
        "last_reply": str(recent_replies[-1] if recent_replies else "").strip(),
        "open_loops": [
            str(item).strip() for item in open_loops[-3:] if str(item).strip()
        ],
        "timeline": [
            str(item.get("summary", "") or "").strip()
            for item in timeline[-limit:]
            if isinstance(item, dict) and str(item.get("summary", "") or "").strip()
        ],
    }


def _event_summary(event: dict[str, Any]) -> str:
    event_type = str(event.get("event_type", "") or "").strip()
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}

    if event_type == "april_started":
        return "APRIL started."
    if event_type == "request_started":
        source = str(payload.get("source", "") or "").strip() or "unknown"
        trigger_kind = str(payload.get("trigger_kind", "") or "").strip()
        if trigger_kind:
            return f"Request started from {source} via {trigger_kind}."
        return f"Request started from {source}."
    if event_type == "desktop_observed":
        title = str(
            (payload.get("foreground") or {}).get("window_title", "") or ""
        ).strip()
        return f"Observed foreground window: {title}" if title else ""
    if event_type == "transcript_received":
        transcript = str(payload.get("transcript", "") or "").strip()
        return f"Heard: {transcript}" if transcript else ""
    if event_type == "intent_planned":
        intent = str(payload.get("intent", "") or "").strip()
        return f"Planned {intent} action." if intent else ""
    if event_type == "action_completed":
        reply = str(payload.get("reply", "") or "").strip()
        return f"Action completed: {reply}" if reply else "Action completed."
    if event_type == "action_failed":
        reply = str(payload.get("reply", "") or payload.get("error", "") or "").strip()
        return f"Action failed: {reply}" if reply else "Action failed."
    if event_type == "request_interrupted":
        return "Request interrupted by a newer request."
    if event_type == "assistant_replied":
        response = str(payload.get("response", "") or "").strip()
        return f"Replied: {response}" if response else ""
    if event_type == "action_validated":
        verdict = str(payload.get("verdict", "") or "").strip()
        detail = str(
            payload.get("detail", "") or payload.get("notes", "") or ""
        ).strip()
        if verdict and detail:
            return f"Validation: {verdict} ({detail})."
        if verdict:
            return f"Validation: {verdict}."
        return ""
    if event_type == "response_discarded":
        return "Discarded an outdated response."
    if event_type == "semantic_example_recorded":
        kind = str(payload.get("kind", "") or "").strip()
        intent = str(payload.get("resolved_intent", "") or "").strip()
        if kind and intent:
            return f"Stored semantic example for {kind} -> {intent}."
        if kind:
            return f"Stored semantic example for {kind}."
        return "Stored semantic example."
    if event_type == "config_changed":
        updates = payload.get("updates", {})
        if isinstance(updates, dict) and updates:
            fragment = ", ".join(f"{key}={value}" for key, value in updates.items())
            return f"Config changed: {fragment}"
    return ""
