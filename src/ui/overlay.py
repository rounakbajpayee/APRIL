"""
TransitionalOverlay — Focus mode surface.

Appears adjacent to the orb, expands softly, dismisses on Escape.
Designed to look like a flagship Microsoft Fluent Design UI (adapts to light/dark themes).
"""

from __future__ import annotations
import math
from PyQt6.QtCore import (
    Qt,
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
    QPoint,
    QSize,
    pyqtProperty,
    QRect,
)
from PyQt6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QBrush,
    QPainterPath,
    QRadialGradient,
    QLinearGradient,
)
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QApplication,
    QSizePolicy,
    QScrollArea,
    QLineEdit,
)

from .state import APRILCore, APRILState, APRILMode, Corner
from . import theme


class TransitionalOverlay(QWidget):
    """Focus mode panel — quick interactions, transcript, and dictation history."""

    def __init__(self, core: APRILCore, parent=None):
        super().__init__(parent)
        self._core = core
        self.bridge = None  # populated by bridge.attach_overlay
        self._anim_phase = 0.0
        self._history_cards: list[tuple[str, QFrame]] = []

        self._setup_window()
        self._build_ui()
        self._setup_animation()

        core.state_changed.connect(self._on_state_changed)
        core.mode_changed.connect(self._on_mode_changed)
        core.corner_changed.connect(self._reposition)

        self.hide()

    # ------------------------------------------------------------------ window

    def _setup_window(self):
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setFixedWidth(theme.OVERLAY_WIDTH)

    # ------------------------------------------------------------------ ui

    def _build_ui(self):
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setSpacing(10)

        # Header row
        hdr = QHBoxLayout()
        self._state_label = QLabel("Ready")
        self._state_label.setFont(theme.mono_font(10))
        hdr.addWidget(self._state_label)
        hdr.addStretch()

        self._mode_btn = QPushButton("Tactical ↗")
        self._mode_btn.setFixedHeight(24)
        self._mode_btn.setFont(theme.ui_font(10))
        self._mode_btn.clicked.connect(self._core.escalate)
        hdr.addWidget(self._mode_btn)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(_btn_ghost_style())
        close_btn.clicked.connect(self._collapse)
        hdr.addWidget(close_btn)
        self._layout.addLayout(hdr)

        self._div1 = _divider()
        self._layout.addWidget(self._div1)

        # Transcript area
        self._transcript = QLabel("—")
        self._transcript.setWordWrap(True)
        self._transcript.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._transcript.setFont(theme.ui_font(11))
        self._transcript.setMinimumHeight(50)
        self._layout.addWidget(self._transcript)

        self._div2 = _divider()
        self._layout.addWidget(self._div2)

        # Dictation History Title
        self._hist_title = QLabel("RECENT DICTATIONS")
        self._hist_title.setFont(theme.mono_font(9))
        self._layout.addWidget(self._hist_title)

        # Dictation History Panel (Persistent & Scrollable)
        self._history_scroll = QScrollArea()
        self._history_scroll.setFixedHeight(150)
        self._history_scroll.setWidgetResizable(True)
        self._history_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )

        self._history_container = QWidget()
        self._history_container.setStyleSheet("background: transparent;")
        self._history_layout = QVBoxLayout(self._history_container)
        self._history_layout.setContentsMargins(0, 0, 0, 0)
        self._history_layout.setSpacing(6)
        self._history_layout.addStretch()  # pushes cards to the top
        self._history_scroll.setWidget(self._history_container)

        self._layout.addWidget(self._history_scroll)

        # Status row
        self._div3 = _divider()
        self._layout.addWidget(self._div3)

        status_row = QHBoxLayout()
        self._task_label = QLabel("No active task")
        self._task_label.setFont(theme.mono_font(9))
        status_row.addWidget(self._task_label)
        status_row.addStretch()

        self._context_badge = _Badge("AMBIENT")
        status_row.addWidget(self._context_badge)
        self._layout.addLayout(status_row)

        # Quick-action buttons
        self._actions_layout = QHBoxLayout()
        self._actions_layout.setSpacing(8)
        self._action_buttons = []
        for label, tip in [
            ("Confirm", "Accept current suggestion"),
            ("Dismiss", "Dismiss"),
            ("Defer", "Resume later"),
        ]:
            btn = QPushButton(label)
            btn.setFixedHeight(28)
            btn.setToolTip(tip)
            btn.setFont(theme.ui_font(11))
            self._actions_layout.addWidget(btn)
            self._action_buttons.append(btn)
        self._layout.addLayout(self._actions_layout)

        # Apply initial theme styles
        self._apply_theme()
        self.adjustSize()

    # ------------------------------------------------------------------ theme

    def _apply_theme(self):
        is_light = theme.is_light_theme()
        txt_color = "rgb(30,30,42)" if is_light else "rgb(220,240,255)"
        state_color = "rgb(8,145,178)" if is_light else "rgb(34,211,238)"
        muted_color = "rgb(115,115,125)" if is_light else "rgb(113,113,122)"

        # Set stylesheet colors
        self._transcript.setStyleSheet(f"color: {txt_color}; background: transparent;")
        self._state_label.setStyleSheet(
            f"color: {state_color}; background: transparent;"
        )
        self._hist_title.setStyleSheet(
            f"color: {muted_color}; background: transparent;"
        )
        self._task_label.setStyleSheet(
            f"color: {muted_color}; background: transparent;"
        )

        # Re-style dividers
        div_css = _divider_style()
        self._div1.setStyleSheet(div_css)
        self._div2.setStyleSheet(div_css)
        self._div3.setStyleSheet(div_css)

        # Badge
        self._context_badge.setStyleSheet(_badge_style())

        # Style standard buttons
        self._mode_btn.setStyleSheet(_btn_ghost_style())
        for btn in self._action_buttons:
            if btn.text() == "Confirm":
                btn.setStyleSheet(_btn_solid_style())
            else:
                btn.setStyleSheet(_btn_ghost_style())

        # Re-style dictation history cards
        card_bg = "rgba(0,0,0,12)" if is_light else "rgba(255,255,255,8)"
        card_border = "rgba(0,0,0,18)" if is_light else "rgba(255,255,255,15)"
        for text, card in self._history_cards:
            card.setStyleSheet(
                f"QFrame {{ background: {card_bg}; border: 1px solid {card_border}; border-radius: 8px; }}"
            )
            edit = card.findChild(QLineEdit)
            if edit:
                edit.setStyleSheet(
                    f"QLineEdit {{ background: transparent; border: none; color: {txt_color}; }}"
                )
            for btn in card.findChildren(QPushButton):
                btn.setStyleSheet(_btn_icon_style())

        self.update()

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
        theme.refresh_theme()
        self._apply_theme()
        self._load_snapshot_history()

        self._reposition(self._core.corner)
        self.setWindowOpacity(0.0)
        self.show()
        self._opacity_anim.setStartValue(0.0)
        self._opacity_anim.setEndValue(1.0)
        self._opacity_anim.start()
        self._anim_timer.start()

    def _collapse(self):
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
        # Automatically append to list if it is a completed transcription
        if text and text.strip() and text != "—" and not text.endswith("…"):
            self._add_history_card(text)

    def set_task(self, text: str) -> None:
        self._task_label.setText(text or "No active task")

    # ------------------------------------------------------------------ dictation history

    def _load_snapshot_history(self):
        # Clear existing layout cards
        while self._history_layout.count() > 1:
            item = self._history_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._history_cards.clear()

        # Load from state engine snapshot
        try:
            from state_engine import load_snapshot

            snapshot = load_snapshot()
            domain_sums = snapshot.get("domain_summaries", {})
            april_sum = domain_sums.get("april", {})
            transcripts = april_sum.get("recent_transcripts", [])
            for t in transcripts:
                if t.strip():
                    self._add_history_card(t)
        except Exception as e:
            print(f"[Overlay] Failed to load history: {e}")

    def _add_history_card(self, text: str):
        if not text or not text.strip():
            return

        # De-duplicate identical history entries
        for existing_text, _ in self._history_cards:
            if existing_text == text:
                return

        card = QFrame()
        card_bg = "rgba(0,0,0,12)" if theme.is_light_theme() else "rgba(255,255,255,8)"
        card_border = (
            "rgba(0,0,0,18)" if theme.is_light_theme() else "rgba(255,255,255,15)"
        )
        card.setStyleSheet(
            f"QFrame {{ background: {card_bg}; border: 1px solid {card_border}; border-radius: 8px; }}"
        )
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(8, 4, 8, 4)
        card_layout.setSpacing(6)

        # Editable Text Box (Allows dictation corrections)
        edit = QLineEdit(text)
        edit.setFont(theme.ui_font(10))
        edit.setToolTip("Edit to correct dictation text")
        txt_color = "rgb(30,30,42)" if theme.is_light_theme() else "rgb(220,240,255)"
        edit.setStyleSheet(
            f"QLineEdit {{ background: transparent; border: none; color: {txt_color}; }}"
        )
        card_layout.addWidget(edit, 1)

        # Clipboard Copy Action
        copy_btn = QPushButton("📋")
        copy_btn.setFixedSize(20, 20)
        copy_btn.setToolTip("Copy to Clipboard")
        copy_btn.setStyleSheet(_btn_icon_style())
        copy_btn.clicked.connect(lambda: self._copy_text(edit.text()))
        card_layout.addWidget(copy_btn)

        # Retype Action (solves cursor focus loss issues)
        type_btn = QPushButton("✍️")
        type_btn.setFixedSize(20, 20)
        type_btn.setToolTip("Retype at current cursor")
        type_btn.setStyleSheet(_btn_icon_style())
        type_btn.clicked.connect(lambda: self._retype_text(edit.text()))
        card_layout.addWidget(type_btn)

        # Add to scroll layout (insert at top above the stretch)
        self._history_layout.insertWidget(0, card)
        self._history_cards.append((text, card))

        # Limit to 10 entries
        if len(self._history_cards) > 10:
            oldest_text, oldest_card = self._history_cards.pop(0)
            self._history_layout.removeWidget(oldest_card)
            oldest_card.deleteLater()

    def _copy_text(self, text: str):
        if text:
            QApplication.clipboard().setText(text)
            self._core.notification_passive.emit("Copied", "Copied to clipboard.")

    def _retype_text(self, text: str):
        if text and self.bridge is not None:
            self.bridge.retype_text(text)

    # ------------------------------------------------------------------ layout

    def _reposition(self, corner: Corner):
        screen = QApplication.primaryScreen().availableGeometry()
        m = theme.CORNER_MARGIN
        ow = self.width()
        oh = self.height()
        orb = theme.ORB_SIZE + 12 * 2
        gap = 8

        match corner:
            case Corner.BOTTOM_RIGHT:
                x = screen.right() - ow - m
                y = screen.bottom() - oh - m - orb - gap
            case Corner.BOTTOM_LEFT:
                x = screen.left() + m
                y = screen.bottom() - oh - m - orb - gap
            case Corner.TOP_RIGHT:
                x = screen.right() - ow - m
                y = screen.top() + m + orb + gap
            case Corner.TOP_LEFT:
                x = screen.left() + m
                y = screen.top() + m + orb + gap
        self.move(x, y)

    # ------------------------------------------------------------------ painting

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 16, 16)

        p.setClipPath(path)
        # Dynamic Fluent System Theme adaptation
        p.fillRect(0, 0, self.width(), self.height(), theme.BG_BASE)

        grad = QLinearGradient(0, 0, 0, 60)
        grad.setColorAt(
            0,
            (
                QColor(255, 255, 255, 18)
                if not theme.is_light_theme()
                else QColor(0, 0, 0, 8)
            ),
        )
        grad.setColorAt(1, QColor(0, 0, 0, 0))
        p.fillRect(0, 0, self.width(), 60, grad)

        p.setClipping(False)
        pen = QPen(theme.BORDER)
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
            APRILState.DORMANT: "Ready",
            APRILState.LISTENING: "Listening…",
            APRILState.THINKING: "Processing…",
            APRILState.SPEAKING: "Speaking",
            APRILState.ACTING: "Acting…",
            APRILState.WARNING: "Warning",
            APRILState.ERROR: "Error",
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
    line.setStyleSheet(_divider_style())
    return line


