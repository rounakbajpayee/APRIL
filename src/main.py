"""
main.py - APRIL entry point.
"""

import ctypes
import hashlib
import json
import os
import sys
import threading
import traceback
from uuid import uuid4

import runtime_trace
from brain import process as plan_with_brain
from debug_log import log_event
from event_ledger import append_event
from intent import execute_plan
from memory import append_turn
from observer import collect_runtime_observation
from semantic_store import record_semantic_example
from state_engine import refresh_state_snapshot
from stt import transcribe_with_metadata
from tts import speak as speak_reply
from tts import stop as stop_speaking

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
DEFAULT_PATH = os.path.join(BASE_DIR, "config_defaults.json")
TRACE_PATH = os.path.join(BASE_DIR, "logs", "startup_trace.log")
_request_lock = threading.Lock()
_latest_request_id = 0
_bridge_ref = None  # APRILBridge | None
_session_id = uuid4().hex
_system_prompt_hash = ""
_input_handler_ref = None


def _format_request_id(request_id: int) -> str:
    """Format an integer request counter as a human-readable REQ-NNNN string.

    Phase 2B: canonical request_id format for trace correlation.
    Human-debuggable; not globally unique across restarts.
    Example: 1 -> 'REQ-0001'
    """
    return f"REQ-{request_id:04d}"


def _normalize_trigger_kind(
    trigger_kind: str | None, *, is_dictation: bool = False
) -> str:
    candidate = str(trigger_kind or "").strip().lower()
    if candidate in {"voice_command", "voice_dictation"}:
        return candidate
    return "voice_dictation" if is_dictation else "voice_command"


def _routing_provenance(plan: dict[str, object]) -> dict[str, object]:
    routing = plan.get("_routing") if isinstance(plan.get("_routing"), dict) else {}
    return {
        "planner_source": str(routing.get("planner_source", "") or "unknown").strip()
        or "unknown",
        "planner_reason": str(routing.get("planner_reason", "") or "").strip(),
        "tool": str(routing.get("tool", "") or "").strip(),
        "confidence_threshold": routing.get("confidence_threshold"),
        "semantic": (
            plan.get("_semantic") if isinstance(plan.get("_semantic"), dict) else None
        ),
        "raw_plan": (
            routing.get("raw_plan")
            if isinstance(routing.get("raw_plan"), dict)
            else None
        ),
    }


def _classify_action_validation(
    *,
    trigger_kind: str,
    planner_source: str,
    plan: dict[str, object],
    result: dict[str, object],
) -> tuple[str, str]:
    ok = bool(result.get("ok", False))
    error_kind = str(result.get("error_kind", "") or "").strip()
    reply = str(result.get("reply", "") or "").strip().lower()
    if trigger_kind == "voice_dictation":
        return "routing_misfire", "dictation_trigger_reached_command_router"
    if ok:
        return "auto_pass", "action_completed_without_runtime_error"
    if planner_source in {
        "llm_intent_plan",
        "semantic_store_replay",
        "registry_semantic_match",
    }:
        if "couldn't map" in reply or "cannot map" in reply:
            return "misroute_intent", "planner_selected_unexecutable_action"
        return "wrong_action", f"planner_source={planner_source}"
    if error_kind:
        return "execution_failed", error_kind
    if not isinstance(plan.get("action"), dict) or not plan.get("action"):
        return "not_intended", "missing_action_payload"
    return "wrong_action", "execution_failed_without_specific_classifier"


def record_action_validation(
    request_id: int,
    verdict: str,
    *,
    notes: str = "",
    source: str = "user",
    config: dict | None = None,
) -> None:
    record_state_event(
        "action_validated",
        source=source,
        state="observed",
        entity_id=f"request_{request_id}",
        payload={
            "request_id": request_id,
            "verdict": str(verdict or "").strip(),
            "notes": str(notes or "").strip(),
        },
        config=config or load_config(),
    )


_job_id_lock = threading.Lock()
_job_id_counter = 0


