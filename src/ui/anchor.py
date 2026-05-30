"""
AmbientAnchor — the persistent corner orb.

Frameless, always-on-top, transparent.  Custom-painted state animations
driven by a QTimer at ~60 fps.  Drag snaps to nearest screen corner.
"""

from __future__ import annotations
import runtime_trace

import math
from PyQt6.QtCore import (
    Qt,
    QTimer,
    QPoint,
    QRect,
    QPropertyAnimation,
    QEasingCurve,
    pyqtProperty,
    QSize,
)
from PyQt6.QtGui import (
    QPainter,
    QPen,
    QBrush,
    QRadialGradient,
    QColor,
    QLinearGradient,
    QPainterPath,
    QCursor,
)
from PyQt6.QtWidgets import QWidget, QApplication

from .state import APRILCore, APRILState, APRILMode, Corner
from . import theme

_STATE_COLORS: dict[APRILState, tuple[QColor, QColor]] = {
    APRILState.DORMANT: (theme.CYAN_20, theme.CYAN_40),
    APRILState.LISTENING: (theme.CYAN_40, theme.CYAN_80),
    APRILState.THINKING: (theme.CYAN_40, theme.CYAN_80),
    APRILState.SPEAKING: (theme.CYAN_80, theme.CYAN),
    APRILState.ACTING: (theme.CYAN_40, theme.CYAN_80),
    APRILState.WARNING: (theme.AMBER_80, theme.AMBER),
    APRILState.ERROR: (theme.RED_80, theme.RED),
}


