"""
runtime_state_sink.py — Minimal canonical runtime interface.

This is the ONLY contract InputHandler needs from any surface.
APRILBridge satisfies this protocol directly; no shim required.

Nothing else belongs in this file.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class RuntimeStateSink(Protocol):
    """
    Minimal boundary between the APRIL runtime and any UI surface.

    InputHandler is the sole caller.
    APRILBridge (ui/bridge.py) is the sole implementor — structurally,
    without modification; its set_state(str) already satisfies this.

    Intentionally tiny.  If you are tempted to add a method here, check
    whether main.py should own that call instead.
    """

    def set_state(self, state: str, request_id: str | None = None) -> None:
        """
        Notify the surface of a runtime state transition.

        state: one of "idle" | "listening" | "thinking" | "speaking" | "error"
        request_id: Phase 2B — optional REQ-NNNN correlation string.
        Thread-safe; may be called from any background thread.
        """
        ...