def _format_job_id(subsystem: str) -> str:
    """Generate a human-readable job_id for one async pipeline subtask.

    Phase 2C: explicit job_id generation at each async boundary.
    Symmetric with _format_request_id — same owner (main.py), same lifetime.
    Format: SUBSYSTEM-NNNN  e.g. 'STT-0001', 'BRAIN-0001', 'TTS-0001'
    Thread-safe; resets on process restart by design.
    """
    global _job_id_counter
    with _job_id_lock:
        _job_id_counter += 1
        return f"{subsystem.upper()}-{_job_id_counter:04d}"


_single_instance_handle = None
_SINGLE_INSTANCE_NAME = "Local\\APRILDesktopSingleton"


def trace_startup(message: str) -> None:
    runtime_trace.trace_marker(f"[main] {message}")


def load_config() -> dict:
    config = {}
    if os.path.exists(DEFAULT_PATH):
        try:
            with open(DEFAULT_PATH, encoding="utf-8") as f:
                config.update(json.load(f))
        except (json.JSONDecodeError, OSError) as exc:
            runtime_trace.trace_event(
                "config_load_error",
                subsystem="config",
                severity=runtime_trace.WARNING,
                payload={"file": "config_defaults.json", "error": str(exc)},
            )
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                config.update(json.load(f))
        except (json.JSONDecodeError, OSError) as exc:
            runtime_trace.trace_event(
                "config_load_error",
                subsystem="config",
                severity=runtime_trace.WARNING,
                payload={"file": "config.json", "error": str(exc)},
            )
        return config
    if config:
        return config
    return {
        "voice": True,
        "at_home": True,
        "tts_engine": "auto",
        "terminal_visible": True,
        "active_sessions": [],
        "ollama_host": "http://192.168.0.234:11434",
        "ollama_model": "gemma4:e2b",
        "whisper_host": "http://192.168.0.234:8001",
        "mac_ssh_host": "192.168.0.234",
        "mac_ssh_user": "homelab",
        "dell_ssh_host": "192.168.0.162",
        "dell_ssh_user": "homelab",
        "jellyfin_host": "http://media.home.lan",
        "jellyfin_api_key": "",
        "vision_host": "http://192.168.0.234:8004",
        "vision_timeout_seconds": 90,
        "audio_sample_rate": 16000,
        "audio_channels": 1,
        "audio_chunk_size": 1024,
        "memory_context_turns": 6,
        "shell_timeout_seconds": 20,
        "copilot_hold_threshold": 0.3,
        "copilot_double_tap_window": 0.4,
        "copilot_min_audio_seconds": 0.5,
        "suppress_copilot": False,
        "widget_anchor_x": None,
        "widget_anchor_y": None,
        "widget_anchor_bottom_y": None,
    }


def on_config_change(key, value):
    print(f"[main] config changed: {key} = {value}")


def record_state_event(
    event_type: str,
    *,
    source: str = "april",
    domain: str = "april",
    state: str = "observed",
    entity_id: str | None = None,
    payload: dict | None = None,
    config: dict | None = None,
) -> None:
    append_event(
        event_type,
        source=source,
        domain=domain,
        state=state,
        entity_id=entity_id,
        payload=payload or {},
    )
    refresh_state_snapshot(config=config)


def begin_interruptible_request(source: str, *, trigger_kind: str = "") -> int:
    """Register a new request for interrupt/staleness tracking.

    Returns an integer sequence number used by is_request_current().
    For the text path, _format_request_id() of this integer IS the canonical
    request_id string.  For the voice path, the canonical string is generated
    in input_handler._generate_request_id() at key-press and passed explicitly
    through on_audio(..., request_id_str).
    """
    global _latest_request_id
    with _request_lock:
        previous_request_id = _latest_request_id if _latest_request_id > 0 else None
        _latest_request_id += 1
        request_id = _latest_request_id
    stop_speaking()
    if previous_request_id is not None:
        record_state_event(
            "request_interrupted",
            source=source,
            state="updated",
            entity_id=f"request_{previous_request_id}",
            payload={
                "source": source,
                "request_id": previous_request_id,
                "replaced_by_request_id": request_id,
            },
            config=load_config(),
        )
    log_event("request_begin", source=source, request_id=request_id)
    runtime_trace.trace_event(
        "request_begin",
        subsystem="input",
        request_id=_format_request_id(request_id),
        payload={"source": source, "trigger_kind": trigger_kind},
    )
    record_state_event(
        "request_started",
        source=source,
        state="started",
        entity_id=f"request_{request_id}",
        payload={
            "source": source,
            "request_id": request_id,
            "trigger_kind": trigger_kind,
        },
        config=load_config(),
    )
    return request_id


