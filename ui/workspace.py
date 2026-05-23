"""
TacticalWorkspace — full diagnostic and orchestration surface.

Larger panel with tabs: Tasks, Nodes, Diagnostics, Log.
Sparse, inspectable, actionable — not a dashboard.
"""
from __future__ import annotations
import math, time
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve,
    QAbstractTableModel, QModelIndex, QSortFilterProxyModel
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPainterPath,
    QLinearGradient, QFont
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QTableView, QHeaderView, QFrame,
    QScrollArea, QSizePolicy, QAbstractItemView, QApplication
)

from .state import APRILCore, APRILMode, APRILState, Corner
from . import theme


class TacticalWorkspace(QWidget):
    """Tactical mode — expanded operational workspace."""

    def __init__(self, core: APRILCore, parent=None):
        super().__init__(parent)
        self._core = core

        self._setup_window()
        self._build_ui()
        self._setup_animation()

        core.mode_changed.connect(self._on_mode_changed)
        core.state_changed.connect(self._on_state_changed)
        core.corner_changed.connect(self._reposition)

        self.hide()

    # ------------------------------------------------------------------ window

    def _setup_window(self):
        self.setFixedSize(theme.WORKSPACE_W, theme.WORKSPACE_H)
        # FIX-03: opaque background — no WA_TranslucentBackground
        self.setStyleSheet("background: rgb(10, 10, 18);")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )

    # ------------------------------------------------------------------ ui

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        bar = QHBoxLayout()

        title = QLabel("APRIL  /  Tactical")
        title.setStyleSheet(
            "color: rgb(34,211,238); font-size: 13px; "
            "font-family: 'JetBrains Mono', Consolas; letter-spacing: 1px;")
        bar.addWidget(title)
        bar.addStretch()

        self._state_pill = _Pill("DORMANT")
        bar.addWidget(self._state_pill)

        focus_btn = QPushButton("↙ Focus")
        focus_btn.setFixedHeight(24)
        focus_btn.setStyleSheet(_BTN_GHOST)
        focus_btn.clicked.connect(self._core.collapse)
        bar.addWidget(focus_btn)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(_BTN_GHOST)
        close_btn.clicked.connect(self._collapse)
        bar.addWidget(close_btn)

        root.addLayout(bar)
        root.addWidget(_divider())

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(_TAB_STYLE)
        self._tabs.addTab(self._build_tasks_tab(),    "Tasks")
        self._tabs.addTab(self._build_nodes_tab(),    "Nodes")
        self._tabs.addTab(self._build_diag_tab(),     "Diagnostics")
        self._tabs.addTab(self._build_log_tab(),      "Log")
        root.addWidget(self._tabs)

    # ------------------------------------------------------------------ tabs

    def _build_tasks_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(8)

        summary = QHBoxLayout()
        for label, val, color in [
            ("Running",   "0", "rgb(34,211,238)"),
            ("Suspended", "0", "rgb(251,191,36)"),
            ("Complete",  "0", "rgb(100,200,120)"),
        ]:
            cell = _StatCell(label, val, color)
            summary.addWidget(cell)
        layout.addLayout(summary)
        layout.addWidget(_divider())

        self._task_model = _TaskModel()
        tv = _Table(self._task_model)
        layout.addWidget(tv)

        act = QHBoxLayout()
        act.addStretch()
        for label in ["Resume", "Cancel", "Clear Done"]:
            btn = QPushButton(label)
            btn.setFixedHeight(26)
            btn.setStyleSheet(_BTN_GHOST)
            act.addWidget(btn)
        layout.addLayout(act)

        return w

    def _build_nodes_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(8)

        self._node_model = _NodeModel()
        self._node_model.add("mac (inference)",  "online",  "Ollama · Qdrant · Oracle")
        self._node_model.add("dell (apps)",      "online",  "Docker stack · StoragePool")
        self._node_model.add("cortex (gateway)", "online",  "LiteLLM v1.82.3")

        tv = _Table(self._node_model)
        layout.addWidget(tv)

        act = QHBoxLayout()
        act.addStretch()
        for label in ["Ping", "Remove", "Add Node…"]:
            btn = QPushButton(label)
            btn.setFixedHeight(26)
            btn.setStyleSheet(_BTN_GHOST if label != "Add Node…" else _BTN_ACCENT)
            act.addWidget(btn)
        layout.addLayout(act)

        return w

    def _build_diag_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(10)

        grid = QHBoxLayout()
        grid.setSpacing(10)
        self._cpu_cell  = _MetricCell("CPU", "—")
        self._mem_cell  = _MetricCell("Memory", "—")
        self._lat_cell  = _MetricCell("Latency", "—")
        self._sess_cell = _MetricCell("Session", "—")
        for cell in [self._cpu_cell, self._mem_cell, self._lat_cell, self._sess_cell]:
            grid.addWidget(cell)
        layout.addLayout(grid)

        layout.addWidget(_divider())

        spark_label = QLabel("Uptime / Response latency")
        spark_label.setStyleSheet("color: rgb(113,113,122); font-size: 10px;")
        layout.addWidget(spark_label)

        self._sparkline = _Sparkline()
        layout.addWidget(self._sparkline)
        layout.addStretch()

        # FIX-07: timer created but NOT started here — started in expand(), stopped in _on_collapse_done()
        self._diag_timer = QTimer(self)
        self._diag_timer.setInterval(1000)
        self._diag_timer.timeout.connect(self._refresh_diag)

        return w

    def _build_log_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(6)

        self._log_area = QLabel()
        self._log_area.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._log_area.setWordWrap(True)
        self._log_area.setStyleSheet(
            "color: rgb(140,160,180); font-family: 'JetBrains Mono', Consolas; "
            "font-size: 10px; line-height: 1.7;"
        )
        self._log_entries: list[str] = []
        self._refresh_log()

        scroll = QScrollArea()
        scroll.setWidget(self._log_area)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        layout.addWidget(scroll)

        act = QHBoxLayout()
        act.addStretch()
        btn = QPushButton("Clear Log")
        btn.setFixedHeight(26)
        btn.setStyleSheet(_BTN_GHOST)
        btn.clicked.connect(self._clear_log)
        act.addWidget(btn)
        layout.addLayout(act)

        return w

    # ------------------------------------------------------------------ animation

    def _setup_animation(self):
        self._opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self._opacity_anim.setDuration(theme.TRANSITION_NORMAL)
        self._opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def expand(self):
        self._reposition(self._core.corner)
        self.setWindowOpacity(0.0)
        self.show()
        self._opacity_anim.setStartValue(0.0)
        self._opacity_anim.setEndValue(1.0)
        self._opacity_anim.start()
        # FIX-07: start diag timer only when visible
        if hasattr(self, '_diag_timer'):
            self._diag_timer.start()

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
        self._opacity_anim.finished.disconnect(self._on_collapse_done)
        # FIX-07: stop diag timer when hidden
        if hasattr(self, '_diag_timer'):
            self._diag_timer.stop()
        self._core.set_mode(APRILMode.FOCUS)

    # ------------------------------------------------------------------ positioning

    def _reposition(self, corner: Corner):
        screen = QApplication.primaryScreen().availableGeometry()
        m = theme.CORNER_MARGIN
        w, h = self.width(), self.height()
        match corner:
            case Corner.BOTTOM_RIGHT: x, y = screen.right() - w - m, screen.bottom() - h - m
            case Corner.BOTTOM_LEFT:  x, y = screen.left() + m,      screen.bottom() - h - m
            case Corner.TOP_RIGHT:    x, y = screen.right() - w - m, screen.top() + m
            case Corner.TOP_LEFT:     x, y = screen.left() + m,      screen.top() + m
        self.move(x, y)

    # ------------------------------------------------------------------ painting

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 20, 20)

        p.setClipPath(path)
        p.fillRect(0, 0, self.width(), self.height(), QColor(10, 10, 18, 218))

        grad = QLinearGradient(0, 0, 0, 80)
        grad.setColorAt(0, QColor(255, 255, 255, 14))
        grad.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(0, 0, self.width(), 80, grad)

        p.setClipping(False)
        pen = QPen(QColor(255, 255, 255, 28))
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.end()

    # ------------------------------------------------------------------ helpers

    def _refresh_diag(self):
        import random
        self._cpu_cell.set_value(f"{random.randint(5, 40)} %")
        self._mem_cell.set_value(f"{random.uniform(0.8, 2.0):.1f} GB")
        self._lat_cell.set_value(f"{random.randint(80, 400)} ms")
        elapsed = int(time.monotonic()) % 3600
        self._sess_cell.set_value(f"{elapsed // 60}m {elapsed % 60}s")
        self._sparkline.push(random.randint(80, 400))

    def _refresh_log(self):
        self._log_area.setText("\n".join(self._log_entries))

    def _clear_log(self):
        self._log_entries.clear()
        self._refresh_log()

    def append_log(self, msg: str):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_entries.append(f"[{ts}]  {msg}")
        if len(self._log_entries) > 200:
            self._log_entries = self._log_entries[-200:]
        self._refresh_log()

    # ------------------------------------------------------------------ slots

    def _on_mode_changed(self, mode: APRILMode):
        if mode == APRILMode.TACTICAL:
            self.expand()
        elif self.isVisible():
            self._collapse()

    def _on_state_changed(self, state: APRILState):
        self._state_pill.setText(state.name)
        colors = {
            APRILState.DORMANT:   "rgb(113,113,122)",
            APRILState.LISTENING: "rgb(34,211,238)",
            APRILState.THINKING:  "rgb(34,211,238)",
            APRILState.SPEAKING:  "rgb(34,211,238)",
            APRILState.ACTING:    "rgb(34,211,238)",
            APRILState.WARNING:   "rgb(251,191,36)",
            APRILState.ERROR:     "rgb(239,68,68)",
        }
        c = colors.get(state, "rgb(113,113,122)")
        self._state_pill.setStyleSheet(
            f"color: {c}; background: transparent; "
            f"border: 1px solid {c}; border-radius: 4px; "
            "font-size: 9px; font-family: 'JetBrains Mono', Consolas; "
            "padding: 2px 6px; letter-spacing: 1px;"
        )


