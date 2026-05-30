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
    QCursor,
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
        # Top-level layout has margins to allow the drop shadow to render without clipping
        self._top_layout = QVBoxLayout(self)
        self._top_layout.setContentsMargins(12, 12, 12, 12)
        self._top_layout.setSpacing(0)

        # Base Frame that holds all content and gets the drop shadow
        self._base_frame = QFrame()
        self._base_frame.setObjectName("OverlayBase")
        
        # Apply drop shadow
        shadow = theme.create_shadow(QColor(0, 0, 0, 75), radius=16, dy=4)
        if shadow:
            self._base_frame.setGraphicsEffect(shadow)

        self._layout = QVBoxLayout(self._base_frame)
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
        self._mode_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._mode_btn.clicked.connect(self._core.escalate)
        hdr.addWidget(self._mode_btn)

        close_btn = QPushButton()
        close_btn.setFixedSize(24, 24)
        close_btn.setIcon(theme.get_icon("fa6s.xmark", size=10))
        close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
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
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            self._actions_layout.addWidget(btn)
            self._action_buttons.append(btn)
        self._layout.addLayout(self._actions_layout)

        self._top_layout.addWidget(self._base_frame)

        # Apply initial theme styles
        self._apply_theme()
        self.adjustSize()

    # ------------------------------------------------------------------ theme

    def _apply_theme(self):
        is_light = theme.is_light_theme()
        txt_color = "rgb(24,24,27)" if is_light else "rgb(243,243,243)"
        state_color = "rgb(0,120,212)" if is_light else "rgb(96,205,255)"
        muted_color = "rgb(113,113,122)" if is_light else "rgb(161,161,170)"
        icon_c = "rgb(82, 82, 91)" if is_light else "rgb(161, 161, 170)"

        # Style base frame background and border mimicking Windows 11 acrylic
        self._base_frame.setStyleSheet(f"""
            QFrame#OverlayBase {{
                background: {theme.BG_BASE.name()};
                border: 1px solid {theme.BORDER.name()};
                border-radius: 12px;
            }}
        """)

        # Set stylesheet colors
        self._transcript.setStyleSheet(f"color: {txt_color}; background: transparent;")
        self._state_label.setStyleSheet(
            f"color: {state_color}; background: transparent;"
        )
        self._hist_title.setStyleSheet(
            f"color: {muted_color}; background: transparent; font-weight: 600; letter-spacing: 0.5px;"
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
        card_bg = "rgba(0,0,0,10)" if is_light else "rgba(255,255,255,8)"
        card_border = "rgba(0,0,0,16)" if is_light else "rgba(255,255,255,14)"
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
                if btn.toolTip() == "Copy to Clipboard":
                    btn.setIcon(theme.get_icon("fa6s.copy", color=icon_c))
                elif btn.toolTip() == "Retype at current cursor":
                    btn.setIcon(theme.get_icon("fa6s.keyboard", color=icon_c))

        self.update()

    # ------------------------------------------------------------------ animation

    def _setup_animation(self):
        self._opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self._opacity_anim.setDuration(theme.TRANSITION_NORMAL)
        self._opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._pos_anim = QPropertyAnimation(self, b"pos")
        self._pos_anim.setDuration(theme.TRANSITION_NORMAL)
        self._pos_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

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

        # Calculate slide-in positions
        target_pos = self._get_reposition_pos(self._core.corner)
        
        # Slide slightly from the orb direction (up or down by 20px)
        is_bottom = self._core.corner in (Corner.BOTTOM_RIGHT, Corner.BOTTOM_LEFT)
        offset_y = 20 if is_bottom else -20
        start_pos = target_pos + QPoint(0, offset_y)
        
        self.move(start_pos)
        self.setWindowOpacity(0.0)
        self.show()

        # Animate opacity
        self._opacity_anim.setStartValue(0.0)
        self._opacity_anim.setEndValue(1.0)
        self._opacity_anim.start()

        # Animate position (slide-in)
        self._pos_anim.setStartValue(start_pos)
        self._pos_anim.setEndValue(target_pos)
        self._pos_anim.start()

        self._anim_timer.start()

    def _collapse(self):
        if not self.isVisible():
            return
        if self._opacity_anim.state() == QPropertyAnimation.State.Running:
            return
            
        # Reposition to slide-out
        target_pos = self.pos()
        is_bottom = self._core.corner in (Corner.BOTTOM_RIGHT, Corner.BOTTOM_LEFT)
        offset_y = 20 if is_bottom else -20
        end_pos = target_pos + QPoint(0, offset_y)

        self._opacity_anim.setStartValue(self.windowOpacity())
        self._opacity_anim.setEndValue(0.0)
        
        self._pos_anim.setStartValue(target_pos)
        self._pos_anim.setEndValue(end_pos)
        
        self._opacity_anim.finished.connect(self._on_collapse_done)
        self._opacity_anim.start()
        self._pos_anim.start()

    def _on_collapse_done(self):
        self.hide()
        self._anim_timer.stop()
        try:
            self._opacity_anim.finished.disconnect(self._on_collapse_done)
        except Exception:
            pass
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
        card.setObjectName("HistoryCard")
        is_light = theme.is_light_theme()
        card_bg = "rgba(0,0,0,10)" if is_light else "rgba(255,255,255,8)"
        card_border = "rgba(0,0,0,16)" if is_light else "rgba(255,255,255,14)"
        card.setStyleSheet(
            f"QFrame#HistoryCard {{ background: {card_bg}; border: 1px solid {card_border}; border-radius: 8px; }}"
        )
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(10, 6, 10, 6)
        card_layout.setSpacing(8)

        # Editable Text Box (Allows dictation corrections)
        edit = QLineEdit(text)
        edit.setFont(theme.ui_font(10))
        edit.setToolTip("Edit to correct dictation text")
        txt_color = "rgb(24,24,27)" if is_light else "rgb(243,243,243)"
        edit.setStyleSheet(
            f"QLineEdit {{ background: transparent; border: none; color: {txt_color}; }}"
        )
        card_layout.addWidget(edit, 1)

        # Action buttons container
        icon_c = "rgb(82, 82, 91)" if is_light else "rgb(161, 161, 170)"

        # Clipboard Copy Action
        copy_btn = QPushButton()
        copy_btn.setFixedSize(20, 20)
        copy_btn.setToolTip("Copy to Clipboard")
        copy_btn.setIcon(theme.get_icon("fa6s.copy", color=icon_c))
        copy_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        copy_btn.setStyleSheet(_btn_icon_style())
        copy_btn.clicked.connect(lambda: self._copy_text(edit.text()))
        card_layout.addWidget(copy_btn)

        # Retype Action (solves cursor focus loss issues)
        type_btn = QPushButton()
        type_btn.setFixedSize(20, 20)
        type_btn.setToolTip("Retype at current cursor")
        type_btn.setIcon(theme.get_icon("fa6s.keyboard", color=icon_c))
        type_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
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

    def _get_reposition_pos(self, corner: Corner) -> QPoint:
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
        return QPoint(x, y)

    def _reposition(self, corner: Corner):
        if self.isVisible() and self._pos_anim.state() != QPropertyAnimation.State.Running:
            self.move(self._get_reposition_pos(corner))

    # ------------------------------------------------------------------ painting

    def paintEvent(self, _event):
        # We perform background painting inside _base_frame via stylesheet or custom drawing
        # and keep the top-level QWidget background fully translucent to prevent shadow clipping.
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Just clear area
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
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
    c = "rgba(0, 0, 0, 16)" if is_light else "rgba(255, 255, 255, 14)"
    return f"color: {c}; background-color: {c}; border: none; height: 1px;"


class _Badge(QLabel):

    def __init__(self, text: str):
        super().__init__(text)
        self.setStyleSheet(_badge_style())


def _badge_style() -> str:
    is_light = theme.is_light_theme()
    color = "rgb(0, 120, 212)" if is_light else "rgb(96, 205, 255)"
    bg = "rgba(0, 120, 212, 20)" if is_light else "rgba(96, 205, 255, 20)"
    border = (
        "1px solid rgba(0, 120, 212, 40)" if is_light else "1px solid rgba(96, 205, 255, 40)"
    )
    return f"""
    color: {color}; background: {bg};
    border: {border}; border-radius: 4px;
    font-size: 9px; font-family: 'Segoe UI Variable Small', Consolas;
    font-weight: 600;
    padding: 2px 6px;
    """


def _btn_solid_style() -> str:
    is_light = theme.is_light_theme()
    bg = "rgb(0, 120, 212)" if is_light else "rgb(0, 120, 212)"
    hover_bg = "rgb(0, 99, 177)"
    text_color = "white"
    return f"""
    QPushButton {{
        background: {bg};
        color: {text_color};
        border: none;
        border-radius: 6px;
        font-size: 11px;
        font-family: 'Segoe UI Variable Text';
        font-weight: 600;
        padding: 0 14px;
    }}
    QPushButton:hover {{ background: {hover_bg}; }}
    QPushButton:pressed {{ background: {bg}; }}
    """


def _btn_ghost_style() -> str:
    is_light = theme.is_light_theme()
    bg = "rgba(0,0,0,6)" if is_light else "rgba(255,255,255,6)"
    border = (
        "1px solid rgba(0,0,0,16)" if is_light else "1px solid rgba(255,255,255,14)"
    )
    color = "rgb(55,55,65)" if is_light else "rgb(200,220,240)"
    hover_bg = "rgba(0,0,0,12)" if is_light else "rgba(255,255,255,12)"
    hover_color = "rgb(24,24,27)" if is_light else "rgb(243,243,243)"
    return f"""
    QPushButton {{
        background: {bg};
        color: {color};
        border: {border};
        border-radius: 6px;
        font-size: 11px;
        font-family: 'Segoe UI Variable Text';
        padding: 0 12px;
    }}
    QPushButton:hover {{ background: {hover_bg}; color: {hover_color}; }}
    QPushButton:pressed {{ background: {bg}; }}
    """


def _btn_icon_style() -> str:
    is_light = theme.is_light_theme()
    color = "rgb(113,113,122)" if is_light else "rgb(161,161,170)"
    hover_color = "rgb(0,120,212)" if is_light else "rgb(96,205,255)"
    hover_bg = "rgba(0,0,0,8)" if is_light else "rgba(255,255,255,8)"
    return f"""
    QPushButton {{
        background: transparent;
        color: {color};
        border: none;
        border-radius: 4px;
    }}
    QPushButton:hover {{
        color: {hover_color};
        background: {hover_bg};
    }}
    """

