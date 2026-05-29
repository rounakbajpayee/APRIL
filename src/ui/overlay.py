"""
TransitionalOverlay — Focus mode panel.

Design language (Fluent 2 / WinUI 3)
─────────────────────────────────────
• Acrylic frosted-glass background, adapts to light / dark system theme.
• Header: APRIL brand mark, live-state badge with icon, close button.
• Transcript area: large, clear, monospaced live dictation feed.
• Dictation history: compact list — no borders, hover-reveals Copy + Type
  action buttons.  Each entry is a QLineEdit so the user can manually
  correct STT errors.
• Action bar: Confirm (accent), Dismiss and Defer (ghost), Tactical ↗.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import (
    Qt,
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
)
from PyQt6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QBrush,
    QPainterPath,
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
    QScrollArea,
    QLineEdit,
    QSizePolicy,
)

from .state import APRILCore, APRILState, APRILMode, Corner
from . import theme

# ── State label + icon mapping ──────────────────────────────────────────────

_STATE_META: dict[APRILState, tuple[str, str]] = {
    APRILState.DORMANT: ("Ready", "fa6s.circle_dot"),
    APRILState.LISTENING: ("Listening…", "fa6s.microphone"),
    APRILState.THINKING: ("Processing…", "fa6s.brain"),
    APRILState.SPEAKING: ("Speaking", "fa6s.volume_high"),
    APRILState.ACTING: ("Acting…", "fa6s.bolt"),
    APRILState.WARNING: ("Warning", "fa6s.triangle_exclamation"),
    APRILState.ERROR: ("Error", "fa6s.circle_xmark"),
}

_STATE_ACCENT: dict[APRILState, tuple[str, str]] = {
    # (dark-mode colour, light-mode colour)
    APRILState.DORMANT: ("rgb(100,116,139)", "rgb(148,163,184)"),
    APRILState.LISTENING: ("rgb(56,189,248)", "rgb(8,145,178)"),
    APRILState.THINKING: ("rgb(56,189,248)", "rgb(8,145,178)"),
    APRILState.SPEAKING: ("rgb(56,189,248)", "rgb(8,145,178)"),
    APRILState.ACTING: ("rgb(167,139,250)", "rgb(124,58,237)"),
    APRILState.WARNING: ("rgb(251,191,36)", "rgb(180,130,10)"),
    APRILState.ERROR: ("rgb(248,113,113)", "rgb(185,28,28)"),
}


# ── History card widget ──────────────────────────────────────────────────────


class _HistoryCard(QWidget):
    """
    A single dictation entry.

    • Looks like a plain text row by default — no frame border, no shadow.
    • On mouse-enter: subtle background tint + Copy and Type buttons slide in.
    • The text is an editable QLineEdit so the user can correct STT errors.
    """

    def __init__(
        self,
        text: str,
        on_copy,
        on_retype,
        index: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_copy = on_copy
        self._on_retype = on_retype
        self._index = index  # 0 = newest (brighter), higher = older (dimmer)
        self._hovered = False
        self.setMouseTracking(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 7, 10, 7)
        layout.setSpacing(6)

        # Recency dot — brightness indicates age (newest = bright cyan)
        self._dot = QLabel("●")
        self._dot.setFixedWidth(10)
        self._dot.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._dot)

        # Editable text field — styled as a plain label until focused
        self._edit = QLineEdit(text)
        self._edit.setFrame(False)
        self._edit.setFont(theme.ui_font(11))
        self._edit.setCursor(QCursor(Qt.CursorShape.IBeamCursor))
        layout.addWidget(self._edit, 1)

        # Action buttons — hidden until hover
        self._copy_btn = QPushButton()
        self._copy_btn.setIcon(theme.get_icon("fa6s.copy"))
        self._copy_btn.setToolTip("Copy to clipboard")
        self._copy_btn.setFixedSize(26, 26)
        self._copy_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._copy_btn.clicked.connect(lambda: on_copy(self._edit.text()))

        self._type_btn = QPushButton()
        self._type_btn.setIcon(theme.get_icon("fa6s.keyboard"))
        self._type_btn.setToolTip("Type at active cursor")
        self._type_btn.setFixedSize(26, 26)
        self._type_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._type_btn.clicked.connect(lambda: on_retype(self._edit.text()))

        layout.addWidget(self._copy_btn)
        layout.addWidget(self._type_btn)

        self._copy_btn.setVisible(False)
        self._type_btn.setVisible(False)

        self.apply_theme()

    # -- hover handling ------------------------------------------------

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        self._copy_btn.setVisible(True)
        self._type_btn.setVisible(True)
        self._refresh_style()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        # Delay the hide check — allows mouse to move to child buttons
        QTimer.singleShot(60, self._maybe_hide)
        super().leaveEvent(event)

    def _maybe_hide(self) -> None:
        global_pos = QCursor.pos()
        local_pos = self.mapFromGlobal(global_pos)
        if not self.rect().contains(local_pos):
            self._hovered = False
            self._copy_btn.setVisible(False)
            self._type_btn.setVisible(False)
            self._refresh_style()

    # -- theming -------------------------------------------------------

    def apply_theme(self) -> None:
        self._refresh_style()

    def _refresh_style(self) -> None:
        light = theme.is_light_theme()

        # Recency-aware dot color: newest = accent, older = muted
        if self._index == 0:
            dot_color = "rgb(8,145,178)" if light else "rgb(56,189,248)"
        elif self._index < 3:
            dot_color = "rgb(148,163,184)" if light else "rgb(100,116,139)"
        else:
            dot_color = "rgb(203,213,225)" if light else "rgb(51,65,85)"

        self._dot.setStyleSheet(
            f"color: {dot_color}; font-size: 8px; background: transparent; border: none;"
        )

        txt = "rgb(15,23,42)" if light else "rgb(220,230,248)"
        accent = "rgb(8,145,178)" if light else "rgb(56,189,248)"
        hover_bg = "rgba(0,0,0,5)" if light else "rgba(255,255,255,6)"

        self.setStyleSheet(
            f"QWidget {{ background: {'transparent' if not self._hovered else hover_bg}; "
            f"border-radius: 8px; }}"
        )
        self._edit.setStyleSheet(
            f"QLineEdit {{ background: transparent; border: none; color: {txt}; "
            f"font-size: 11px; font-family: 'Segoe UI Variable Display', 'Segoe UI'; }}"
            f"QLineEdit:focus {{ border-bottom: 1px solid {accent}; }}"
        )

        btn_style = f"""
