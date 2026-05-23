"""
main.py - APRIL entry point.
"""

import ctypes
from datetime import datetime, timezone
import json
import os
import threading
import traceback

from brain import process as plan_with_brain
from debug_log import log_event
from event_ledger import append_event
from intent import execute_plan
from memory import append_turn
from semantic_store import record_semantic_example
from observer import collect_runtime_observation
from state_engine import refresh_state_snapshot
from stt import transcribe_with_metadata
from tts import speak as speak_reply, stop as stop_speaking


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
DEFAULT_PATH = os.path.join(BASE_DIR, "config_defaults.json")
TRACE_PATH = os.path.join(BASE_DIR, "logs", "startup_trace.log")
_request_lock = threading.Lock()
_latest_request_id = 0
_widget_ref = None
_bridge_ref = None          # APRILBridge | None  (Phase 2: new surface system)
_single_instance_handle = None
_SINGLE_INSTANCE_NAME = "Local\\APRILDesktopSingleton"


def trace_startup(message: str) -> None:
    os.makedirs(os.path.dirname(TRACE_PATH), exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    with open(TRACE_PATH, "a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} [main] {message}\n")


def load_config() -> dict:
    config = {}
    if os.path.exists(DEFAULT_PATH):
        with open(DEFAULT_PATH, encoding="utf-8") as f:
            config.update(json.load(f))
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            config.update(json.load(f))
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
        "gemini_api_key": "",
        "vision_model": "gemini-2.5-flash",
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


def begin_interruptible_request(source: str) -> int:
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
            payload={"source": source, "request_id": previous_request_id, "replaced_by_request_id": request_id},
            config=load_config(),
        )
    log_event("request_begin", source=source, request_id=request_id)
    record_state_event(
        "request_started",
        source=source,
        state="started",
        entity_id=f"request_{request_id}",
        payload={"source": source, "request_id": request_id},
        config=load_config(),
    )
    return request_id


def interrupt_current_request(source: str = "interrupt") -> int:
    return begin_interruptible_request(source)


def is_request_current(request_id: int) -> bool:
    with _request_lock:
        return request_id == _latest_request_id


def handle_user_text(text: str, source: str = "text", request_id: int | None = None):
    print(f"[main] user text ({source}): {text}")
    log_event("user_text", source=source, text=text, request_id=request_id)
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
        _bridge_ref.set_state("thinking")
        _bridge_ref.set_task(f"Processing: {text[:60]}")

    plan = plan_with_brain(text, config)
    log_event(
        "intent_plan",
        source=source,
        request_id=request_id,
        intent=plan.get("intent"),
        action=plan.get("action"),
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
        },
        config=config,
    )
    if request_id is not None and not is_request_current(request_id):
        log_event("response_discarded", source=source, text=text, response="", request_id=request_id)
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
        },
    )
    response = str(result.get("reply", "") or "").strip()
    ok = bool(result.get("ok", bool(response)))
    error_kind = str(result.get("error_kind", "") or "").strip()
    log_event(
        "action_result",
        source=source,
        request_id=request_id,
        intent=plan.get("intent"),
        ok=ok,
        reply=response,
        config_changed=bool(result.get("config_changed")),
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
        },
        config=config,
    )
    if request_id is not None and not is_request_current(request_id):
        log_event("response_discarded", source=source, text=text, response=response, request_id=request_id)
        record_state_event(
            "response_discarded",
            source=source,
            state="updated",
            entity_id=f"request_{request_id}",
            payload={"source": source, "request_id": request_id, "text": text, "response": response},
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
        if _widget_ref is not None:
            _schedule_widget_config_refresh(config)

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
        },
    )
    if response:
        print(f"[main] assistant response: {response}")
        log_event("assistant_response", source=source, response=response, request_id=request_id)
        append_turn(text, response, source=source)
        record_state_event(
            "assistant_replied",
            source=source,
            state="completed",
            entity_id=f"request_{request_id}" if request_id is not None else None,
            payload={"source": source, "request_id": request_id, "response": response},
            config=config,
        )
        if _widget_ref is not None:
            _widget_ref.set_state("speaking", response)
        if _bridge_ref is not None:
            _bridge_ref.set_state("speaking")
            _bridge_ref.set_transcript(response)
            _bridge_ref.set_task("Speaking")
            _bridge_ref.append_log(f"reply ({source}): {response[:120]}")
        speak_reply(
            response,
            config,
            on_done=lambda _ok: _on_speak_done(response),
        )
        return response

    if _bridge_ref is not None:
        _bridge_ref.set_state("idle")
        _bridge_ref.set_task("")

    if source == "voice":
        return f"Heard: {text}"
    return "I heard you, but I do not have a reply yet."


def _on_speak_done(response: str) -> None:
    """Unified TTS completion handler — drives both old widget and new surfaces."""
    if _widget_ref is not None:
        _widget_ref.set_state("idle", response)
    if _bridge_ref is not None:
        _bridge_ref.set_state("idle")
        _bridge_ref.set_task("")


def on_text_submit(text: str):
    request_id = begin_interruptible_request("text")
    return handle_user_text(text, source="text", request_id=request_id)


