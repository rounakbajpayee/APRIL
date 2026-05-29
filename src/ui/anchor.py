"""
AmbientAnchor — the persistent corner orb.

Frameless, always-on-top, transparent widget.  Custom-painted state
animations driven by a QTimer at ~60 fps.  Drag snaps to the nearest
screen corner.

Design language (Fluent 2 / WinUI 3)
─────────────────────────────────────
DORMANT   : 7 px emerald breathing dot — identical to the iOS status dot.
            Everything outside is click-through (window mask reduced to dot).

LISTENING : Three cyan ripple rings expanding outward (sonar / audio wave).

THINKING  : Spinning arc on a dim circular track (iOS-style activity ring).

SPEAKING  : Five animated equaliser bars, independently phased sinusoids.

ACTING    : Dotted circular track + bright leading arc (progress indicator).

WARNING   : Expanding amber ring + solid centre dot — pulsing 1×/s.

ERROR     : Same as WARNING but red and 2×/s — clearly urgent.
"""

from __future__ import annotations
import runtime_trace

import math

from PyQt6.QtCore import Qt, QTimer, QPoint, QRect
from PyQt6.QtGui import (
    QPainter,
    QPen,
    QBrush,
    QColor,
    QLinearGradient,
    QRegion,
    QCursor,
)
from PyQt6.QtWidgets import QWidget, QApplication

from .state import APRILCore, APRILState, APRILMode, Corner
from . import theme

# ── State → (dim_colour, bright_colour) mapping ────────────────────────────
_STATE_COLORS: dict[APRILState, tuple[QColor, QColor]] = {
    APRILState.DORMANT: (theme.CYAN_20, theme.CYAN_40),
    APRILState.LISTENING: (theme.CYAN_40, theme.CYAN_80),
    APRILState.THINKING: (theme.CYAN_40, theme.CYAN_80),
    APRILState.SPEAKING: (theme.CYAN_80, theme.CYAN),
    APRILState.ACTING: (theme.VIOLET, theme.VIOLET),
    APRILState.WARNING: (theme.AMBER_80, theme.AMBER),
    APRILState.ERROR: (theme.RED_80, theme.RED),
}

# Animation speeds (phase-increment per tick, ~60 fps)
_SPEEDS: dict[APRILState, float] = {
    APRILState.DORMANT: 0.004,
    APRILState.LISTENING: 0.010,
    APRILState.THINKING: 0.020,
    APRILState.SPEAKING: 0.018,
    APRILState.ACTING: 0.014,
    APRILState.WARNING: 0.016,
    APRILState.ERROR: 0.030,
}

_DORMANT_INTERVAL = 66  # ~15 fps when idle — saves CPU
_ACTIVE_INTERVAL = theme.ANIMATION_INTERVAL


