"""
ui/overlay.py — Layer 2: Quick Peek Card.

A lightweight, non-focus-stealing Mica card (320x120px) that slides up near
the Ambient Dot upon capture/notification and auto-dismisses after 5 seconds.
"""

from __future__ import annotations

import math
from PyQt6.QtCore import (
    Qt,
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
    QPoint,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QPainter,
    QColor,
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
)

from .state import APRILCore, APRILState, APRILMode, Corner
from . import theme


class TransitionalOverlay(QWidget):
    """Layer 2: Quick Peek Card. Non-focus-stealing transient panel."""

    def __init__(self, core: APRILCore, parent=None):
        super().__init__(parent)
        self._core = core
        self.bridge = None  # Attached via bridge
        
        # 5-second auto-dismiss timer
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setInterval(5000)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self._collapse)

        self._setup_window()
        self._build_ui()
        self._setup_animation()

        core.state_changed.connect(self._on_state_changed)
        core.mode_changed.connect(self._on_mode_changed)
        core.corner_changed.connect(self._reposition)

        self.hide()

    def _setup_window(self) -> None:
        self.setFixedSize(320, 120)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        
        # Frameless, stay-on-top, tool window that doesn't accept active keyboard focus
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        theme.apply_fluent_effects(self, use_acrylic=True)

    def _build_ui(self) -> None:
        self._top_layout = QVBoxLayout(self)
        self._top_layout.setContentsMargins(8, 8, 8, 8)
        self._top_layout.setSpacing(0)

        # Base Frame (Mica glassmorphism style)
        self._base_frame = theme.MicaFrame()
        self._base_frame.setObjectName("OverlayBase")
        
        shadow = theme.create_shadow(QColor(0, 0, 0, 75), radius=12, dy=3)
        if shadow:
            self._base_frame.setGraphicsEffect(shadow)

        self._layout = QVBoxLayout(self._base_frame)
        self._layout.setContentsMargins(12, 10, 12, 10)
        self._layout.setSpacing(6)

        # 1. Header row (Type label + Close button)
        hdr = QHBoxLayout()
        hdr.setSpacing(6)

        self._type_icon = QLabel()
        self._type_icon.setFixedSize(14, 14)
        hdr.addWidget(self._type_icon)

        self._hdr_title = QLabel("Note Crystallized")
        self._hdr_title.setFont(theme.ui_font(10))
        self._hdr_title.setStyleSheet("font-weight: bold;")
        hdr.addWidget(self._hdr_title)

        hdr.addStretch()

        self._close_btn = QPushButton()
        self._close_btn.setFixedSize(18, 18)
        self._close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._close_btn.clicked.connect(self._collapse)
        hdr.addWidget(self._close_btn)

        self._layout.addLayout(hdr)

        # 2. Content label (Dictation/payload preview)
        self._text_lbl = QLabel("—")
        self._text_lbl.setWordWrap(True)
        self._text_lbl.setFont(theme.ui_font(10))
        self._text_lbl.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._text_lbl.setStyleSheet("color: rgba(255, 255, 255, 200);")
        self._text_lbl.setFixedHeight(36)
        self._layout.addWidget(self._text_lbl, 1)

        # 3. Actions Capsule Bar
        actions_lay = QHBoxLayout()
        actions_lay.setContentsMargins(0, 0, 0, 0)
        actions_lay.setSpacing(6)

        actions_lay.addStretch()

        self._edit_btn = QPushButton("Edit")
        self._edit_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._edit_btn.clicked.connect(self._on_edit_clicked)
        actions_lay.addWidget(self._edit_btn)

        self._open_btn = QPushButton("Open")
        self._open_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._open_btn.clicked.connect(self._on_open_clicked)
        actions_lay.addWidget(self._open_btn)

        self._layout.addLayout(actions_lay)

        self._top_layout.addWidget(self._base_frame)
        self._apply_theme()

    def _setup_animation(self) -> None:
        self._opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self._opacity_anim.setDuration(theme.TRANSITION_NORMAL)
        self._opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._pos_anim = QPropertyAnimation(self, b"pos")
        self._pos_anim.setDuration(theme.TRANSITION_NORMAL)
        self._pos_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def show_peek(self, art_type: str, text: str) -> None:
        """Pop up the Quick Peek card showing the newly crystallized artifact."""
        # Icon and title updates
        icon_mapping = {
            "Note": "fa6s.file-lines",
            "Task": "fa6s.circle-check",
            "Reminder": "fa6s.bell",
            "Research": "fa6s.magnifying-glass",
            "Conversation": "fa6s.comments",
            "Automation": "fa6s.wand-magic-sparkles",
            "Workspace Item": "fa6s.folder-open",
            "Agent Activity": "fa6s.microchip",
        }
        icon_name = icon_mapping.get(art_type, "fa6s.file-lines")
        icon_c = "rgb(82, 82, 91)" if theme.is_light_theme() else "rgb(161, 161, 170)"
        self._type_icon.setPixmap(theme.get_icon(icon_name, color=icon_c).pixmap(12, 12))
        self._hdr_title.setText(f"{art_type} Crystallized")
        
        # Snippet body
        max_len = 80
        snippet = text
        if len(snippet) > max_len:
            snippet = snippet[:max_len] + "..."
        self._text_lbl.setText(snippet)

        theme.refresh_theme()
        self._apply_theme()

        # Reposition and animate
        target_pos = self._get_reposition_pos(self._core.corner)
        is_bottom = self._core.corner in (Corner.BOTTOM_RIGHT, Corner.BOTTOM_LEFT)
        offset_y = 15 if is_bottom else -15
        start_pos = target_pos + QPoint(0, offset_y)
        
        self.move(start_pos)
        self.setWindowOpacity(0.0)
        self.show()

        self._opacity_anim.setStartValue(0.0)
        self._opacity_anim.setEndValue(1.0)
        self._opacity_anim.start()

        self._pos_anim.setStartValue(start_pos)
        self._pos_anim.setEndValue(target_pos)
        self._pos_anim.start()

        # Start 5s dismiss timer
        self._dismiss_timer.start()

    def _collapse(self) -> None:
        if not self.isVisible():
            return
        if self._opacity_anim.state() == QPropertyAnimation.State.Running:
            return
            
        target_pos = self.pos()
        is_bottom = self._core.corner in (Corner.BOTTOM_RIGHT, Corner.BOTTOM_LEFT)
        offset_y = 15 if is_bottom else -15
        end_pos = target_pos + QPoint(0, offset_y)

        self._opacity_anim.setStartValue(self.windowOpacity())
        self._opacity_anim.setEndValue(0.0)
        
        self._pos_anim.setStartValue(target_pos)
        self._pos_anim.setEndValue(end_pos)
        
        self._opacity_anim.finished.connect(self._on_collapse_done)
        self._opacity_anim.start()
        self._pos_anim.start()

    def _on_collapse_done(self) -> None:
        self.hide()
        try:
            self._opacity_anim.finished.disconnect(self._on_collapse_done)
        except Exception:
            pass
        self._core.set_mode(APRILMode.AMBIENT)

    def set_transcript(self, text: str) -> None:
        """Legacy stub from bridge protocol."""
        self.show_peek("Note", text)

    def set_task(self, text: str) -> None:
        """Legacy stub."""
        pass

    def enterEvent(self, event) -> None:  # noqa: N802
        """Pause auto-dismiss on hover."""
        self._dismiss_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        """Resume dismiss timer on mouse leave."""
        self._dismiss_timer.start()
        super().leaveEvent(event)

    def _on_edit_clicked(self) -> None:
        if self.bridge is not None:
            self.bridge.open_workspace_to_recent(edit=True)
        self._collapse()

    def _on_open_clicked(self) -> None:
        if self.bridge is not None:
            self.bridge.open_workspace_to_recent(edit=False)
        self._collapse()

    def _on_state_changed(self, state: APRILState) -> None:
        # Listening or Thinking states could show status briefly
        pass

    def _on_mode_changed(self, mode: APRILMode) -> None:
        if mode == APRILMode.FOCUS:
            import database
            recent = database.get_artifacts("recent")
            if recent:
                self.show_peek(recent[0]["type"], recent[0]["content"])
            else:
                self.show_peek("Note", "No recent captures.")
        elif mode == APRILMode.AMBIENT and self.isVisible():
            self._collapse()

    def _get_reposition_pos(self, corner: Corner) -> QPoint:
        screen = QApplication.primaryScreen().availableGeometry()
        m = theme.CORNER_MARGIN
        ow, oh = self.width(), self.height()
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

    def _reposition(self, corner: Corner) -> None:
        if self.isVisible() and self._pos_anim.state() != QPropertyAnimation.State.Running:
            self.move(self._get_reposition_pos(corner))

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        p.end()

    def _apply_theme(self) -> None:
        is_light = theme.is_light_theme()
        txt_color = "rgb(24,24,27)" if is_light else "rgb(243,243,243)"
        accent_color = f"rgb({theme.CYAN.red()}, {theme.CYAN.green()}, {theme.CYAN.blue()})"
        icon_c = "rgb(82, 82, 91)" if is_light else "rgb(161, 161, 170)"

        self._base_frame.setStyleSheet("""
            QFrame#OverlayBase {
                background: transparent;
                border: none;
            }
        """)

        self._hdr_title.setStyleSheet(f"color: {accent_color}; background: transparent;")
        self._text_lbl.setStyleSheet(f"color: {txt_color}; background: transparent;")

        self._close_btn.setStyleSheet(_btn_ghost_style())
        self._close_btn.setIcon(theme.get_icon("fa6s.xmark", color=icon_c))

        self._edit_btn.setStyleSheet(_btn_ghost_style())
        self._open_btn.setStyleSheet(_btn_solid_style())
        self.update()


