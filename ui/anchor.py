"""
AmbientAnchor — the persistent corner orb.

Frameless, always-on-top, opaque with circular mask.  Custom-painted state
animations driven by a QTimer at ~60 fps.  Drag snaps to nearest screen corner.
"""
from __future__ import annotations
import math
from PyQt6.QtCore import (
    Qt, QTimer, QPoint, QRect, QPropertyAnimation,
    QEasingCurve, pyqtProperty, QSize
)
from PyQt6.QtGui import (
    QPainter, QPen, QBrush, QRadialGradient, QColor,
    QLinearGradient, QPainterPath, QCursor
)
from PyQt6.QtWidgets import QWidget, QApplication

from .state import APRILCore, APRILState, APRILMode, Corner
from . import theme


_STATE_COLORS: dict[APRILState, tuple[QColor, QColor]] = {
    APRILState.DORMANT:   (theme.CYAN_20,  theme.CYAN_40),
    APRILState.LISTENING: (theme.CYAN_40,  theme.CYAN_80),
    APRILState.THINKING:  (theme.CYAN_40,  theme.CYAN_80),
    APRILState.SPEAKING:  (theme.CYAN_80,  theme.CYAN),
    APRILState.ACTING:    (theme.CYAN_40,  theme.CYAN_80),
    APRILState.WARNING:   (theme.AMBER_80, theme.AMBER),
    APRILState.ERROR:     (theme.RED_80,   theme.RED),
}