# ------------------------------------------------------------------ models

class _TaskModel(QAbstractTableModel):
    _HEADERS = ["Task", "Status", "Elapsed"]

    def __init__(self):
        super().__init__()
        self._data: list[list[str]] = []

    def add(self, name, status, elapsed):
        self._data.append([name, status, elapsed])
        self.layoutChanged.emit()

    def rowCount(self, _=QModelIndex()): return len(self._data)
    def columnCount(self, _=QModelIndex()): return 3
    def headerData(self, s, o, role=Qt.ItemDataRole.DisplayRole):
        if o == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self._HEADERS[s]
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            return self._data[index.row()][index.column()]
        if role == Qt.ItemDataRole.ForegroundRole:
            status = self._data[index.row()][1]
            from PyQt6.QtGui import QBrush
            colors = {"running": QColor(34,211,238), "suspended": QColor(251,191,36),
                      "background": QColor(140,160,180)}
            if index.column() == 1:
                return QBrush(colors.get(status, QColor(220,240,255)))
            return QBrush(QColor(220, 240, 255))


class _NodeModel(QAbstractTableModel):
    _HEADERS = ["Node", "Status", "Info"]

    def __init__(self):
        super().__init__()
        self._data: list[list[str]] = []

    def add(self, name, status, info):
        self._data.append([name, status, info])
        self.layoutChanged.emit()

    def rowCount(self, _=QModelIndex()): return len(self._data)
    def columnCount(self, _=QModelIndex()): return 3
    def headerData(self, s, o, role=Qt.ItemDataRole.DisplayRole):
        if o == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self._HEADERS[s]
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            return self._data[index.row()][index.column()]
        if role == Qt.ItemDataRole.ForegroundRole:
            from PyQt6.QtGui import QBrush
            if index.column() == 1:
                status = self._data[index.row()][1]
                c = QColor(34,211,238) if status == "online" else QColor(239,68,68)
                return QBrush(c)
            return QBrush(QColor(220, 240, 255))