# ── Stylesheet Helpers ───────────────────────────────────────────────────────

def _btn_solid_style() -> str:
    bg = f"rgba({theme.CYAN.red()}, {theme.CYAN.green()}, {theme.CYAN.blue()}, 220)"
    hover = f"rgba({theme.CYAN.red()}, {theme.CYAN.green()}, {theme.CYAN.blue()}, 255)"
    return f"""
    QPushButton {{
        background: {bg};
        color: white;
        border: none;
        border-radius: 4px;
        font-size: 10px;
        font-family: 'Segoe UI Variable Text';
        font-weight: bold;
        padding: 4px 10px;
    }}
    QPushButton:hover {{ background: {hover}; }}
    """


def _btn_ghost_style() -> str:
    is_light = theme.is_light_theme()
    bg = "rgba(0,0,0,6)" if is_light else "rgba(255,255,255,6)"
    border = f"1px solid rgba({theme.BORDER.red()}, {theme.BORDER.green()}, {theme.BORDER.blue()}, {theme.BORDER.alpha()})"
    color = "rgb(55,55,65)" if is_light else "rgb(200,220,240)"
    hover_bg = "rgba(0,0,0,12)" if is_light else "rgba(255,255,255,12)"
    hover_color = "rgb(24,24,27)" if is_light else "rgb(243,243,243)"
    return f"""
    QPushButton {{
        background: {bg};
        color: {color};
        border: {border};
        border-radius: 4px;
        font-size: 10px;
        font-family: 'Segoe UI Variable Text';
        padding: 4px 10px;
    }}
    QPushButton:hover {{ background: {hover_bg}; color: {hover_color}; }}
    """