class AmbientAnchor(QWidget):
    """Small always-on-top orb that lives in a screen corner."""

    # Extra hit-area padding so the widget is easy to click
    _PAD = 12

    def __init__(self, core: APRILCore, parent=None):
        super().__init__(parent)
        self._core = core
        self._phase = 0.0          # animation phase 0–1 (cycles)
        self._drag_start: QPoint | None = None
        self._widget_origin: QPoint | None = None

        # Opacity used for fade-in/out transitions
        self._opacity = 1.0

        self._setup_window()
        self._place_in_corner(core.corner)

        self._timer = QTimer(self)
        self._timer.setInterval(theme.ANIMATION_INTERVAL)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        core.state_changed.connect(self._on_state_changed)
        core.mode_changed.connect(self._on_mode_changed)
        core.corner_changed.connect(self._place_in_corner)

    # ------------------------------------------------------------------ setup

    def _setup_window(self):
        size = theme.ORB_SIZE + self._PAD * 2
        self.setFixedSize(size, size)
        # FIX-01: opaque background — no WA_TranslucentBackground
        self.setStyleSheet("background: rgb(7, 11, 16);")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool               # no taskbar entry
        )
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        # FIX-11: do NOT use setMask — on Windows with DPI scaling the
        # QRegion ellipse mask makes the window invisible or unclickable.
        # Circular appearance is achieved purely in paintEvent (fills corners
        # with the background colour).  Mouse events work on the full square
        # hit-area which is intentional — _PAD gives extra click margin.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

    def _place_in_corner(self, corner: Corner):
        screen = QApplication.primaryScreen().availableGeometry()
        m = theme.CORNER_MARGIN
        s = self.width()
        match corner:
            case Corner.BOTTOM_RIGHT: pos = QPoint(screen.right()  - s - m, screen.bottom() - s - m)
            case Corner.BOTTOM_LEFT:  pos = QPoint(screen.left()   + m,     screen.bottom() - s - m)
            case Corner.TOP_RIGHT:    pos = QPoint(screen.right()  - s - m, screen.top()    + m)
            case Corner.TOP_LEFT:     pos = QPoint(screen.left()   + m,     screen.top()    + m)
        self.move(pos)

    # ------------------------------------------------------------------ animation

    def _tick(self):
        state = self._core.state
        speeds = {
            APRILState.DORMANT:   0.003,
            APRILState.LISTENING: 0.012,
            APRILState.THINKING:  0.018,
            APRILState.SPEAKING:  0.025,
            APRILState.ACTING:    0.015,
            APRILState.WARNING:   0.020,
            APRILState.ERROR:     0.030,
        }
        self._phase = (self._phase + speeds.get(state, 0.005)) % 1.0
        self.update()

    # ------------------------------------------------------------------ painting

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self._opacity)

        cx = self.width()  / 2
        cy = self.height() / 2
        r  = theme.ORB_SIZE / 2

        # Fill circular area with dark background (FIX-01: explicit fill instead of transparency)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(7, 11, 16)))
        p.drawEllipse(int(cx - r), int(cy - r), int(r * 2), int(r * 2))

        state = self._core.state
        dim_col, bright_col = _STATE_COLORS[state]

        self._draw_glow(p, cx, cy, r, bright_col)
        self._draw_base(p, cx, cy, r, dim_col)

        match state:
            case APRILState.DORMANT:   self._draw_dormant(p, cx, cy, r, bright_col)
            case APRILState.LISTENING: self._draw_listening(p, cx, cy, r, bright_col)
            case APRILState.THINKING:  self._draw_thinking(p, cx, cy, r, bright_col)
            case APRILState.SPEAKING:  self._draw_speaking(p, cx, cy, r, bright_col)
            case APRILState.ACTING:    self._draw_acting(p, cx, cy, r, bright_col)
            case APRILState.WARNING:   self._draw_pulse(p, cx, cy, r, bright_col)
            case APRILState.ERROR:     self._draw_pulse(p, cx, cy, r, bright_col, fast=True)

        # Rim highlight
        pen = QPen(QColor(255, 255, 255, 35))
        pen.setWidth(1)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(int(cx - r), int(cy - r), int(r * 2), int(r * 2))

        p.end()

    def _draw_glow(self, p: QPainter, cx, cy, r, color: QColor):
        glow_r = r + 10 + math.sin(self._phase * math.tau) * 4
        grad = QRadialGradient(cx, cy, glow_r)
        c = QColor(color)
        c.setAlpha(60)
        grad.setColorAt(0.0, c)
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawEllipse(int(cx - glow_r), int(cy - glow_r),
                      int(glow_r * 2), int(glow_r * 2))

    def _draw_base(self, p: QPainter, cx, cy, r, color: QColor):
        grad = QRadialGradient(cx, cy - r * 0.3, r * 1.2)
        light = QColor(255, 255, 255, 18)
        dark  = QColor(10, 10, 20, 180)
        grad.setColorAt(0.0, light)
        grad.setColorAt(1.0, dark)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawEllipse(int(cx - r), int(cy - r), int(r * 2), int(r * 2))

    def _draw_dormant(self, p: QPainter, cx, cy, r, color: QColor):
        # FIX-06: slow opacity pulse only — static size, no breathing
        alpha = int(70 + math.sin(self._phase * math.tau) * 35)
        c = QColor(color)
        c.setAlpha(alpha)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(c))
        dot_r = 3.5  # static — no radius breathing
        p.drawEllipse(int(cx - dot_r), int(cy - dot_r), int(dot_r * 2), int(dot_r * 2))

    def _draw_listening(self, p: QPainter, cx, cy, r, color: QColor):
        for i in range(3):
            offset = (self._phase + i / 3) % 1.0
            ring_r = r * 0.3 + offset * r * 0.65
            alpha  = int((1 - offset) * 140)
            c = QColor(color)
            c.setAlpha(alpha)
            pen = QPen(c)
            pen.setWidthF(1.5)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(int(cx - ring_r), int(cy - ring_r),
                          int(ring_r * 2), int(ring_r * 2))

    def _draw_thinking(self, p: QPainter, cx, cy, r, color: QColor):
        angle = self._phase * 360
        arc_r = r * 0.68
        pen = QPen(QColor(color.red(), color.green(), color.blue(), 40))
        pen.setWidthF(1.5)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        rect = QRect(int(cx - arc_r), int(cy - arc_r),
                     int(arc_r * 2), int(arc_r * 2))
        p.drawEllipse(rect)

        bright_pen = QPen(color)
        bright_pen.setWidthF(2.0)
        bright_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(bright_pen)
        p.drawArc(rect, int((angle % 360) * 16), int(90 * 16))

    def _draw_speaking(self, p: QPainter, cx, cy, r, color: QColor):
        bar_count = 5
        bar_w = 2.5
        gap   = 4.0
        total_w = bar_count * bar_w + (bar_count - 1) * gap
        x0 = cx - total_w / 2

        for i in range(bar_count):
            bx = x0 + i * (bar_w + gap)
            h = (r * 0.3 + math.sin(
                self._phase * math.tau * (1 + i * 0.4) + i) * r * 0.45)
            c = QColor(color)
            c.setAlpha(180 + int(i * 12))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(c))
            p.drawRoundedRect(
                int(bx), int(cy - h / 2),
                int(bar_w), int(h), 1, 1)

    def _draw_acting(self, p: QPainter, cx, cy, r, color: QColor):
        arc_r = r * 0.65
        angle = self._phase * 360

        base = QColor(color)
        base.setAlpha(35)
        pen = QPen(base)
        pen.setWidthF(1.5)
        pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        rect = QRect(int(cx - arc_r), int(cy - arc_r),
                     int(arc_r * 2), int(arc_r * 2))
        p.drawEllipse(rect)

        bright = QPen(color)
        bright.setWidthF(2.0)
        bright.setCapStyle(Qt.PenCapStyle.RoundCap)
        bright.setStyle(Qt.PenStyle.SolidLine)
        p.setPen(bright)
        p.drawArc(rect, int((angle % 360) * 16), int(60 * 16))

    def _draw_pulse(self, p: QPainter, cx, cy, r, color: QColor, fast=False):
        freq = 2 if fast else 1
        pulse = (math.sin(self._phase * math.tau * freq) + 1) / 2
        ring_r = r * 0.3 + pulse * r * 0.6
        alpha  = int((1 - pulse) * 160)
        c = QColor(color)
        c.setAlpha(alpha)
        pen = QPen(c)
        pen.setWidthF(2.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(int(cx - ring_r), int(cy - ring_r),
                      int(ring_r * 2), int(ring_r * 2))

        dot_r = 4 + pulse * 2
        c2 = QColor(color)
        c2.setAlpha(200)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(c2))
        p.drawEllipse(int(cx - dot_r), int(cy - dot_r),
                      int(dot_r * 2), int(dot_r * 2))

    # ------------------------------------------------------------------ interaction

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start    = event.globalPosition().toPoint()
            self._widget_origin = self.pos()

    def mouseMoveEvent(self, event):
        if self._drag_start is not None:
            delta = event.globalPosition().toPoint() - self._drag_start
            self.move(self._widget_origin + delta)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start is not None:
            self._drag_start = None
            self._snap_to_corner()

    def mouseDoubleClickEvent(self, _event):
        self._core.escalate()

    def contextMenuEvent(self, event):
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet(_MENU_STYLE)

        menu.addSection("Mode")
        for label, m in [("Ambient", APRILMode.AMBIENT),
                          ("Focus",   APRILMode.FOCUS),
                          ("Tactical", APRILMode.TACTICAL)]:
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(self._core.mode == m)
            act.triggered.connect(lambda checked, _m=m: self._core.set_mode(_m))

        menu.addSeparator()
        menu.addAction("Settings …").triggered.connect(
            self._core.settings_requested.emit)
        menu.addSeparator()

        state_menu = menu.addMenu("Dev: Set State")
        for s in APRILState:
            a = state_menu.addAction(s.name.capitalize())
            a.triggered.connect(lambda checked, _s=s: self._core.set_state(_s))

        menu.exec(event.globalPos())

    def _snap_to_corner(self):
        screen = QApplication.primaryScreen().availableGeometry()
        cx = self.x() + self.width()  / 2
        cy = self.y() + self.height() / 2
        is_left = cx < screen.center().x()
        is_top  = cy < screen.center().y()
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
        self._phase = 0.0
        # FIX-06: dormant at 15fps, active states at 60fps
        if state == APRILState.DORMANT:
            self._timer.setInterval(66)
        else:
            self._timer.setInterval(theme.ANIMATION_INTERVAL)

    def _on_mode_changed(self, mode):
        pass  # orb visible in all modes


_MENU_STYLE = """
QMenu {
    background: rgba(10,10,20,230);
    border: 1px solid rgba(255,255,255,25);
    border-radius: 10px;
    padding: 4px;
    color: rgb(220,240,255);
    font-size: 12px;
}
QMenu::item { padding: 6px 18px 6px 12px; border-radius: 6px; }
QMenu::item:selected { background: rgba(34,211,238,35); }
QMenu::item:checked { color: rgb(34,211,238); }
QMenu::separator { height: 1px; background: rgba(255,255,255,15); margin: 3px 0; }
QMenu::section { color: rgba(113,113,122,255); font-size: 10px; padding: 4px 12px 2px; }
"""