QPushButton {{
    background: transparent;
    border: none;
    border-radius: 5px;
    padding: 3px;
}}
QPushButton:hover {{
    background: {'rgba(0,0,0,8)' if light else 'rgba(255,255,255,10)'};
}}
QPushButton:pressed {{
    background: {'rgba(0,0,0,14)' if light else 'rgba(255,255,255,16)'};
}}
"""
        self._copy_btn.setStyleSheet(btn_style)
        self._type_btn.setStyleSheet(btn_style)

        # Refresh icon colors
        icon_color = "rgb(71,85,105)" if light else "rgb(148,163,184)"
        self._copy_btn.setIcon(theme.get_icon("fa6s.copy", color=icon_color))
        self._type_btn.setIcon(theme.get_icon("fa6s.keyboard", color=icon_color))

    def get_text(self) -> str:
        return self._edit.text()


# ── Main overlay widget ──────────────────────────────────────────────────────


class TransitionalOverlay(QWidget):
    """Focus mode floating panel."""

    def __init__(self, core: APRILCore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._core = core
        self.bridge = None  # set by APRILBridge.attach_overlay()
        self._anim_phase: float = 0.0
        self._history_cards: list[_HistoryCard] = []

        self._setup_window()
        self._build_ui()
        self._setup_animation()

        core.state_changed.connect(self._on_state_changed)
        core.mode_changed.connect(self._on_mode_changed)
        core.corner_changed.connect(self._reposition)

        self.hide()

    # ------------------------------------------------------------------ window

    def _setup_window(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setFixedWidth(theme.OVERLAY_WIDTH)

    # ------------------------------------------------------------------ UI construction

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────
        hdr = QWidget()
        hdr.setObjectName("overlay_header")
        hdr.setFixedHeight(52)
        hdr.setStyleSheet("background: transparent;")
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(16, 0, 12, 0)
        hdr_lay.setSpacing(10)

        # Brand mark icon
        self._brand_icon = QLabel()
        self._brand_icon.setFixedSize(20, 20)
        hdr_lay.addWidget(self._brand_icon)

        # APRIL wordmark
        self._brand_lbl = QLabel("APRIL")
        self._brand_lbl.setFont(theme.ui_font(12))
        hdr_lay.addWidget(self._brand_lbl)

        hdr_lay.addStretch()

        # Live state badge (icon + label)
        self._state_icon_lbl = QLabel()
        self._state_icon_lbl.setFixedSize(14, 14)
        hdr_lay.addWidget(self._state_icon_lbl)

        self._state_lbl = QLabel("Ready")
        self._state_lbl.setFont(theme.mono_font(9))
        hdr_lay.addWidget(self._state_lbl)

        # Tactical escalate button
        self._escalate_btn = QPushButton()
        self._escalate_btn.setIcon(theme.get_icon("fa6s.arrow_up_right_from_square"))
        self._escalate_btn.setToolTip("Open Tactical workspace")
        self._escalate_btn.setFixedSize(28, 28)
        self._escalate_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._escalate_btn.clicked.connect(self._core.escalate)
        hdr_lay.addWidget(self._escalate_btn)

        # Close
        self._close_btn = QPushButton()
        self._close_btn.setIcon(theme.get_icon("fa6s.xmark"))
        self._close_btn.setToolTip("Dismiss (Esc)")
        self._close_btn.setFixedSize(28, 28)
        self._close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._close_btn.clicked.connect(self._collapse)
        hdr_lay.addWidget(self._close_btn)

        root.addWidget(hdr)

        # ── Divider ───────────────────────────────────────────────────────
        self._div_top = _HDivider()
        root.addWidget(self._div_top)

        # ── Content area (padded) ─────────────────────────────────────────
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(16, 14, 16, 14)
        content_lay.setSpacing(12)

        # Transcript — large, clear, monospaced
        self._transcript = QLabel("—")
        self._transcript.setWordWrap(True)
        self._transcript.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._transcript.setFont(theme.ui_font(13))
        self._transcript.setMinimumHeight(52)
        self._transcript.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        content_lay.addWidget(self._transcript)

        # History section header
        hist_hdr = QHBoxLayout()
        hist_hdr.setSpacing(6)

        hist_icon = QLabel()
        hist_icon.setFixedSize(12, 12)
        try:
            import qtawesome as qta

            light = theme.is_light_theme()
            ic = qta.icon("fa6s.clock_rotate_left", color="rgb(100,116,139)", scale_factor=0.9)
            hist_icon.setPixmap(ic.pixmap(12, 12))
        except Exception:
            pass
        hist_hdr.addWidget(hist_icon)

        self._hist_title = QLabel("RECENT")
        self._hist_title.setFont(theme.label_font(8))
        hist_hdr.addWidget(self._hist_title)
        hist_hdr.addStretch()

        content_lay.addLayout(hist_hdr)

        # History scroll area
        self._history_scroll = QScrollArea()
        self._history_scroll.setFixedHeight(160)
        self._history_scroll.setWidgetResizable(True)
        self._history_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:vertical { width: 4px; background: transparent; }"
            "QScrollBar::handle:vertical { background: rgba(148,163,184,80); border-radius: 2px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        self._history_container = QWidget()
        self._history_container.setStyleSheet("background: transparent;")
        self._history_layout = QVBoxLayout(self._history_container)
        self._history_layout.setContentsMargins(0, 0, 0, 0)
        self._history_layout.setSpacing(1)
        self._history_layout.addStretch()
        self._history_scroll.setWidget(self._history_container)
        content_lay.addWidget(self._history_scroll)

        root.addWidget(content)

        # ── Bottom divider + action bar ────────────────────────────────────
        self._div_bot = _HDivider()
        root.addWidget(self._div_bot)

        actions = QWidget()
        actions.setStyleSheet("background: transparent;")
        act_lay = QHBoxLayout(actions)
        act_lay.setContentsMargins(14, 10, 14, 14)
        act_lay.setSpacing(8)

        # Task label
        self._task_lbl = QLabel("No active task")
        self._task_lbl.setFont(theme.mono_font(9))
        act_lay.addWidget(self._task_lbl)
        act_lay.addStretch()

        # Action buttons
        self._action_btns: list[QPushButton] = []
        for label, icon_name, is_accent in [
            ("Confirm", "fa6s.circle_check", True),
            ("Dismiss", "fa6s.ban", False),
            ("Defer", "fa6s.clock", False),
        ]:
            btn = QPushButton(label)
            btn.setIcon(theme.get_icon(icon_name))
            btn.setFixedHeight(30)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setFont(theme.ui_font(11))
            act_lay.addWidget(btn)
            self._action_btns.append(btn)

        root.addWidget(actions)

        # Apply initial theme
        self._apply_theme()
        self.adjustSize()

    # ------------------------------------------------------------------ theme

    def _apply_theme(self) -> None:
        light = theme.is_light_theme()
        txt = "rgb(15,23,42)" if light else "rgb(220,230,248)"
        muted = "rgb(100,116,139)" if light else "rgb(100,116,139)"
        accent = "rgb(8,145,178)" if light else "rgb(56,189,248)"
        brand_color = accent

        # Brand icon + label
        try:
            import qtawesome as qta

            ic = qta.icon("fa6s.circle_dot", color=brand_color, scale_factor=1.0)
            self._brand_icon.setPixmap(ic.pixmap(18, 18))
        except Exception:
            self._brand_icon.setPixmap(
                theme.get_icon("fa6s.circle_dot", color=brand_color).pixmap(18, 18)
            )

        self._brand_lbl.setStyleSheet(
            f"color: {brand_color}; font-size: 13px; font-weight: 600; "
            f"font-family: 'Segoe UI Variable Display', sans-serif; background: transparent; border: none;"
        )

        # State label
        state = self._core.state
        state_label, state_icon_name = _STATE_META.get(state, ("Ready", "fa6s.circle_dot"))
        dark_c, light_c = _STATE_ACCENT.get(state, (txt, txt))
        state_color = light_c if light else dark_c

        try:
            import qtawesome as qta

            si = qta.icon(state_icon_name, color=state_color, scale_factor=0.85)
            self._state_icon_lbl.setPixmap(si.pixmap(13, 13))
        except Exception:
            pass

        self._state_lbl.setStyleSheet(
            f"color: {state_color}; font-size: 9px; font-family: 'Cascadia Code', Consolas; "
            f"background: transparent; border: none; letter-spacing: 0.5px;"
        )
        self._state_lbl.setText(state_label)

        # Transcript
        self._transcript.setStyleSheet(
            f"color: {txt}; background: transparent; "
            f"font-size: 13px; font-family: 'Segoe UI Variable Display', sans-serif; line-height: 1.5;"
        )

        # History title
        self._hist_title.setStyleSheet(
            f"color: {muted}; font-size: 8px; letter-spacing: 1.4px; "
            f"font-family: 'Segoe UI Variable Display', sans-serif; background: transparent; border: none;"
        )

        # Task label
        self._task_lbl.setStyleSheet(
            f"color: {muted}; font-size: 9px; font-family: 'Cascadia Code', Consolas; "
            f"background: transparent; border: none;"
        )

        # Dividers
        div_css = _divider_css()
        self._div_top.setStyleSheet(div_css)
        self._div_bot.setStyleSheet(div_css)

        # Icon buttons (escalate + close)
        icon_btn_css = _icon_btn_css()
        self._escalate_btn.setStyleSheet(icon_btn_css)
        self._close_btn.setStyleSheet(icon_btn_css)
        icon_c = "rgb(71,85,105)" if light else "rgb(148,163,184)"
        self._escalate_btn.setIcon(theme.get_icon("fa6s.arrow_up_right_from_square", color=icon_c))
        self._close_btn.setIcon(theme.get_icon("fa6s.xmark", color=icon_c))

        # Action buttons
        for i, btn in enumerate(self._action_btns):
            if i == 0:
                btn.setStyleSheet(_btn_accent_css())
            else:
                btn.setStyleSheet(_btn_ghost_css())

        # History cards
        for card in self._history_cards:
            card.apply_theme()

        self.update()

    # ------------------------------------------------------------------ animation

    def _setup_animation(self) -> None:
        self._opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self._opacity_anim.setDuration(theme.TRANSITION_NORMAL)
        self._opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(theme.ANIMATION_INTERVAL)
        self._anim_timer.timeout.connect(self._tick_anim)

    def _tick_anim(self) -> None:
        self._anim_phase = (self._anim_phase + 0.015) % 1.0
        self.update()

    # ------------------------------------------------------------------ public API

    def expand(self) -> None:
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

    def set_transcript(self, text: str) -> None:
        self._transcript.setText(text or "—")
        if text and text.strip() and text != "—" and not text.endswith("…"):
            self._add_history_card(text)

    def set_task(self, text: str) -> None:
        self._task_lbl.setText(text or "No active task")

    # ------------------------------------------------------------------ history

    def _load_snapshot_history(self) -> None:
        # Clear existing cards
        while self._history_layout.count() > 1:
            item = self._history_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._history_cards.clear()

        try:
            from state_engine import load_snapshot

            snap = load_snapshot()
            transcripts = (
                snap.get("domain_summaries", {}).get("april", {}).get("recent_transcripts", [])
            )
            for t in transcripts:
                if t.strip():
                    self._add_history_card(t)
        except Exception as exc:
            print(f"[Overlay] Failed to load history: {exc}")

    def _add_history_card(self, text: str) -> None:
        if not text or not text.strip():
            return

        # De-duplicate
        for card in self._history_cards:
            if card.get_text() == text:
                return

        # Update all existing cards' index (they become one older)
        for card in self._history_cards:
            card._index += 1
            card.apply_theme()

        card = _HistoryCard(
            text,
            on_copy=self._copy_text,
            on_retype=self._retype_text,
            index=0,
            parent=self._history_container,
        )
        self._history_layout.insertWidget(0, card)
        self._history_cards.insert(0, card)

        # Max 10 entries
        if len(self._history_cards) > 10:
            oldest = self._history_cards.pop()
            self._history_layout.removeWidget(oldest)
            oldest.deleteLater()

    def _copy_text(self, text: str) -> None:
        if text:
            QApplication.clipboard().setText(text)
            self._core.notification_passive.emit("Copied", "Text copied to clipboard.")

    def _retype_text(self, text: str) -> None:
        if text and self.bridge is not None:
            self.bridge.retype_text(text)

    # ------------------------------------------------------------------ layout

    def _reposition(self, corner: Corner) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        m = theme.CORNER_MARGIN
        ow = self.width()
        oh = self.sizeHint().height()
        orb = theme.ORB_SIZE + 12 * 2  # ORB_SIZE + PAD * 2
        gap = 10

        match corner:
            case Corner.BOTTOM_RIGHT:
                x, y = screen.right() - ow - m, screen.bottom() - oh - m - orb - gap
            case Corner.BOTTOM_LEFT:
                x, y = screen.left() + m, screen.bottom() - oh - m - orb - gap
            case Corner.TOP_RIGHT:
                x, y = screen.right() - ow - m, screen.top() + m + orb + gap
            case Corner.TOP_LEFT:
                x, y = screen.left() + m, screen.top() + m + orb + gap

        self.move(x, y)

    # ------------------------------------------------------------------ painting

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 18, 18)

        # Acrylic base
        p.setClipPath(path)
        p.fillRect(0, 0, self.width(), self.height(), theme.BG_BASE)

        # Subtle top-edge gloss
        grad = QLinearGradient(0, 0, 0, 56)
        grad.setColorAt(0, QColor(255, 255, 255, 20 if not theme.is_light_theme() else 35))
        grad.setColorAt(1, QColor(0, 0, 0, 0))
        p.fillRect(0, 0, self.width(), 56, grad)

        p.setClipping(False)

        # Border
        pen = QPen(theme.BORDER)
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        p.end()

    # ------------------------------------------------------------------ keyboard

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self._collapse()
        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------------------ private collapse

    def _collapse(self) -> None:
        if not self.isVisible():
            return
        if self._opacity_anim.state() == QPropertyAnimation.State.Running:
            return
        self._opacity_anim.setStartValue(self.windowOpacity())
        self._opacity_anim.setEndValue(0.0)
        self._opacity_anim.finished.connect(self._on_collapse_done)
        self._opacity_anim.start()

    def _on_collapse_done(self) -> None:
        self.hide()
        self._anim_timer.stop()
        try:
            self._opacity_anim.finished.disconnect(self._on_collapse_done)
        except Exception:
            pass
        self._core.set_mode(APRILMode.AMBIENT)

    # ------------------------------------------------------------------ slots

    def _on_state_changed(self, state: APRILState) -> None:
        label, icon_name = _STATE_META.get(state, ("Ready", "fa6s.circle_dot"))
        dark_c, light_c = _STATE_ACCENT.get(state, ("rgb(220,230,248)", "rgb(15,23,42)"))
        color = light_c if theme.is_light_theme() else dark_c

        try:
            import qtawesome as qta

            si = qta.icon(icon_name, color=color, scale_factor=0.85)
            self._state_icon_lbl.setPixmap(si.pixmap(13, 13))
        except Exception:
            pass

        self._state_lbl.setText(label)
        self._state_lbl.setStyleSheet(
            f"color: {color}; font-size: 9px; font-family: 'Cascadia Code', Consolas; "
            f"background: transparent; border: none; letter-spacing: 0.5px;"
        )

    def _on_mode_changed(self, mode: APRILMode) -> None:
        if mode == APRILMode.FOCUS:
            self.expand()
        elif mode == APRILMode.AMBIENT and self.isVisible():
            self._collapse()


# ── Helper widgets & style functions ─────────────────────────────────────────


class _HDivider(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFixedHeight(1)
        self.setStyleSheet(_divider_css())


def _divider_css() -> str:
    c = "rgba(0,0,0,18)" if theme.is_light_theme() else "rgba(255,255,255,15)"
    return f"color: {c}; background: {c}; border: none;"


def _icon_btn_css() -> str:
    light = theme.is_light_theme()
    hover = "rgba(0,0,0,7)" if light else "rgba(255,255,255,8)"
    pressed = "rgba(0,0,0,12)" if light else "rgba(255,255,255,14)"
    return f"""