def interrupt_current_request(source: str = "interrupt") -> int:
    return begin_interruptible_request(source)


def is_request_current(request_id: int) -> bool:
    with _request_lock:
        return request_id == _latest_request_id


def handle_user_text(
    text: str,
    source: str = "text",
    request_id: int | None = None,
    request_id_str: str | None = None,
    *,
    trigger_kind: str = "voice_command",
):
    # Derive formatted request_id string if not passed explicitly (e.g. direct callers).
    if request_id_str is None and request_id is not None:
        request_id_str = _format_request_id(request_id)
    print(f"[main] user text ({source}): {text}")
    log_event("user_text", source=source, text=text, request_id=request_id)
    runtime_trace.trace_event(
        "handle_user_text",
        subsystem="brain",
        request_id=request_id_str,
        payload={"source": source, "text": text[:120], "trigger_kind": trigger_kind},
    )
    config = load_config()
    observation = collect_runtime_observation()
    record_state_event(
        "desktop_observed",
        source="desktop",
        domain="desktop",
        state="observed",
        entity_id=f"request_{request_id}" if request_id is not None else None,
        payload=observation,
        config=config,
    )
    if _bridge_ref is not None:
        _bridge_ref.set_state("thinking", request_id=request_id_str)
        _bridge_ref.set_task(f"Processing: {text[:60]}")
    _error_in_pipeline = None
    try:
        brain_job_id = _format_job_id("BRAIN")
        runtime_trace.trace_event(
            "brain_begin",
            subsystem="brain",
            request_id=request_id_str,
            job_id=brain_job_id,
            payload={"source": source, "text_len": len(text)},
        )
        plan = plan_with_brain(text, config)
        provenance = _routing_provenance(plan)
        runtime_trace.trace_event(
            "intent_planned",
            subsystem="brain",
            request_id=request_id_str,
            job_id=brain_job_id,
            payload={
                "intent": plan.get("intent"),
                "source": source,
                "trigger_kind": trigger_kind,
                "planner_source": provenance["planner_source"],
            },
        )
        log_event(
            "intent_plan",
            source=source,
            request_id=request_id,
            intent=plan.get("intent"),
            action=plan.get("action"),
            trigger_kind=trigger_kind,
            planner_source=provenance["planner_source"],
        )
        record_state_event(
            "intent_planned",
            source=source,
            state="observed",
            entity_id=f"request_{request_id}" if request_id is not None else None,
            payload={
                "source": source,
                "request_id": request_id,
                "text": text,
                "intent": plan.get("intent"),
                "action": plan.get("action"),
                "trigger_kind": trigger_kind,
                "routing": provenance,
            },
            config=config,
        )
        if request_id is not None and not is_request_current(request_id):
            log_event(
                "response_discarded",
                source=source,
                text=text,
                response="",
                request_id=request_id,
            )
            record_state_event(
                "response_discarded",
                source=source,
                state="updated",
                entity_id=f"request_{request_id}",
                payload={"source": source, "request_id": request_id, "text": text},
                config=config,
            )
            return ""

        result = execute_plan(
            plan,
            config,
            context={
                "text": text,
                "source": source,
                "config_callback": on_config_change,
                "trigger_kind": trigger_kind,
                "routing_provenance": provenance,
            },
        )
        response = str(result.get("reply", "") or "").strip()
        ok = bool(result.get("ok", bool(response)))
        error_kind = str(result.get("error_kind", "") or "").strip()
        validation_label, validation_detail = _classify_action_validation(
            trigger_kind=trigger_kind,
            planner_source=str(provenance["planner_source"]),
            plan=plan,
            result=result,
        )
        log_event(
            "action_result",
            source=source,
            request_id=request_id,
            intent=plan.get("intent"),
            ok=ok,
            reply=response,
            config_changed=bool(result.get("config_changed")),
            trigger_kind=trigger_kind,
            planner_source=provenance["planner_source"],
            validation_label=validation_label,
        )
        record_state_event(
            "action_completed" if ok else "action_failed",
            source=source,
            state="completed" if ok else "failed",
            entity_id=f"request_{request_id}" if request_id is not None else None,
            payload={
                "source": source,
                "request_id": request_id,
                "text": text,
                "intent": plan.get("intent"),
                "reply": response,
                "ok": ok,
                "error_kind": error_kind,
                "config_changed": bool(result.get("config_changed")),
                "trigger_kind": trigger_kind,
                "routing": provenance,
                "validation_label": validation_label,
                "validation_detail": validation_detail,
            },
            config=config,
        )
        record_state_event(
            "action_validated",
            source="system",
            state="observed",
            entity_id=f"request_{request_id}" if request_id is not None else None,
            payload={
                "request_id": request_id,
                "trigger_kind": trigger_kind,
                "planner_source": provenance["planner_source"],
                "verdict": validation_label,
                "detail": validation_detail,
            },
            config=config,
        )
        if request_id is not None and not is_request_current(request_id):
            log_event(
                "response_discarded",
                source=source,
                text=text,
                response=response,
                request_id=request_id,
            )
            record_state_event(
                "response_discarded",
                source=source,
                state="updated",
                entity_id=f"request_{request_id}",
                payload={
                    "source": source,
                    "request_id": request_id,
                    "text": text,
                    "response": response,
                },
                config=config,
            )
            return ""

        if result.get("config_changed"):
            config = load_config()
            updates = result.get("updates")
            if isinstance(updates, dict) and updates:
                record_state_event(
                    "config_changed",
                    source=source,
                    state="updated",
                    entity_id="runtime_config",
                    payload={"source": source, "updates": updates},
                    config=config,
                )

        _enriched = plan.get("_enriched_context") or {}
        _enriched_str = ""
        if _enriched.get("memory"):
            _enriched_str += f"Memory:\n{_enriched['memory']}\n\n"
        if _enriched.get("state"):
            _enriched_str += f"State:\n{_enriched['state']}"

        record_semantic_example(
            kind="turn",
            text=text,
            source=source,
            resolved_intent=str(plan.get("intent", "") or ""),
            response=response,
            action=plan.get("action") if isinstance(plan.get("action"), dict) else {},
            outcome="success" if ok else "failure",
            subject_type="utterance",
            subject_ref=str(request_id or ""),
            confidence=1.0 if ok else 0.6,
            metadata={
                "request_id": request_id,
                "source": source,
                "ok": ok,
                "error_kind": error_kind,
                "config_changed": bool(result.get("config_changed")),
                "trigger_kind": trigger_kind,
                "planner_source": provenance["planner_source"],
                "validation_detail": validation_detail,
            },
            session_id=_session_id,
            system_prompt_hash=_system_prompt_hash,
            enriched_context=_enriched_str.strip(),
            validation_label=validation_label,
        )
        if response:
            print(f"[main] assistant response: {response}")
            log_event(
                "assistant_response",
                source=source,
                response=response,
                request_id=request_id,
            )
            runtime_trace.trace_event(
                "assistant_response",
                subsystem="brain",
                request_id=request_id_str,
                job_id=brain_job_id,
                payload={"source": source, "reply_len": len(response)},
            )
            append_turn(text, response, source=source)
            record_state_event(
                "assistant_replied",
                source=source,
                state="completed",
                entity_id=f"request_{request_id}" if request_id is not None else None,
                payload={
                    "source": source,
                    "request_id": request_id,
                    "response": response,
                },
                config=config,
            )
            tts_job_id = _format_job_id("TTS")
            runtime_trace.trace_event(
                "tts_begin",
                subsystem="tts",
                request_id=request_id_str,
                job_id=tts_job_id,
                payload={"source": source, "reply_len": len(response)},
            )
            if _bridge_ref is not None:
                _bridge_ref.set_state("speaking", request_id=request_id_str)
                _bridge_ref.set_transcript(response)
                _bridge_ref.set_task("Speaking")
                _bridge_ref.append_log(f"reply ({source}): {response[:120]}")
            speak_reply(
                response,
                config,
                on_done=lambda _ok: _on_speak_done(
                    response, request_id_str, tts_job_id
                ),
            )
            return response

        if _bridge_ref is not None:
            _bridge_ref.set_state("idle", request_id=request_id_str)
            _bridge_ref.set_task("")

        if source == "voice":
            return f"Heard: {text}"
        return "I heard you, but I do not have a reply yet."
    except Exception as exc:
        _error_in_pipeline = exc
        runtime_trace.trace_event(
            "pipeline_error",
            subsystem="brain",
            severity=runtime_trace.ERROR,
            request_id=request_id_str,
            payload={"error": str(exc), "source": source, "text": text[:120]},
        )
        raise
    finally:
        if _error_in_pipeline is not None and _bridge_ref is not None:
            _bridge_ref.set_state("idle", request_id=request_id_str)
            _bridge_ref.set_task("")