def on_audio_captured(audio_bytes: bytes, duration: float):
    request_id = begin_interruptible_request("voice")
    size_kb = len(audio_bytes) / 1024
    print(f"[main] audio captured: {duration:.2f}s, {size_kb:.1f} KiB WAV")
    log_event("audio_captured", duration=duration, size_kb=round(size_kb, 1), request_id=request_id)
    config = load_config()
    record_state_event(
        "audio_captured",
        source="voice",
        state="completed",
        entity_id=f"request_{request_id}",
        payload={"request_id": request_id, "duration": duration, "size_kb": round(size_kb, 1)},
        config=config,
    )
    if _bridge_ref is not None:
        _bridge_ref.set_state("listening")
        _bridge_ref.set_task("Listening…")

    transcript, stt_meta = transcribe_with_metadata(audio_bytes, config)
    if not transcript.strip():
        print("[main] transcription unavailable")
        log_event("transcription_unavailable", request_id=request_id, **stt_meta)
        record_state_event(
            "transcript_unavailable",
            source="voice",
            state="failed",
            entity_id=f"request_{request_id}",
            payload={"request_id": request_id, **stt_meta},
            config=config,
        )
        if _bridge_ref is not None:
            _bridge_ref.set_state("idle")
            _bridge_ref.set_task("")
        return "I captured that, but I couldn't transcribe it."

    print(f"[main] transcript: {transcript}")
    log_event("transcript", transcript=transcript, request_id=request_id, **stt_meta)
    record_state_event(
        "transcript_received",
        source="voice",
        state="completed",
        entity_id=f"request_{request_id}",
        payload={"request_id": request_id, "transcript": transcript, **stt_meta},
        config=config,
    )
    if _bridge_ref is not None:
        _bridge_ref.set_transcript(transcript)

    return handle_user_text(transcript, source="voice", request_id=request_id)


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


def _schedule_widget_config_refresh(config: dict) -> None:
    if _widget_ref is None or not hasattr(_widget_ref, "schedule_config_refresh"):
        return
    _widget_ref.schedule_config_refresh(config)


def _start_surface_system() -> None:
    """
    Phase 2: start the new Figma scaffold surface system alongside the old widget.

    Must be called from inside the Qt event loop (via QTimer.singleShot) so
    that Tool windows receive their show events and actually appear on screen.
    Isolated so any failure is caught without killing the legacy widget.
    """
    global _bridge_ref
    try:
        from ui import (
            APRILCore, APRILBridge, AmbientAnchor,
            TransitionalOverlay, TacticalWorkspace, SettingsPanel,
        )

        core      = APRILCore()
        bridge    = APRILBridge(core)
        anchor    = AmbientAnchor(core)
        overlay   = TransitionalOverlay(core)
        workspace = TacticalWorkspace(core)
        settings  = SettingsPanel(core)

        bridge.attach_overlay(overlay)
        bridge.attach_workspace(workspace)
        core.settings_requested.connect(settings.show)

        anchor.show()
        anchor.raise_()
        # Deferred raise: DWM on Windows can suppress Tool windows that are
        # shown by a process without current foreground rights.  A second
        # raise_() 500 ms later forces the window to the top after the
        # compositor has settled.
        from PyQt6.QtCore import QTimer as _QTimer
        _QTimer.singleShot(500, anchor.raise_)

        bridge.set_state("idle")
        _bridge_ref = bridge

        trace_startup("new surface system started (Phase 2 parallel mode)")
        print("[main] new surface system started alongside legacy widget")

    except Exception:
        trace_startup(
            "new surface system failed to start (non-fatal):\n"
            + traceback.format_exc()
        )
        print("[main] WARNING: new surface system failed to start — legacy widget still running")


def main():
    global _widget_ref
    trace_startup("main() entered")
    config = load_config()
    trace_startup(f"config loaded voice={config.get('voice')} at_home={config.get('at_home')}")
    if not acquire_single_instance():
        trace_startup("duplicate instance detected; exiting")
        print("[main] another APRIL instance is already running - exiting duplicate launch")
        return
    print(f"[main] config loaded - at_home={config.get('at_home')}, voice={config.get('voice')}")
    record_state_event(
        "april_started",
        source="system",
        state="started",
        entity_id="april_runtime",
        payload={"voice": bool(config.get("voice", True)), "at_home": bool(config.get("at_home", True))},
        config=config,
    )
    trace_startup("startup event recorded")

    from widget import APRILWidget
    trace_startup("APRILWidget import succeeded")

    widget = APRILWidget(config, on_config_change=on_config_change, on_text_submit=on_text_submit)
    _widget_ref = widget
    trace_startup("APRILWidget constructed")

    # ── Phase 2: schedule new surface system to start on first event loop tick ─
    # QTimer.singleShot(0) defers until after app.exec() starts so Tool windows
    # receive their show events and are actually painted on screen.
    from PyQt6.QtCore import QTimer
    QTimer.singleShot(0, _start_surface_system)
    trace_startup("surface system startup scheduled (singleShot 0)")
    # ──────────────────────────────────────────────────────────────────────────

    print("[main] widget started - APRIL is idle")
    from input_handler import start as start_input_handler
    trace_startup("input_handler import succeeded")

    input_handler = start_input_handler(
        widget,
        config,
        on_audio=on_audio_captured,
        on_interrupt=interrupt_current_request,
    )
    trace_startup(f"input_handler started type={type(input_handler).__name__}")

    try:
        trace_startup("entering widget.run()")
        widget.run()
    finally:
        trace_startup("widget.run() exited; stopping input handler")
        input_handler.stop()
    print("[main] widget closed - shutting down")
    trace_startup("main() shutdown complete")


if __name__ == "__main__":
    try:
        trace_startup("__main__ entered")
        main()
    except Exception:
        trace_startup("fatal exception during startup:\n" + traceback.format_exc())
        raise