def _divider_style() -> str:
    is_light = theme.is_light_theme()
    c = "rgba(0, 0, 0, 20)" if is_light else "rgba(255, 255, 255, 20)"
    return f"color: {c};"


class _Badge(QLabel):

    def __init__(self, text: str):
        super().__init__(text)
        self.setStyleSheet(_badge_style())


def _badge_style() -> str:
    is_light = theme.is_light_theme()
    color = "rgb(8,145,178)" if is_light else "rgb(34,211,238)"
    bg = "rgba(8,145,178,20)" if is_light else "rgba(34,211,238,20)"
    border = (
        "1px solid rgba(8,145,178,40)" if is_light else "1px solid rgba(34,211,238,40)"
    )
    return f"""
    color: {color}; background: {bg};
    border: {border}; border-radius: 4px;
    font-size: 9px; font-family: 'Segoe UI Variable Display', Consolas;
    padding: 2px 5px;
    """


def _btn_solid_style() -> str:
    return """
    QPushButton {
        background: rgba(34,211,238,180);
        color: rgb(10,10,20);
        border: none;
        border-radius: 6px;
        font-size: 11px;
        padding: 0 10px;
    }
    QPushButton:hover { background: rgba(34,211,238,220); }
    QPushButton:pressed { background: rgba(34,211,238,255); }
    """