def _on_speak_done(
    response: str, request_id_str: str | None = None, tts_job_id: str | None = None
) -> None:
    """TTS completion handler — drives the bridge back to idle."""
    runtime_trace.trace_event(
        "tts_done",
        subsystem="tts",
        request_id=request_id_str,
        job_id=tts_job_id,
    )
    if _bridge_ref is not None:
        _bridge_ref.set_state("idle")
        _bridge_ref.set_task("")


def on_text_submit(text: str):
    request_id = begin_interruptible_request("text")
    req_id_str = _format_request_id(request_id)
    runtime_trace.trace_event(
        "text_submit",
        subsystem="input",
        request_id=req_id_str,
        payload={"text": text[:120]},
    )
    return handle_user_text(
        text, source="text", request_id=request_id, request_id_str=req_id_str
    )


def _post_process_dictation(text: str) -> str:
    """Clean stutters, filler words, format spoken punctuation, and fix spacing."""
    if not text:
        return ""
    import re

    # Convert Whisper's automatic segment newlines to spaces first
    text = text.replace("\r\n", " ").replace("\n", " ")
    # 1. Clean common filler words
    fillers = ["um", "uh", "ah", "er", "eh"]
    for f in fillers:
        text = re.sub(r"\b" + f + r"\b[,.]?", "", text, flags=re.IGNORECASE)

    # 2. Spoken Punctuation mapping
    punctuation_map = [
        ("new paragraph", "\n\n"),
        ("newparagraph", "\n\n"),
        ("new line", "\n"),
        ("newline", "\n"),
        ("sew line", "\n"),
        ("sewline", "\n"),
        ("shoe line", "\n"),
        ("shoeline", "\n"),
        ("exclamation point", "!"),
        ("exclamation mark", "!"),
        ("question mark", "?"),
        ("full stop", "."),
        ("period", "."),
        ("comma", ","),
        ("colon", ":"),
        ("semicolon", ";"),
    ]
    for spoken, symbol in punctuation_map:
        text = re.sub(r"\b" + spoken + r"\b", symbol, text, flags=re.IGNORECASE)

    # 3. Clean up stutters (duplicate consecutive identical words)
    text = re.sub(r"\b(\w+)\s+\1\b", r"\1", text, flags=re.IGNORECASE)

    # 4. Clean spacing around newlines, collapse spaces, and remove spaces before punctuation
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = re.sub(r"\s+([.,?!:;])", r"\1", text)
    text = re.sub(r"[ \t]+", " ", text)

    # 5. Capitalize sentences
    text = re.sub(r"^([a-z])", lambda m: m.group(1).upper(), text)
    text = re.sub(r"([.?!]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)
    return text.strip()


def on_audio_captured(
    audio_bytes: bytes,
    duration: float,
    request_id_str: str | None = None,
    is_dictation: bool = False,
    trigger_kind: str | None = None,
):
    # begin_interruptible_request handles interrupt/staleness tracking.
    # The canonical request_id_str comes from input_handler (born at key press);
    # we do NOT format a second REQ-NNNN from the integer here.
    trigger_kind = _normalize_trigger_kind(trigger_kind, is_dictation=is_dictation)
    is_dictation = trigger_kind == "voice_dictation"
    request_source = "dictation" if is_dictation else "voice"
    request_id = begin_interruptible_request(request_source, trigger_kind=trigger_kind)
    if request_id_str is None:
        # Defensive fallback: should not occur in normal operation.
        request_id_str = _format_request_id(request_id)
    size_kb = len(audio_bytes) / 1024
    print(f"[main] audio captured: {duration:.2f}s, {size_kb:.1f} KiB WAV")
    log_event(
        "audio_captured",
        duration=duration,
        size_kb=round(size_kb, 1),
        request_id=request_id,
        trigger_kind=trigger_kind,
    )
    runtime_trace.trace_event(
        "audio_captured",
        subsystem="input",
        request_id=request_id_str,
        payload={
            "duration": round(duration, 3),
            "size_kb": round(size_kb, 1),
            "is_dictation": is_dictation,
            "trigger_kind": trigger_kind,
        },
    )
    config = load_config()
    record_state_event(
        "audio_captured",
        source=request_source,
        state="completed",
        entity_id=f"request_{request_id}",
        payload={
            "request_id": request_id,
            "duration": duration,
            "size_kb": round(size_kb, 1),
            "is_dictation": is_dictation,
            "trigger_kind": trigger_kind,
        },
        config=config,
    )
    if _bridge_ref is not None:
        state_to_push = "dictating" if is_dictation else "listening"
        _bridge_ref.set_state(state_to_push, request_id=request_id_str)
        _bridge_ref.set_task("Dictating…" if is_dictation else "Listening…")

    if is_dictation:
        dictation_prompt = "dictation, new line, newline, new paragraph, period, comma, question mark, exclamation point, test 1, test 2, April, say hi."
        existing_prompt = str(config.get("stt_initial_prompt", "") or "").strip()
        if existing_prompt:
            config = dict(
                config, stt_initial_prompt=f"{existing_prompt}, {dictation_prompt}"
            )
        else:
            config = dict(config, stt_initial_prompt=dictation_prompt)

    stt_job_id = _format_job_id("STT")
    runtime_trace.trace_event(
        "stt_begin",
        subsystem="stt",
        request_id=request_id_str,
        job_id=stt_job_id,
        payload={"duration": round(duration, 3)},
    )
    try:
        transcript, stt_meta = transcribe_with_metadata(audio_bytes, config)
    except Exception as stt_exc:
        runtime_trace.trace_event(
            "stt_error",
            subsystem="stt",
            severity=runtime_trace.ERROR,
            request_id=request_id_str,
            job_id=stt_job_id,
            payload={"error": str(stt_exc)},
        )
        if _bridge_ref is not None:
            _bridge_ref.set_state("idle", request_id=request_id_str)
            _bridge_ref.set_task("")
        return "I captured that, but transcription failed unexpectedly."
    if not transcript.strip():
        print("[main] transcription unavailable")
        log_event(
            "transcription_unavailable",
            request_id=request_id,
            trigger_kind=trigger_kind,
            **stt_meta,
        )
        runtime_trace.trace_event(
            "transcript_unavailable",
            subsystem="stt",
            severity=runtime_trace.WARNING,
            request_id=request_id_str,
            job_id=stt_job_id,
            payload=stt_meta,
        )
        record_state_event(
            "transcript_unavailable",
            source=request_source,
            state="failed",
            entity_id=f"request_{request_id}",
            payload={
                "request_id": request_id,
                "trigger_kind": trigger_kind,
                **stt_meta,
            },
            config=config,
        )
        if _bridge_ref is not None:
            _bridge_ref.set_state("idle", request_id=request_id_str)
            _bridge_ref.set_task("")
        return "I captured that, but I couldn't transcribe it."

    print(f"[main] transcript: {transcript}")
    log_event(
        "transcript",
        transcript=transcript,
        request_id=request_id,
        trigger_kind=trigger_kind,
        **stt_meta,
    )
    runtime_trace.trace_event(
        "transcript_received",
        subsystem="stt",
        request_id=request_id_str,
        job_id=stt_job_id,
        payload={"transcript": transcript[:120]},
    )
    record_state_event(
        "transcript_received",
        source=request_source,
        state="completed",
        entity_id=f"request_{request_id}",
        payload={
            "request_id": request_id,
            "transcript": transcript,
            "trigger_kind": trigger_kind,
            **stt_meta,
        },
        config=config,
    )

    if is_dictation:
        cleaned = _post_process_dictation(transcript)
        print(f"[main] dictation output: {cleaned}")
        if cleaned:
            if _input_handler_ref is not None:
                _input_handler_ref.is_pasting = True
                runtime_trace.trace_event(
                    "dictation_paste_start",
                    subsystem="input",
                    severity=runtime_trace.DEBUG,
                    request_id=request_id_str,
                )
            else:
                runtime_trace.trace_event(
                    "dictation_paste_missing_handler",
                    subsystem="input",
                    severity=runtime_trace.WARNING,
                    request_id=request_id_str,
                )
            try:
                try:
                    import time

                    import pyperclip
                    from pynput.keyboard import Controller, Key

                    keyboard = Controller()

                    # 1. Cooldown to wait for Copilot key modifiers (Ctrl+Alt+Shift+Win) to physically clear
                    time.sleep(0.2)

                    # 2. Flush OS modifier states in case they are stuck in the event queue
                    keyboard.release(Key.ctrl)
                    keyboard.release(Key.alt)
                    keyboard.release(Key.shift)
                    keyboard.release(Key.cmd)  # Win key
                    time.sleep(0.02)

                    # 3. Backup user's current clipboard
                    old_clipboard = pyperclip.paste()

                    # 4. Split and paste line-by-line using Shift+Enter to prevent message submission
                    lines = cleaned.split("\n")
                    for idx, line in enumerate(lines):
                        if idx > 0:
                            with keyboard.pressed(Key.shift):
                                keyboard.press(Key.enter)
                                keyboard.release(Key.enter)
                            time.sleep(0.05)

                        if line:
                            pyperclip.copy(line)
                            time.sleep(0.05)  # wait for clipboard to update

                            with keyboard.pressed(Key.ctrl):
                                keyboard.press("v")
                                keyboard.release("v")
                            time.sleep(0.1)  # wait for paste to complete

                    # 5. Restore the user's old clipboard
                    time.sleep(0.1)
                    pyperclip.copy(old_clipboard)

                except Exception as e:
                    # Ultimate Fallback: Slow character-by-character typing if the clipboard fails
                    print(
                        f"[main] clipboard paste failed ({e}), falling back to slow typing"
                    )
                    try:
                        import time

                        from pynput.keyboard import Controller, Key

                        keyboard = Controller()
                        for char in cleaned:
                            if char == "\n":
                                with keyboard.pressed(Key.shift):
                                    keyboard.press(Key.enter)
                                    keyboard.release(Key.enter)
                            else:
                                keyboard.type(char)
                            time.sleep(0.015)
                    except Exception as e2:
                        print(f"[main] dictation fallback typing failed: {e2}")
                        runtime_trace.trace_event(
                            "dictation_type_error",
                            subsystem="input",
                            severity=runtime_trace.ERROR,
                            request_id=request_id_str,
                            payload={"error": str(e2)},
                        )
            finally:
                if _input_handler_ref is not None:
                    _input_handler_ref.is_pasting = False
                    runtime_trace.trace_event(
                        "dictation_paste_end",
                        subsystem="input",
                        severity=runtime_trace.DEBUG,
                        request_id=request_id_str,
                    )
        runtime_trace.trace_event(
            "dictation_completed",
            subsystem="input",
            request_id=request_id_str,
            payload={
                "raw_len": len(transcript),
                "clean_len": len(cleaned),
                "trigger_kind": trigger_kind,
            },
        )
        record_state_event(
            "action_validated",
            source="system",
            state="observed",
            entity_id=f"request_{request_id}",
            payload={
                "request_id": request_id,
                "trigger_kind": trigger_kind,
                "verdict": "confirmed_correct" if cleaned else "execution_failed",
                "detail": (
                    "dictation_bypassed_router" if cleaned else "dictation_output_empty"
                ),
            },
            config=config,
        )
        if _bridge_ref is not None:
            _bridge_ref.set_state("idle", request_id=request_id_str)
            _bridge_ref.set_task("")
            _bridge_ref.append_log(f"dictated: {cleaned[:120]}")
        return cleaned

    if _bridge_ref is not None:
        _bridge_ref.set_transcript(transcript)

    return handle_user_text(
        transcript,
        source=request_source,
        request_id=request_id,
        request_id_str=request_id_str,
        trigger_kind=trigger_kind,
    )


def acquire_single_instance() -> bool:
    global _single_instance_handle
    if os.name != "nt":
        return True
    kernel32 = ctypes.windll.kernel32
    ERROR_ALREADY_EXISTS = 183
    handle = kernel32.CreateMutexW(None, False, _SINGLE_INSTANCE_NAME)
    if not handle:
        return True
    last_error = kernel32.GetLastError()
    if last_error == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return False
    _single_instance_handle = handle
    return True


def main():
    global _bridge_ref
    trace_startup("main() entered")
    config = load_config()
    import database

    database.init_db()
    global _system_prompt_hash
    from brain import _system_prompt

    _system_prompt_hash = hashlib.sha256(
        _system_prompt(config).encode("utf-8")
    ).hexdigest()[:16]
    trace_startup(
        f"config loaded voice={config.get('voice')} at_home={config.get('at_home')}"
    )
    if not acquire_single_instance():
        trace_startup("duplicate instance detected; exiting")
        print(
            "[main] another APRIL instance is already running - exiting duplicate launch"
        )
        return
    print(
        f"[main] config loaded - at_home={config.get('at_home')}, voice={config.get('voice')}"
    )
    record_state_event(
        "april_started",
        source="system",
        state="started",
        entity_id="april_runtime",
        payload={
            "voice": bool(config.get("voice", True)),
            "at_home": bool(config.get("at_home", True)),
        },
        config=config,
    )
    trace_startup("startup event recorded")

    # ── QApplication ────────────────────────────────────────────────────────────────────────
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    trace_startup("QApplication created in main()")
    # ────────────────────────────────────────────────────────────────────────────────

    # ── Surface system ───────────────────────────────────────────────────────────────────────
    from ui import (
        AmbientAnchor,
        APRILBridge,
        APRILCore,
        TransitionalOverlay,
    )

    core = APRILCore()
    bridge = APRILBridge(core)
    anchor = AmbientAnchor(core)
    overlay = TransitionalOverlay(core)
    bridge.attach_overlay(overlay)

    import webbrowser

    core.settings_requested.connect(
        lambda: webbrowser.open("http://localhost:8080/#settings")
    )
    anchor.show()
    anchor._force_topmost()
    bridge.set_state("idle")
    _bridge_ref = bridge
    import threading

    from control_panel import start_control_panel

    threading.Thread(target=start_control_panel, args=(bridge,), daemon=True).start()
    trace_startup("surface system started")
    print("[main] surface system started")
    # ────────────────────────────────────────────────────────────────────────────────

    from input_handler import start as start_input_handler

    # APRILBridge.set_state(str) satisfies the RuntimeStateSink protocol directly.
    # No shim required.
    global _input_handler_ref
    input_handler = start_input_handler(
        bridge,
        config,
        on_audio=on_audio_captured,
        on_interrupt=interrupt_current_request,
    )
    _input_handler_ref = input_handler
    trace_startup(f"input_handler started type={type(input_handler).__name__}")

    try:
        trace_startup("entering app.exec()")
        app.exec()
    finally:
        trace_startup("app.exec() returned — shutdown complete")
        input_handler.stop()
        runtime_trace.shutdown()
    print("[main] surface system closed - shutting down")


if __name__ == "__main__":
    try:
        trace_startup("__main__ entered")
        main()
    except Exception:
        trace_startup("fatal exception during startup:\n" + traceback.format_exc())
        raise
