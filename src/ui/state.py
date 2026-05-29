from __future__ import annotations
import runtime_trace

from enum import Enum, auto
from PyQt6.QtCore import QObject, pyqtSignal


class APRILState(Enum):
    DORMANT = auto()
    LISTENING = auto()
    THINKING = auto()
    SPEAKING = auto()
    ACTING = auto()
    WARNING = auto()
    ERROR = auto()


class APRILMode(Enum):
    AMBIENT = auto()
    FOCUS = auto()
    TACTICAL = auto()


class PresenceProfile(Enum):
    MINIMAL = auto()
    BALANCED = auto()
    IMMERSIVE = auto()


class Corner(Enum):
    BOTTOM_RIGHT = auto()
    BOTTOM_LEFT = auto()
    TOP_RIGHT = auto()
    TOP_LEFT = auto()


class APRILCore(QObject):
    """Central state machine — single source of truth for all APRIL surfaces."""

    state_changed = pyqtSignal(APRILState)
    mode_changed = pyqtSignal(APRILMode)
    profile_changed = pyqtSignal(PresenceProfile)
    corner_changed = pyqtSignal(Corner)
    settings_requested = pyqtSignal()

    # Notification signals
    notification_passive = pyqtSignal(str, str)  # title, body
    notification_contextual = pyqtSignal(str, str)
    notification_interruptive = pyqtSignal(str, str)
    notification_critical = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = APRILState.DORMANT
        self._mode = APRILMode.AMBIENT
        self._profile = PresenceProfile.BALANCED
        self._corner = Corner.BOTTOM_RIGHT

    # --- State ---

    @property
    def state(self) -> APRILState:
        return self._state

    def set_state(self, s: APRILState, request_id: str | None = None) -> None:
        if self._state != s:
            runtime_trace.trace_event(
                "core_state_transition",
                subsystem="state",
                request_id=request_id,
                payload={"old": self._state.name, "new": s.name},
            )
            self._state = s
            self.state_changed.emit(s)
        else:
            runtime_trace.trace_event(
                "core_state_dedupe",
                subsystem="state",
                severity=runtime_trace.DEBUG,
                request_id=request_id,
                payload={"state": s.name},
            )

    # --- Mode ---

    @property
    def mode(self) -> APRILMode:
        return self._mode

    def set_mode(self, m: APRILMode) -> None:
        if self._mode != m:
            self._mode = m
            self.mode_changed.emit(m)

    def escalate(self) -> None:
        """Step up one mode level."""
        order = [APRILMode.AMBIENT, APRILMode.FOCUS, APRILMode.TACTICAL]
        idx = order.index(self._mode)
        if idx < len(order) - 1:
            self.set_mode(order[idx + 1])

    def collapse(self) -> None:
        """Step down one mode level."""
        order = [APRILMode.AMBIENT, APRILMode.FOCUS, APRILMode.TACTICAL]
        idx = order.index(self._mode)
        if idx > 0:
            self.set_mode(order[idx - 1])

    # --- Profile ---

    @property
    def profile(self) -> PresenceProfile:
        return self._profile

    def set_profile(self, p: PresenceProfile) -> None:
        if self._profile != p:
            self._profile = p
            self.profile_changed.emit(p)

    # --- Corner ---

    @property
    def corner(self) -> Corner:
        return self._corner

    def set_corner(self, c: Corner) -> None:
        if self._corner != c:
            self._corner = c
            self.corner_changed.emit(c)