class AmbientAnchor(QWidget):
    """Small always-on-top orb widget that lives in a screen corner."""

    _PAD = 12  # transparent hit-area padding around the painted orb

    def __init__(self, core: APRILCore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._core = core
        self._phase: float = 0.0
        self._drag_start: QPoint | None = None
        self._widget_origin: QPoint | None = None
        self._opacity: float = 1.0
        self._theme_tick: int = 0
        self._last_state: APRILState | None = None

        self._setup_window()
        self._place_in_corner(core.corner)

        # Animation timer (~60 fps when active, ~15 fps when dormant)
        self._timer = QTimer(self)
        self._timer.setInterval(_ACTIVE_INTERVAL)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        # Win32 HWND_TOPMOST enforcement every 15 s (survives z-order fights)
        self._top_timer = QTimer(self)
        self._top_timer.setInterval(15_000)
        self._top_timer.timeout.connect(self._force_topmost)
        self._top_timer.start()

        core.state_changed.connect(self._on_state_changed)
        core.mode_changed.connect(self._on_mode_changed)
        core.corner_changed.connect(self._place_in_corner)

    # ------------------------------------------------------------------ setup

    def _setup_window(self) -> None:
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
        self._update_mask(APRILState.DORMANT)

    def _update_mask(self, state: APRILState) -> None:
        """
        In DORMANT state the click region is limited to the tiny status dot so
        the rest of the corner is fully transparent and click-through.
        In active states the entire orb ellipse is interactive.
        """
        cx = self.width() // 2
        cy = self.height() // 2
        if state == APRILState.DORMANT:
            r = 6  # a tiny extra margin around the 3.5 px dot
            self.setMask(QRegion(cx - r, cy - r, r * 2, r * 2, QRegion.RegionType.Ellipse))
        else:
            pad = self._PAD
            orb = theme.ORB_SIZE
            self.setMask(QRegion(pad, pad, orb, orb, QRegion.RegionType.Ellipse))

    def _force_topmost(self) -> None:
        """Win32 SetWindowPos HWND_TOPMOST — keeps the orb above all windows."""
        try:
            import ctypes

            HWND_TOPMOST = -1
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOACTIVATE = 0x0010
            ctypes.windll.user32.SetWindowPos(
                int(self.winId()),
                HWND_TOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
            )
        except Exception:
            pass

    def _place_in_corner(self, corner: Corner) -> None:
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

    def _tick(self) -> None:
        state = self._core.state
        self._phase = (self._phase + _SPEEDS.get(state, 0.005)) % 1.0

        # Check theme every ~2 s (120 ticks × 16 ms)
        self._theme_tick += 1
        if self._theme_tick >= 120:
            self._theme_tick = 0
            was_light = theme.is_light_theme()
            theme.refresh_theme()
            if theme.is_light_theme() != was_light:
                self.update()

        # Trace state changes without spamming every tick
        if self._last_state != state:
            self._last_state = state
            runtime_trace.trace_event(
                "anchor_state_changed",
                subsystem="ui",
                severity=runtime_trace.DEBUG,
                payload={"state": state.name},
            )

        self.update()

    # ------------------------------------------------------------------ painting

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self._opacity)

        cx = float(self.width()) / 2
        cy = float(self.height()) / 2
        r = theme.ORB_SIZE / 2
        state = self._core.state

        if state == APRILState.DORMANT:
            self._paint_dormant_dot(p, cx, cy)
        else:
            self._paint_orb(p, cx, cy, r, state)

        p.end()

    # -- dormant -------------------------------------------------------

    def _paint_dormant_dot(self, p: QPainter, cx: float, cy: float) -> None:
        """7 px emerald dot with soft alpha breathing — identical to iOS status dot."""
        alpha = int(190 + math.sin(self._phase * math.tau) * 55)
        c = QColor(theme.EMERALD)
        c.setAlpha(alpha)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(c))
        dot_r = 3.5
        p.drawEllipse(int(cx - dot_r), int(cy - dot_r), int(dot_r * 2), int(dot_r * 2))

    # -- full orb ------------------------------------------------------

    def _paint_orb(self, p: QPainter, cx: float, cy: float, r: float, state: APRILState) -> None:
        _dim, bright = _STATE_COLORS[state]

        # 1 · Background fill (acrylic translucent)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(theme.BG_BASE))
        p.drawEllipse(int(cx - r), int(cy - r), int(r * 2), int(r * 2))

        # 2 · Subtle top-edge gloss shimmer (simulates ambient light source)
        shimmer = QLinearGradient(cx, cy - r, cx, cy + r * 0.3)
        alpha_top = 35 if not theme.is_light_theme() else 50
        shimmer.setColorAt(0.0, QColor(255, 255, 255, alpha_top))
        shimmer.setColorAt(0.45, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(shimmer))
        p.drawEllipse(int(cx - r + 1), int(cy - r + 1), int(r * 2 - 2), int(r * 2 - 2))

        # 3 · State-specific animation layer
        match state:
            case APRILState.LISTENING:
                self._paint_listening(p, cx, cy, r, bright)
            case APRILState.THINKING:
                self._paint_thinking(p, cx, cy, r, bright)
            case APRILState.SPEAKING:
                self._paint_speaking(p, cx, cy, r, bright)
            case APRILState.ACTING:
                self._paint_acting(p, cx, cy, r, bright)
            case APRILState.WARNING:
                self._paint_alert(p, cx, cy, r, bright, fast=False)
            case APRILState.ERROR:
                self._paint_alert(p, cx, cy, r, bright, fast=True)

        # 4 · 1 px Fluent border ring
        pen = QPen(theme.BORDER)
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(int(cx - r), int(cy - r), int(r * 2), int(r * 2))

    # -- state animations ----------------------------------------------

    def _paint_listening(self, p: QPainter, cx: float, cy: float, r: float, color: QColor) -> None:
        """Three concentric ripple rings expanding outward (sonar / audio wave)."""
        for i in range(3):
            offset = (self._phase + i / 3.0) % 1.0
            ring_r = r * 0.08 + offset * r * 0.87
            alpha = int((1.0 - offset) * 155)
            c = QColor(color)
            c.setAlpha(alpha)
            pen = QPen(c)
            pen.setWidthF(1.2 + (1.0 - offset) * 0.8)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(
                int(cx - ring_r),
                int(cy - ring_r),
                int(ring_r * 2),
                int(ring_r * 2),
            )

    def _paint_thinking(self, p: QPainter, cx: float, cy: float, r: float, color: QColor) -> None:
        """Spinning arc on a dim circular track — iOS-style activity indicator."""
        arc_r = r * 0.58
        rect = QRect(int(cx - arc_r), int(cy - arc_r), int(arc_r * 2), int(arc_r * 2))
        angle_deg = self._phase * 360

        # Dim track
        track_c = QColor(color)
        track_c.setAlpha(24)
        pen = QPen(track_c)
        pen.setWidthF(2.8)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(rect)

        # Rotating leading arc (counter-clockwise feels more "thinking")
        arc_pen = QPen(color)
        arc_pen.setWidthF(2.8)
        arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(arc_pen)
        start = int((90 - angle_deg) % 360 * 16)
        p.drawArc(rect, start, int(100 * 16))

    def _paint_speaking(self, p: QPainter, cx: float, cy: float, r: float, color: QColor) -> None:
        """Five independently phased equaliser bars — audio waveform visualiser."""
        bar_count = 5
        bar_w = 3.0
        gap = 3.5
        total_w = bar_count * bar_w + (bar_count - 1) * gap
        x0 = cx - total_w / 2
        max_h = r * 0.82
        min_h = r * 0.13

        for i in range(bar_count):
            bx = x0 + i * (bar_w + gap)
            # Each bar has a different phase offset and slightly different frequency
            t = (math.sin((self._phase + i * 0.19) * math.tau * 1.5) + 1) / 2
            h = min_h + t * (max_h - min_h)
            c = QColor(color)
            c.setAlpha(155 + int(t * 90))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(c))
            p.drawRoundedRect(int(bx), int(cy - h / 2), int(bar_w), int(h), 1.5, 1.5)

    def _paint_acting(self, p: QPainter, cx: float, cy: float, r: float, color: QColor) -> None:
        """Dotted circular track + bright leading arc — task-progress indicator."""
        arc_r = r * 0.60
        rect = QRect(int(cx - arc_r), int(cy - arc_r), int(arc_r * 2), int(arc_r * 2))
        angle_deg = self._phase * 360

        # Dotted dim track
        track_c = QColor(color)
        track_c.setAlpha(22)
        pen = QPen(track_c)
        pen.setWidthF(1.8)
        pen.setStyle(Qt.PenStyle.DotLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(rect)

        # Bright solid leading arc
        lead_pen = QPen(color)
        lead_pen.setWidthF(2.4)
        lead_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        lead_pen.setStyle(Qt.PenStyle.SolidLine)
        p.setPen(lead_pen)
        start = int((90 + angle_deg) % 360 * 16)
        p.drawArc(rect, start, int(48 * 16))

    def _paint_alert(
        self,
        p: QPainter,
        cx: float,
        cy: float,
        r: float,
        color: QColor,
        fast: bool,
    ) -> None:
        """Expanding ring + solid centre dot — WARNING (1×/s) and ERROR (2×/s)."""
        freq = 1.8 if fast else 1.0
        pulse = (math.sin(self._phase * math.tau * freq) + 1) / 2

        # Expanding outer ring
        ring_r = r * 0.26 + pulse * r * 0.58
        ring_c = QColor(color)
        ring_c.setAlpha(int((1.0 - pulse) * 145))
        pen = QPen(ring_c)
        pen.setWidthF(1.8)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(int(cx - ring_r), int(cy - ring_r), int(ring_r * 2), int(ring_r * 2))

        # Pulsing filled centre dot
        dot_r = 5.0 + pulse * 1.8
        dot_c = QColor(color)
        dot_c.setAlpha(210)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(dot_c))
        p.drawEllipse(int(cx - dot_r), int(cy - dot_r), int(dot_r * 2), int(dot_r * 2))

    # ------------------------------------------------------------------ interaction

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.globalPosition().toPoint()
            self._widget_origin = self.pos()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_start is not None:
            delta = event.globalPosition().toPoint() - self._drag_start
            self.move(self._widget_origin + delta)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start is not None:
            delta = event.globalPosition().toPoint() - self._drag_start
            if delta.manhattanLength() < 5:
                self._core.escalate()  # tap → expand mode
            else:
                self._snap_to_corner()
            self._drag_start = None

    def mouseDoubleClickEvent(self, _event) -> None:  # noqa: N802
        self._core.escalate()

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        from PyQt6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.setStyleSheet(_context_menu_style())

        menu.addSection("Mode")
        for label, icon_name, m in [
            ("Ambient", "fa6s.circle_dot", APRILMode.AMBIENT),
            ("Focus", "fa6s.crosshairs", APRILMode.FOCUS),
            ("Tactical", "fa6s.table_list", APRILMode.TACTICAL),
        ]:
            act = menu.addAction(theme.get_icon(icon_name), label)
            act.setCheckable(True)
            act.setChecked(self._core.mode == m)
            act.triggered.connect(lambda _checked, _m=m: self._core.set_mode(_m))

        menu.addSeparator()
        menu.addAction(theme.get_icon("fa6s.gear"), "Settings …").triggered.connect(
            self._core.settings_requested.emit
        )

        menu.addSeparator()
        state_sub = menu.addMenu(theme.get_icon("fa6s.bug"), "Dev: Set State")
        for s in APRILState:
            a = state_sub.addAction(s.name.capitalize())
            a.triggered.connect(lambda _checked, _s=s: self._core.set_state(_s))

        menu.exec(event.globalPos())

    def _snap_to_corner(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        cx = self.x() + self.width() / 2
        cy = self.y() + self.height() / 2
        is_left = cx < screen.center().x()
        is_top = cy < screen.center().y()
        c = (
            Corner.TOP_LEFT
            if (is_top and is_left)
            else (
                Corner.TOP_RIGHT
                if is_top
                else Corner.BOTTOM_LEFT if is_left else Corner.BOTTOM_RIGHT
            )
        )
        self._core.set_corner(c)

    # ------------------------------------------------------------------ slots

    def _on_state_changed(self, state: APRILState) -> None:
        self._phase = 0.0
        self._timer.setInterval(
            _DORMANT_INTERVAL if state == APRILState.DORMANT else _ACTIVE_INTERVAL
        )
        self._update_mask(state)

    def _on_mode_changed(self, _mode: APRILMode) -> None:
        pass  # orb remains visible in all modes


# ── context menu stylesheet (theme-adaptive) ────────────────────────────────


def _context_menu_style() -> str:
    light = theme.is_light_theme()
    bg = "rgba(245,246,250,235)" if light else "rgba(18,20,32,235)"
    border = "rgba(0,0,0,22)" if light else "rgba(255,255,255,20)"
    color = "rgb(15,23,42)" if light else "rgb(220,230,248)"
    sel_bg = "rgba(8,145,178,18)" if light else "rgba(56,189,248,18)"
    sel_color = "rgb(8,145,178)" if light else "rgb(56,189,248)"
    muted = "rgba(100,116,139,255)" if light else "rgba(100,116,139,255)"
    return f"""
QMenu {{
    background: {bg};
    border: 1px solid {border};
    border-radius: 12px;
    padding: 6px;
    color: {color};
    font-size: 12px;
    font-family: 'Segoe UI Variable Display', 'Segoe UI', sans-serif;
}}
QMenu::item {{
    padding: 7px 20px 7px 10px;
    border-radius: 7px;
}}
QMenu::item:selected {{ background: {sel_bg}; color: {sel_color}; }}
QMenu::item:checked  {{ color: {sel_color}; font-weight: 600; }}
QMenu::separator     {{ height: 1px; background: {border}; margin: 4px 6px; }}
QMenu::section       {{ color: {muted}; font-size: 10px; padding: 6px 12px 3px; }}
"""
