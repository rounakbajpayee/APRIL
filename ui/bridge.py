"""
ui/bridge.py — APRILBridge

Thread-safe adapter between the APRIL runtime (brain / STT / TTS threads)
and the new APRILCore surface system.

The runtime runs in background threads; Qt widgets must only be touched from
the main thread.  APRILBridge owns the thread crossing: runtime code calls the
public methods (safe from any thread), and Qt's QueuedConnection delivers each
payload to the surface slots on the main thread.

State mapping
─────────────
Runtime string   →  APRILState enum
"idle"           →  DORMANT
"listening"      →  LISTENING
"thinking"       →  THINKING
"speaking"       →  SPEAKING
"error"          →  ERROR
(anything else)  →  DORMANT  (safe fallback)

Usage
─────
    bridge = APRILBridge(core)
    bridge.attach_overlay(overlay)
    bridge.attach_workspace(workspace)

    # from any thread:
    bridge.set_state("listening")
    bridge.set_transcript("I heard: hello")
    bridge.append_log("intent resolved: media_play")
"""
from __future__ import annotations

import runtime_trace

from PyQt6.QtCore import QObject, pyqtSignal, Qt

from .state import APRILCore, APRILState


# ── runtime string → APRILState ────────────────────────────────────────────

_STATE_MAP: dict[str, APRILState] = {
    "idle":        APRILState.DORMANT,
    "dormant":     APRILState.DORMANT,
    "listening":   APRILState.LISTENING,
    "thinking":    APRILState.THINKING,
    "processing":  APRILState.THINKING,
    "speaking":    APRILState.SPEAKING,
    "acting":      APRILState.ACTING,
    "dictating":   APRILState.ACTING,
    "warning":     APRILState.WARNING,
    "error":       APRILState.ERROR,
}


class APRILBridge(QObject):
    """
    Thread-safe bridge: live APRIL runtime → APRILCore surfaces.

    All public methods are safe to call from any thread.
    Qt slot handlers (_apply_*) always run on the main thread via
    QueuedConnection, so surfaces are never touched from a background thread.
    """

    # Internal signals — cross the thread boundary into the Qt event loop.
    # Typed with primitive Qt-compatible types only (str, not APRILState)
    # so they can be emitted from any thread without pickling issues.
    _state_sig        = pyqtSignal(str)            # raw runtime state string
    _transcript_sig   = pyqtSignal(str)            # STT / assistant response text
    _task_sig         = pyqtSignal(str)            # current task label
    _log_sig          = pyqtSignal(str)            # single log line
    _notification_sig = pyqtSignal(str, str, str)  # level, title, body

    def __init__(self, core: APRILCore, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._core: APRILCore = core

        # Surface references — registered after construction via attach_*()
        self._overlay   = None   # TransitionalOverlay | None
        self._workspace = None   # TacticalWorkspace   | None

        # All connections use QueuedConnection so signals emitted from
        # background threads are safely delivered on the main thread.
        self._state_sig.connect(
            self._apply_state, Qt.ConnectionType.QueuedConnection)
        self._transcript_sig.connect(
            self._apply_transcript, Qt.ConnectionType.QueuedConnection)
        self._task_sig.connect(
            self._apply_task, Qt.ConnectionType.QueuedConnection)
        self._log_sig.connect(
            self._apply_log, Qt.ConnectionType.QueuedConnection)
        self._notification_sig.connect(
            self._apply_notification, Qt.ConnectionType.QueuedConnection)

    # ── surface attachment ──────────────────────────────────────────────────

    def attach_overlay(self, overlay) -> None:
        """Register the TransitionalOverlay surface."""
        self._overlay = overlay

    def attach_workspace(self, workspace) -> None:
        """Register the TacticalWorkspace surface."""
        self._workspace = workspace

    # ── public API (thread-safe) ────────────────────────────────────────────

    def set_state(self, state: str, request_id: str | None = None) -> None:
        """
        Notify the bridge of a runtime state change.

        ``state`` is the runtime string — "idle", "listening", "thinking",
        "speaking", "error", etc.  Call from any thread.
        ``request_id`` — Phase 2B REQ-NNNN correlation string, passed through
        to the trace and forwarded via the signal payload.
        """
        runtime_trace.trace_event(
            "bridge_set_state",
            subsystem="bridge",
            request_id=request_id,
            payload={"state": state},
        )
        # Transport note: pyqtSignal(str) carries a single string across the
        # thread boundary.  We encode request_id into the payload as
        # "state\x00REQ-NNNN" using a null-byte separator rather than adding
        # a second signal parameter.  This avoids widening the signal contract
        # and keeps the existing QueuedConnection wiring unchanged.
        # _apply_state unpacks the separator.  The null byte (\x00) cannot
        # appear in either field: state strings are short ASCII labels and
        # REQ-NNNN is also ASCII.
        # This is a transport encoding hack, not a semantic model.  A future
        # phase may introduce a dedicated typed signal if the contract grows.
        encoded = f"{state}\x00{request_id}" if request_id is not None else state
        self._state_sig.emit(encoded)

    def set_transcript(self, text: str) -> None:
        """
        Push live STT or assistant response text to the overlay.

        Call from any thread.
        """
        self._transcript_sig.emit(text or "")

    def set_task(self, text: str) -> None:
        """
        Update the current-task label in the overlay status bar.

        Call from any thread.
        """
        self._task_sig.emit(text or "")

    def append_log(self, msg: str) -> None:
        """
        Append a single log line to the workspace Log tab.

        Call from any thread.
        """
        self._log_sig.emit(msg or "")

    def notify(self, level: str, title: str, body: str = "") -> None:
        """
        Emit a notification through APRILCore.

        ``level`` is one of: "passive", "contextual", "interruptive", "critical".
        Call from any thread.
        """
        self._notification_sig.emit(level, title, body)

    # ── private slots (main-thread only) ───────────────────────────────────

    def _apply_state(self, encoded: str) -> None:
        # Unpack optional request_id encoded as "state\x00REQ-NNNN".
        if "\x00" in encoded:
            state_str, request_id = encoded.split("\x00", 1)
        else:
            state_str, request_id = encoded, None
        april_state = _STATE_MAP.get(state_str.lower(), APRILState.DORMANT)
        runtime_trace.trace_event(
            "bridge_apply_state",
            subsystem="bridge",
            request_id=request_id,
            payload={"state": state_str, "april_state": april_state.name},
        )
        self._core.set_state(april_state, request_id=request_id)

    def _apply_transcript(self, text: str) -> None:
        if self._overlay is not None:
            self._overlay.set_transcript(text)

    def _apply_task(self, text: str) -> None:
        if self._overlay is not None:
            self._overlay.set_task(text)

    def _apply_log(self, msg: str) -> None:
        if self._workspace is not None:
            self._workspace.append_log(msg)

    def _apply_notification(self, level: str, title: str, body: str) -> None:
        _dispatch = {
            "passive":      self._core.notification_passive,
            "contextual":   self._core.notification_contextual,
            "interruptive": self._core.notification_interruptive,
            "critical":     self._core.notification_critical,
        }
        sig = _dispatch.get(level.lower())
        if sig is not None:
            sig.emit(title, body)