# ------------------------------------------------------------------ small widgets

class _Table(QTableView):
    def __init__(self, model):
        super().__init__()
        self.setModel(model)
        self.setStyleSheet(_TABLE_STYLE)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.verticalHeader().hide()
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(False)
        self.setAlternatingRowColors(False)


class _StatCell(QFrame):
    def __init__(self, label: str, value: str, color: str):
        super().__init__()
        self.setStyleSheet(
            "background: rgba(255,255,255,6); border: 1px solid rgba(255,255,255,15); "
            "border-radius: 8px;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(2)
        self._val = QLabel(value)
        self._val.setStyleSheet(f"color: {color}; font-size: 20px; font-family: 'JetBrains Mono', Consolas; border: none;")
        lbl = QLabel(label)
        lbl.setStyleSheet("color: rgb(113,113,122); font-size: 10px; border: none;")
        lay.addWidget(self._val)
        lay.addWidget(lbl)

    def set_value(self, v: str): self._val.setText(v)


class _MetricCell(QFrame):
    def __init__(self, label: str, value: str):
        super().__init__()
        self.setStyleSheet(
            "background: rgba(255,255,255,6); border: 1px solid rgba(255,255,255,15); "
            "border-radius: 8px;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(1)
        lbl = QLabel(label)
        lbl.setStyleSheet("color: rgb(113,113,122); font-size: 9px; border: none;")
        self._val = QLabel(value)
        self._val.setStyleSheet(
            "color: rgb(220,240,255); font-size: 13px; "
            "font-family: 'JetBrains Mono', Consolas; border: none;")
        lay.addWidget(lbl)
        lay.addWidget(self._val)

    def set_value(self, v: str): self._val.setText(v)


class _Sparkline(QWidget):
    MAX = 60

    def __init__(self):
        super().__init__()
        self.setFixedHeight(48)
        self._data: list[int] = []

    def push(self, v: int):
        self._data.append(v)
        if len(self._data) > self.MAX:
            self._data.pop(0)
        self.update()

    def paintEvent(self, _):
        if len(self._data) < 2:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        mn, mx = min(self._data), max(self._data)
        rng = mx - mn or 1
        pts = []
        for i, v in enumerate(self._data):
            x = i * w / (self.MAX - 1)
            y = h - (v - mn) / rng * (h - 4) - 2
            pts.append((x, y))

        path = QPainterPath()
        path.moveTo(pts[0][0], pts[0][1])
        for x, y in pts[1:]:
            path.lineTo(x, y)

        pen = QPen(QColor(34, 211, 238, 180))
        pen.setWidthF(1.5)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.end()


class _Pill(QLabel):
    def __init__(self, text: str):
        super().__init__(text)
        self.setStyleSheet(
            "color: rgb(113,113,122); background: transparent; "
            "border: 1px solid rgb(113,113,122); border-radius: 4px; "
            "font-size: 9px; font-family: 'JetBrains Mono', Consolas; "
            "padding: 2px 6px; letter-spacing: 1px;"
        )


def _divider() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("color: rgba(255,255,255,18);")
    return line


_BTN_GHOST = """
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
"""

_BTN_ACCENT = """
QPushButton {
    background: rgba(34,211,238,160);
    color: rgb(10,10,20);
    border: none;
    border-radius: 6px;
    font-size: 11px;
    padding: 0 10px;
    font-family: 'Inter', 'Segoe UI';
}
QPushButton:hover { background: rgba(34,211,238,210); }
"""

_TAB_STYLE = """
QTabWidget::pane { border: none; background: transparent; }
QTabBar::tab {
    background: transparent;
    color: rgb(113,113,122);
    font-size: 11px;
    font-family: 'Inter', 'Segoe UI';
    padding: 6px 16px;
    border: none;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:selected {
    color: rgb(34,211,238);
    border-bottom: 2px solid rgb(34,211,238);
}
QTabBar::tab:hover { color: rgb(200,220,240); }
"""

_TABLE_STYLE = """
QTableView {
    background: transparent;
    border: none;
    color: rgb(220,240,255);
    font-size: 11px;
    font-family: 'Inter', 'Segoe UI';
    selection-background-color: rgba(34,211,238,30);
    gridline-color: transparent;
}
QHeaderView::section {
    background: rgba(255,255,255,6);
    color: rgb(113,113,122);
    font-size: 10px;
    font-family: 'JetBrains Mono', Consolas;
    border: none;
    padding: 4px 8px;
}
QTableView::item { padding: 4px 8px; border-bottom: 1px solid rgba(255,255,255,8); }
QTableView::item:selected { background: rgba(34,211,238,30); }
"""
