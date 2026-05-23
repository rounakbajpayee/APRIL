"""
TransitionalOverlay — Focus mode surface.

Appears adjacent to the orb, expands softly, dismisses on Escape or
clicking outside.  Never steals focus from the active application.
"""
from __future__ import annotations
import math
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve,
    QPoint, QSize, pyqtProperty, QRect
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPainterPath,
    QRadialGradient, QLinearGradient
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QApplication, QSizePolicy
)

from .state import APRILCore, APRILState, APRILMode, Corner
from . import theme


class TransitionalOverlay(QWidget):
    """Focus mode panel — quick interactions and transcription."""

    def __init__(self, core: APRILCore, parent=None):
        super().__init__(parent)
        self._core = core
        self._anim_phase = 0.0

        self._setup_window()
        self._build_ui()
        self._setup_animation()

        core.state_changed.connect(self._on_state_changed)
        core.mode_changed.connect(self._on_mode_changed)
        core.corner_changed.connect(self._reposition)

        self.hide()

    # ------------------------------------------------------------------ window

    def _setup_window(self):
        # FIX-02: opaque background — no WA_TranslucentBackground
        self.setStyleSheet("background: rgb(10, 10, 20);")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setFixedWidth(theme.OVERLAY_WIDTH)

    # ------------------------------------------------------------------ ui

    def _build_ui(self):
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setSpacing(12)

        # Header row
        hdr = QHBoxLayout()
        self._state_label = QLabel("Ready")
        self._state_label.setStyleSheet(
            "color: rgb(34,211,238); font-size: 11px; font-family: 'JetBrains Mono', Consolas;")
        hdr.addWidget(self._state_label)
        hdr.addStretch()

        self._mode_btn = QPushButton("Tactical ↗")
        self._mode_btn.setFixedHeight(24)
        self._mode_btn.setStyleSheet(_BTN_STYLE_GHOST)
        self._mode_btn.clicked.connect(self._core.escalate)
        hdr.addWidget(self._mode_btn)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(_BTN_STYLE_GHOST)
        close_btn.clicked.connect(self._collapse)
        hdr.addWidget(close_btn)
        self._layout.addLayout(hdr)

        self._layout.addWidget(_divider())

        # Transcript area
        self._transcript = QLabel("—")
        self._transcript.setWordWrap(True)
        self._transcript.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._transcript.setStyleSheet(
            "color: rgb(220,240,255); font-size: 12px; "
            "line-height: 1.6; font-family: 'Inter', 'Segoe UI';"
        )
        self._transcript.setMinimumHeight(60)
        self._layout.addWidget(self._transcript)

        # Status row
        self._layout.addWidget(_divider())
        status_row = QHBoxLayout()

        self._task_label = QLabel("No active task")
        self._task_label.setStyleSheet(
            "color: rgb(113,113,122); font-size: 10px; font-family: 'JetBrains Mono', Consolas;")
        status_row.addWidget(self._task_label)
        status_row.addStretch()

        self._context_badge = _Badge("AMBIENT")
        status_row.addWidget(self._context_badge)
        self._layout.addLayout(status_row)

        # Quick-action buttons
        actions_row = QHBoxLayout()
        actions_row.setSpacing(8)
        for label, tip in [("Confirm", "Accept current suggestion"),
                            ("Dismiss", "Dismiss"),
                            ("Defer",   "Resume later")]:
            btn = QPushButton(label)
            btn.setFixedHeight(28)
            btn.setToolTip(tip)
            btn.setStyleSheet(_BTN_STYLE_SOLID if label == "Confirm" else _BTN_STYLE_GHOST)
            actions_row.addWidget(btn)
        self._layout.addLayout(actions_row)

        self.adjustSize()

    # ------------------------------------------------------------------ animation

    def _setup_animation(self):
        self._opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self._opacity_anim.setDuration(theme.TRANSITION_NORMAL)
        self._opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(theme.ANIMATION_INTERVAL)
        self._anim_timer.timeout.connect(self._tick)

    def _tick(self):
        self._anim_phase = (self._anim_phase + 0.015) % 1.0
        self.update()

    # ------------------------------------------------------------------ public API

    def expand(self):
        self._reposition(self._core.corner)
        self.setWindowOpacity(0.0)
        self.show()
        self._opacity_anim.setStartValue(0.0)
        self._opacity_anim.setEndValue(1.0)
        self._opacity_anim.start()
        self._anim_timer.start()

    def _collapse(self):
        # FIX-09: guard against re-entrant collapse
        if not self.isVisible():
            return
        if self._opacity_anim.state() == QPropertyAnimation.State.Running:
            return
        self._opacity_anim.setStartValue(self.windowOpacity())
        self._opacity_anim.setEndValue(0.0)
        self._opacity_anim.finished.connect(self._on_collapse_done)
        self._opacity_anim.start()

    def _on_collapse_done(self):
        self.hide()
        self._anim_timer.stop()
        self._opacity_anim.finished.disconnect(self._on_collapse_done)
        self._core.set_mode(APRILMode.AMBIENT)

    # ------------------------------------------------------------------ public data API

    def set_transcript(self, text: str) -> None:
        """Called by APRILBridge to push live STT/response text."""
        self._transcript.setText(text or "—")

    def set_task(self, text: str) -> None:
        self._task_label.setText(text or "No active task")

    # ------------------------------------------------------------------ layout

    def _reposition(self, corner: Corner):
        screen = QApplication.primaryScreen().availableGeometry()
        m  = theme.CORNER_MARGIN
        ow = self.width()
        oh = self.height()
        orb = theme.ORB_SIZE + 12 * 2
        gap = 8

        match corner:
            case Corner.BOTTOM_RIGHT:
                x = screen.right()  - ow - m
                y = screen.bottom() - oh - m - orb - gap
            case Corner.BOTTOM_LEFT:
                x = screen.left()   + m
                y = screen.bottom() - oh - m - orb - gap
            case Corner.TOP_RIGHT:
                x = screen.right()  - ow - m
                y = screen.top()    + m + orb + gap
            case Corner.TOP_LEFT:
                x = screen.left()   + m
                y = screen.top()    + m + orb + gap
        self.move(x, y)

    # ------------------------------------------------------------------ painting

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 16, 16)

        p.setClipPath(path)
        p.fillRect(0, 0, self.width(), self.height(),
                   QColor(10, 10, 20, 210))

        grad = QLinearGradient(0, 0, 0, 60)
        grad.setColorAt(0, QColor(255, 255, 255, 18))
        grad.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(0, 0, self.width(), 60, grad)

        p.setClipping(False)
        pen = QPen(QColor(255, 255, 255, 30))
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        p.end()

    # ------------------------------------------------------------------ keyboard

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._collapse()
        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------------------ slots

    def _on_state_changed(self, state: APRILState):
        labels = {
            APRILState.DORMANT:   "Ready",
            APRILState.LISTENING: "Listening…",
            APRILState.THINKING:  "Processing…",
            APRILState.SPEAKING:  "Speaking",
            APRILState.ACTING:    "Acting…",
            APRILState.WARNING:   "Warning",
            APRILState.ERROR:     "Error",
        }
        self._state_label.setText(labels.get(state, "—"))

    def _on_mode_changed(self, mode: APRILMode):
        if mode == APRILMode.FOCUS:
            self.expand()
        elif mode == APRILMode.AMBIENT and self.isVisible():
            self._collapse()