class AmbientAnchor(QWidget):
    """Small always-on-top orb that lives in a screen corner."""

    # Extra hit-area padding so the widget is easy to click
    _PAD = 12

    def __init__(self, core: APRILCore, parent=None):
        super().__init__(parent)
        self._core = core
        self._phase = 0.0  # animation phase 0–1 (cycles)
        self._drag_start: QPoint | None = None
        self._widget_origin: QPoint | None = None

        # Opacity used for fade-in/out transitions
        self._opacity = 1.0
        self._is_light = theme.is_light_theme()

        self._setup_window()
        self._place_in_corner(core.corner)

        self._timer = QTimer(self)
        self._timer.setInterval(theme.ANIMATION_INTERVAL)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        # Keep-on-top: Win32 HWND_TOPMOST every 15 s to survive z-order fights
        self._top_timer = QTimer(self)
        self._top_timer.setInterval(15000)
        self._top_timer.timeout.connect(self._force_topmost)
        self._top_timer.start()

        core.state_changed.connect(self._on_state_changed)
        core.mode_changed.connect(self._on_mode_changed)
        core.corner_changed.connect(self._place_in_corner)

    def _get_state_colors(self, state: APRILState) -> tuple[QColor, QColor]:
        if state == APRILState.WARNING:
            return (theme.AMBER_80, theme.AMBER)
        elif state == APRILState.ERROR:
            return (theme.RED_80, theme.RED)
        else:
            c = theme.CYAN
            c_80 = theme.CYAN_80
            c_40 = theme.CYAN_40
            c_20 = theme.CYAN_20
            
            if state == APRILState.DORMANT:
                return (c_20, c_40)
            elif state == APRILState.SPEAKING:
                return (c_80, c)
            else:
                return (c_40, c_80)

    # ------------------------------------------------------------------ setup

    # ------------------------------------------------------------------ setup

    def _setup_window(self):
        size = theme.ORB_SIZE + self._PAD * 2
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._update_mask(self._core.state)

    def _update_mask(self, state: APRILState):
        # Clear the mask completely so dynamic ripple animations and indicators
        # can draw outside the central dot bounds cleanly without clipping.
        self.clearMask()

    def _force_topmost(self):
        """Win32 SetWindowPos HWND_TOPMOST — survives z-order fights."""
        import ctypes

        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_NOACTIVATE = 0x0010
        HWND_TOPMOST = -1
        ctypes.windll.user32.SetWindowPos(
            int(self.winId()),
            HWND_TOPMOST,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
        )

    def _place_in_corner(self, corner: Corner):
        screen = QApplication.primaryScreen().availableGeometry()
        m = theme.CORNER_MARGIN
        s = self.width()
        match corner:
            case Corner.BOTTOM_RIGHT:
                pos = QPoint(screen.right() - s - m, screen.bottom() - s - m)
            case Corner.BOTTOM_LEFT:
                pos = QPoint(screen.left() + m, screen.bottom() - s - m)
            case Corner.TOP_RIGHT:
                pos = QPoint(screen.right() - s - m, screen.top() + m)
            case Corner.TOP_LEFT:
                pos = QPoint(screen.left() + m, screen.top() + m)
        self.move(pos)
        self._update_mask(self._core.state)

    # ------------------------------------------------------------------ animation

    def _tick(self):
        state = self._core.state
        speeds = {
            APRILState.DORMANT: 0.004,
            APRILState.LISTENING: 0.010,
            APRILState.THINKING: 0.015,
            APRILState.SPEAKING: 0.022,
            APRILState.ACTING: 0.012,
            APRILState.WARNING: 0.016,
            APRILState.ERROR: 0.026,
        }
        self._phase = (self._phase + speeds.get(state, 0.005)) % 1.0

        # Periodic check for Windows system light/dark theme changes (no disk polling)
        if not hasattr(self, "_theme_check_counter"):
            self._theme_check_counter = 0
        self._theme_check_counter += 1
        if self._theme_check_counter >= 120:
            self._theme_check_counter = 0
            curr_light = theme.is_light_theme()
            if curr_light != self._is_light:
                self._is_light = curr_light
                theme.refresh_theme()
                self.update()

        if not hasattr(self, "_last_logged_state") or self._last_logged_state != state:
            self._last_logged_state = state
            runtime_trace.trace_event(
                "anchor_repaint_state",
                subsystem="ui",
                severity=runtime_trace.DEBUG,
                payload={"state": state.name},
            )
        self.update()

    # ------------------------------------------------------------------ painting

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self._opacity)

        cx = self.width() / 2
        cy = self.height() / 2
        dot_r = 5.0

        state = self._core.state
        dim_col, bright_col = self._get_state_colors(state)

        # 1. State Animations
        if state == APRILState.DORMANT:
            # Soft breathing opacity pulse
            alpha = int(160 + math.sin(self._phase * math.tau) * 45)
            c = QColor(bright_col)
            c.setAlpha(alpha)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(c))
            p.drawEllipse(int(cx - dot_r), int(cy - dot_r), int(dot_r * 2), int(dot_r * 2))

        elif state == APRILState.LISTENING:
            # Concentric expanding ripples
            pulse = 1.0 + math.sin(self._phase * math.tau) * 0.15
            curr_r = dot_r * pulse
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(bright_col))
            p.drawEllipse(int(cx - curr_r), int(cy - curr_r), int(curr_r * 2), int(curr_r * 2))

            for i in range(2):
                offset = (self._phase + i / 2.0) % 1.0
                ring_r = dot_r + offset * 14.0
                alpha = int((1.0 - offset) * 150)
                rc = QColor(bright_col)
                rc.setAlpha(alpha)
                pen = QPen(rc)
                pen.setWidthF(1.0)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(int(cx - ring_r), int(cy - ring_r), int(ring_r * 2), int(ring_r * 2))

        elif state == APRILState.THINKING:
            # Hugging spinning sweep arc loader
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(bright_col))
            p.drawEllipse(int(cx - dot_r), int(cy - dot_r), int(dot_r * 2), int(dot_r * 2))

            angle = self._phase * 360
            arc_r = dot_r + 3.5
            pen = QPen(bright_col)
            pen.setWidthF(1.5)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            rect = QRect(int(cx - arc_r), int(cy - arc_r), int(arc_r * 2), int(arc_r * 2))
            p.drawArc(rect, int((angle % 360) * 16), int(120 * 16))

        elif state == APRILState.SPEAKING:
            # Bouncing voice waveform bars
            bar_w = 2.0
            gap = 2.0
            total_w = 3 * bar_w + 2 * gap
            x0 = cx - total_w / 2

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(bright_col))
            for i in range(3):
                bx = x0 + i * (bar_w + gap)
                h_factor = abs(math.sin(self._phase * math.tau * 1.5 + i * 0.7))
                h = 3.0 + h_factor * 11.0
                p.drawRoundedRect(int(bx), int(cy - h / 2), int(bar_w), int(h), 1, 1)

        elif state == APRILState.ACTING:
            # Radar sweeps line scanner
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(bright_col))
            p.drawEllipse(int(cx - dot_r), int(cy - dot_r), int(dot_r * 2), int(dot_r * 2))

            angle_rad = self._phase * math.tau
            sweep_len = dot_r + 5.0
            px = cx + math.cos(angle_rad) * sweep_len
            py = cy - math.sin(angle_rad) * sweep_len
            pen = QPen(bright_col)
            pen.setWidthF(1.2)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawLine(int(cx), int(cy), int(px), int(py))

        elif state == APRILState.WARNING:
            # Medium alert breathing dot
            pulse = 1.0 + math.sin(self._phase * math.tau * 1.5) * 0.25
            curr_r = dot_r * pulse
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(bright_col))
            p.drawEllipse(int(cx - curr_r), int(cy - curr_r), int(curr_r * 2), int(curr_r * 2))

        elif state == APRILState.ERROR:
            # Red flash rapid alert dot
            pulse = 1.0 + math.sin(self._phase * math.tau * 3.0) * 0.35
            curr_r = dot_r * pulse
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(bright_col))
            p.drawEllipse(int(cx - curr_r), int(cy - curr_r), int(curr_r * 2), int(curr_r * 2))

        p.end()

    # ------------------------------------------------------------------ interaction

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.globalPosition().toPoint()
            self._widget_origin = self.pos()

    def mouseMoveEvent(self, event):
        if self._drag_start is not None:
            delta = event.globalPosition().toPoint() - self._drag_start
            self.move(self._widget_origin + delta)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start is not None:
            delta = event.globalPosition().toPoint() - self._drag_start
            if delta.manhattanLength() < 5:  # tap, not drag
                import webbrowser
                webbrowser.open("http://localhost:8080")
            else:
                self._snap_to_corner()
            self._drag_start = None

    def mouseDoubleClickEvent(self, _event):
        import webbrowser
        webbrowser.open("http://localhost:8080")

    def contextMenuEvent(self, event):
        from PyQt6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.setStyleSheet(_menu_style())

        menu.addAction("Settings …").triggered.connect(
            self._core.settings_requested.emit
        )
        menu.addSeparator()

        state_menu = menu.addMenu("Dev: Set State")
        for s in APRILState:
            a = state_menu.addAction(s.name.capitalize())
            a.triggered.connect(lambda checked, _s=s: self._core.set_state(_s))

        menu.exec(event.globalPos())

    def _snap_to_corner(self):
        screen = QApplication.primaryScreen().availableGeometry()
        cx = self.x() + self.width() / 2
        cy = self.y() + self.height() / 2
        is_left = cx < screen.center().x()
        is_top = cy < screen.center().y()
        if is_top and is_left:
            c = Corner.TOP_LEFT
        elif is_top:
            c = Corner.TOP_RIGHT
        elif is_left:
            c = Corner.BOTTOM_LEFT
        else:
            c = Corner.BOTTOM_RIGHT
        self._core.set_corner(c)

    # ------------------------------------------------------------------ slots

    def _on_state_changed(self, state: APRILState):
        runtime_trace.trace_event(
            "anchor_state_changed",
            subsystem="ui",
            payload={"state": state.name},
        )
        self._phase = 0.0
        if state == APRILState.DORMANT:
            self._timer.setInterval(66)
        else:
            self._timer.setInterval(theme.ANIMATION_INTERVAL)
        self._update_mask(state)

    def _on_mode_changed(self, mode):
        pass  # orb visible in all modes