def _btn_ghost_style() -> str:
    is_light = theme.is_light_theme()
    bg = "rgba(0,0,0,8)" if is_light else "rgba(255,255,255,8)"
    border = (
        "1px solid rgba(0,0,0,20)" if is_light else "1px solid rgba(255,255,255,20)"
    )
    color = "rgb(80,80,95)" if is_light else "rgb(180,200,220)"
    hover_bg = "rgba(0,0,0,15)" if is_light else "rgba(255,255,255,15)"
    hover_color = "rgb(30,30,42)" if is_light else "rgb(220,240,255)"
    return f"""
    QPushButton {{
        background: {bg};
        color: {color};
        border: {border};
        border-radius: 6px;
        font-size: 11px;
        padding: 0 10px;
    }}
    QPushButton:hover {{ background: {hover_bg}; color: {hover_color}; }}
    QPushButton:pressed {{ background: {bg}; }}
    """


def _btn_icon_style() -> str:
    is_light = theme.is_light_theme()
    color = "rgb(115,115,125)" if is_light else "rgb(140,160,180)"
    hover_color = "rgb(8,145,178)" if is_light else "rgb(34,211,238)"
    return f"""
    QPushButton {{
        background: transparent;
        color: {color};
        border: none;
        font-size: 11px;
    }}
    QPushButton:hover {{
        color: {hover_color};
    }}
    """