QPushButton {{
    background: transparent;
    border: none;
    border-radius: 7px;
    padding: 4px;
}}
QPushButton:hover   {{ background: {hover}; }}
QPushButton:pressed {{ background: {pressed}; }}
"""


def _btn_ghost_css() -> str:
    light = theme.is_light_theme()
    bg = "rgba(0,0,0,6)" if light else "rgba(255,255,255,7)"
    border = "rgba(0,0,0,18)" if light else "rgba(255,255,255,16)"
    color = "rgb(71,85,105)" if light else "rgb(148,163,184)"
    hover_bg = "rgba(0,0,0,10)" if light else "rgba(255,255,255,12)"
    hover_c = "rgb(15,23,42)" if light else "rgb(220,230,248)"
    return f"""
QPushButton {{
    background: {bg};
    color: {color};
    border: 1px solid {border};
    border-radius: 7px;
    font-size: 11px;
    font-family: 'Segoe UI Variable Display', 'Segoe UI';
    padding: 0 12px;
}}
QPushButton:hover   {{ background: {hover_bg}; color: {hover_c}; }}
QPushButton:pressed {{ background: {bg}; }}
"""


def _btn_accent_css() -> str:
    light = theme.is_light_theme()
    bg = "rgba(8,145,178,200)" if light else "rgba(56,189,248,190)"
    hover = "rgba(8,145,178,240)" if light else "rgba(56,189,248,230)"
    return f"""
QPushButton {{
    background: {bg};
    color: rgb(8,20,32);
    border: none;
    border-radius: 7px;
    font-size: 11px;
    font-family: 'Segoe UI Variable Display', 'Segoe UI';
    font-weight: 600;
    padding: 0 14px;
}}
QPushButton:hover   {{ background: {hover}; }}
QPushButton:pressed {{ background: {bg}; }}
"""