def _menu_style() -> str:
    """Dynamic, theme-adaptive context menu stylesheet mimicking Windows 11 Fluent design."""
    is_light = theme.is_light_theme()
    accent_rgb = f"rgb({theme.CYAN.red()}, {theme.CYAN.green()}, {theme.CYAN.blue()})"
    
    if is_light:
        css = """
        QMenu {
            background: rgba(243, 243, 243, 220);
            border: 1px solid rgba(0, 0, 0, 24);
            border-radius: 8px;
            padding: 6px;
            color: rgb(24, 24, 27);
            font-family: 'Segoe UI Variable Text', 'Segoe UI';
            font-size: 12px;
        }
        QMenu::item {
            padding: 6px 24px 6px 16px;
            border-radius: 4px;
            margin: 1px 0;
            background: transparent;
        }
        QMenu::item:selected {
            background: rgba(0, 0, 0, 10);
            color: rgb(24, 24, 27);
        }
        QMenu::item:checked {
            color: @ACCENT@;
            font-weight: 600;
        }
        QMenu::separator {
            height: 1px;
            background: rgba(0, 0, 0, 15);
            margin: 4px 6px;
        }
        QMenu::section {
            color: rgba(0, 0, 0, 120);
            font-size: 10px;
            font-family: 'Segoe UI Variable Small';
            font-weight: 600;
            padding: 4px 16px 2px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        """
        return css.replace("@ACCENT@", accent_rgb)
    else:
        css = """
        QMenu {
            background: rgba(32, 32, 32, 220);
            border: 1px solid rgba(255, 255, 255, 20);
            border-radius: 8px;
            padding: 6px;
            color: rgb(243, 243, 243);
            font-family: 'Segoe UI Variable Text', 'Segoe UI';
            font-size: 12px;
        }
        QMenu::item {
            padding: 6px 24px 6px 16px;
            border-radius: 4px;
            margin: 1px 0;
            background: transparent;
        }
        QMenu::item:selected {
            background: rgba(255, 255, 255, 12);
            color: rgb(243, 243, 243);
        }
        QMenu::item:checked {
            color: @ACCENT@;
            font-weight: 600;
        }
        QMenu::separator {
            height: 1px;
            background: rgba(255, 255, 255, 20);
            margin: 4px 6px;
        }
        QMenu::section {
            color: rgba(255, 255, 255, 140);
            font-size: 10px;
            font-family: 'Segoe UI Variable Small';
            font-weight: 600;
            padding: 4px 16px 2px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        """
        return css.replace("@ACCENT@", accent_rgb)