# ------------------------------------------------------------------ helpers

def _divider() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("color: rgba(255,255,255,20);")
    return line


class _Badge(QLabel):
    def __init__(self, text: str):
        super().__init__(text)
        self.setStyleSheet(
            "color: rgb(34,211,238); background: rgba(34,211,238,20); "
            "border: 1px solid rgba(34,211,238,40); border-radius: 4px; "
            "font-size: 9px; font-family: 'JetBrains Mono', Consolas; "
            "padding: 1px 5px;"
        )


_BTN_STYLE_SOLID = """
QPushButton {
    background: rgba(34,211,238,180);
    color: rgb(10,10,20);
    border: none;
    border-radius: 6px;
    font-size: 11px;
    padding: 0 10px;
    font-family: 'Inter', 'Segoe UI';
}
QPushButton:hover { background: rgba(34,211,238,220); }
QPushButton:pressed { background: rgba(34,211,238,255); }
"""

_BTN_STYLE_GHOST = """
QPushButton {
    background: rgba(255,255,255,8);
    color: rgb(180,200,220);
    border: 1px solid rgba(255,255,255,20);
    border-radius: 6px;
    font-size: 11px;
    padding: 0 10px;
    font-family: 'Inter', 'Segoe UI';
}
QPushButton:hover { background: rgba(255,255,255,15); color: rgb(220,240,255); }
QPushButton:pressed { background: rgba(255,255,255,5); }
"""
