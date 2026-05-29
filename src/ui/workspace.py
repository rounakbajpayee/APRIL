"""
TacticalWorkspace — full diagnostic and orchestration surface.

Larger panel with tabs: Tasks, Nodes, Diagnostics, Log.
Designed in Microsoft Fluent Design (adapts to light/dark system themes).
"""

from __future__ import annotations
import math
import time
from datetime import datetime
from PyQt6.QtCore import (
    Qt,
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
    QAbstractTableModel,
    QModelIndex,
    QSortFilterProxyModel,
)
from PyQt6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QBrush,
    QPainterPath,
    QLinearGradient,
    QFont,
)
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QTableView,
    QHeaderView,
    QFrame,
    QScrollArea,
    QSizePolicy,
    QAbstractItemView,
    QApplication,
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
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )

    # ------------------------------------------------------------------ ui

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        bar = QHBoxLayout()

        self._title = QLabel("APRIL  /  Tactical")
        self._title.setStyleSheet(
            "color: rgb(34,211,238); font-size: 13px; "
            "font-family: 'Segoe UI Variable Display', Consolas; letter-spacing: 1px;"
        )
        bar.addWidget(self._title)
        bar.addStretch()

        self._state_pill = _Pill("DORMANT")
        bar.addWidget(self._state_pill)

        self._focus_btn = QPushButton("↙ Focus")
        self._focus_btn.setFixedHeight(24)
        self._focus_btn.clicked.connect(self._core.collapse)
        bar.addWidget(self._focus_btn)

        self._close_btn = QPushButton("✕")
        self._close_btn.setFixedSize(24, 24)
        self._close_btn.clicked.connect(self._collapse)
        bar.addWidget(self._close_btn)

        root.addLayout(bar)
        self._div1 = _divider()
        root.addWidget(self._div1)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_tasks_tab(), "Tasks")
        self._tabs.addTab(self._build_nodes_tab(), "Nodes")
        self._tabs.addTab(self._build_diag_tab(), "Diagnostics")
        self._tabs.addTab(self._build_log_tab(), "Log")
        root.addWidget(self._tabs)

        self._apply_theme()

    # ------------------------------------------------------------------ tabs

    def _build_tasks_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(8)

        summary = QHBoxLayout()
        for label, val, color in [
            ("Running", "0", "rgb(34,211,238)"),
            ("Suspended", "0", "rgb(251,191,36)"),
            ("Complete", "0", "rgb(100,200,120)"),
        ]:
            cell = _StatCell(label, val, color)
            summary.addWidget(cell)
        layout.addLayout(summary)

        self._task_div = _divider()
        layout.addWidget(self._task_div)

        self._task_model = _TaskModel()
        tv = _Table(self._task_model)
        layout.addWidget(tv)

        act = QHBoxLayout()
        act.addStretch()
        self._task_btns = []
        for label in ["Resume", "Cancel", "Clear Done"]:
            btn = QPushButton(label)
            btn.setFixedHeight(26)
            act.addWidget(btn)
            self._task_btns.append(btn)
        layout.addLayout(act)

        return w

    def _build_nodes_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(8)

        self._node_model = _NodeModel()
        self._node_model.add("mac (inference)", "online", "Ollama · Qdrant · Oracle")
        self._node_model.add("dell (apps)", "online", "Docker stack · StoragePool")
        self._node_model.add("cortex (gateway)", "online", "LiteLLM v1.82.3")

        tv = _Table(self._node_model)
        layout.addWidget(tv)

        act = QHBoxLayout()
        act.addStretch()
        self._node_btns = []
        for label in ["Ping", "Remove", "Add Node…"]:
            btn = QPushButton(label)
            btn.setFixedHeight(26)
            act.addWidget(btn)
            self._node_btns.append(btn)
        layout.addLayout(act)

        return w

    def _build_diag_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(10)

        grid = QHBoxLayout()
        grid.setSpacing(10)
        self._cpu_cell = _MetricCell("CPU", "—")
        self._mem_cell = _MetricCell("Memory", "—")
        self._lat_cell = _MetricCell("Latency", "—")
        self._sess_cell = _MetricCell("Session", "—")
        for cell in [self._cpu_cell, self._mem_cell, self._lat_cell, self._sess_cell]:
            grid.addWidget(cell)
        layout.addLayout(grid)

        self._diag_div = _divider()
        layout.addWidget(self._diag_div)

        self._spark_label = QLabel("Uptime / Response latency")
        self._spark_label.setFont(theme.ui_font(10))
        layout.addWidget(self._spark_label)

        self._sparkline = _Sparkline()
        layout.addWidget(self._sparkline)
        layout.addStretch()

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
        self._log_entries: list[str] = []
        self._refresh_log()

        scroll = QScrollArea()
        scroll.setWidget(self._log_area)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        layout.addWidget(scroll)

        act = QHBoxLayout()
        act.addStretch()
        self._clear_btn = QPushButton("Clear Log")
        self._clear_btn.setFixedHeight(26)
        self._clear_btn.clicked.connect(self._clear_log)
        act.addWidget(self._clear_btn)
        layout.addLayout(act)

        return w

    # ------------------------------------------------------------------ theme

    def _apply_theme(self):
        is_light = theme.is_light_theme()
        txt_color = "rgb(30,30,42)" if is_light else "rgb(220,240,255)"
        title_color = "rgb(8,145,178)" if is_light else "rgb(34,211,238)"
        muted_color = "rgb(115,115,125)" if is_light else "rgb(113,113,122)"

        # Title
        self._title.setStyleSheet(
            f"color: {title_color}; font-size: 13px; "
            f"font-family: 'Segoe UI Variable Display', Consolas; letter-spacing: 1px; background: transparent;"
        )

        # Tabs stylesheet
        self._tabs.setStyleSheet(_tab_style())

        # Header buttons
        self._focus_btn.setStyleSheet(_btn_ghost_style())
        self._close_btn.setStyleSheet(_btn_ghost_style())

        # State pill style update
        self._on_state_changed(self._core.state)

        # Dividers
        self._div1.setStyleSheet(_divider_style())
        if hasattr(self, "_task_div"):
            self._task_div.setStyleSheet(_divider_style())
        if hasattr(self, "_diag_div"):
            self._diag_div.setStyleSheet(_divider_style())

        # Sub-widgets
        for cell in self.findChildren(_StatCell):
            cell._apply_theme()
        for cell in self.findChildren(_MetricCell):
            cell._apply_theme()
        for table in self.findChildren(_Table):
            table.setStyleSheet(_table_style())
            table.horizontalHeader().setStyleSheet(_header_style())

        # Action buttons
        if hasattr(self, "_task_btns"):
            for btn in self._task_btns:
                btn.setStyleSheet(_btn_ghost_style())
        if hasattr(self, "_node_btns"):
            for btn in self._node_btns:
                if btn.text() == "Add Node…":
                    btn.setStyleSheet(_btn_accent_style())
                else:
                    btn.setStyleSheet(_btn_ghost_style())
        if hasattr(self, "_clear_btn"):
            self._clear_btn.setStyleSheet(_btn_ghost_style())

        # Diagnostic spark text
        if hasattr(self, "_spark_label"):
            self._spark_label.setStyleSheet(
                f"color: {muted_color}; background: transparent;"
            )

        # Log text
        self._log_area.setStyleSheet(
            f"color: {txt_color}; font-family: 'Segoe UI Mono', Consolas; "
            "font-size: 10px; line-height: 1.7; background: transparent;"
        )

    # ------------------------------------------------------------------ animation

    def _setup_animation(self):
        self._opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self._opacity_anim.setDuration(theme.TRANSITION_NORMAL)
        self._opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def expand(self):
        theme.refresh_theme()
        self._apply_theme()

        self._reposition(self._core.corner)
        self.setWindowOpacity(0.0)
        self.show()
        self._opacity_anim.setStartValue(0.0)
        self._opacity_anim.setEndValue(1.0)
        self._opacity_anim.start()
        if hasattr(self, "_diag_timer"):
            self._diag_timer.start()

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
        self._opacity_anim.finished.disconnect(self._on_collapse_done)
        if hasattr(self, "_diag_timer"):
            self._diag_timer.stop()
        self._core.set_mode(APRILMode.FOCUS)

    # ------------------------------------------------------------------ positioning

    def _reposition(self, corner: Corner):
        screen = QApplication.primaryScreen().availableGeometry()
        m = theme.CORNER_MARGIN
        w, h = self.width(), self.height()
        match corner:
            case Corner.BOTTOM_RIGHT:
                x, y = screen.right() - w - m, screen.bottom() - h - m
            case Corner.BOTTOM_LEFT:
                x, y = screen.left() + m, screen.bottom() - h - m
            case Corner.TOP_RIGHT:
                x, y = screen.right() - w - m, screen.top() + m
            case Corner.TOP_LEFT:
                x, y = screen.left() + m, screen.top() + m
        self.move(x, y)

    # ------------------------------------------------------------------ painting

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 20, 20)

        p.setClipPath(path)
        p.fillRect(0, 0, self.width(), self.height(), theme.BG_BASE)

        grad = QLinearGradient(0, 0, 0, 80)
        grad.setColorAt(
            0,
            (
                QColor(255, 255, 255, 14)
                if not theme.is_light_theme()
                else QColor(0, 0, 0, 8)
            ),
        )
        grad.setColorAt(1, QColor(0, 0, 0, 0))
        p.fillRect(0, 0, self.width(), 80, grad)

        p.setClipping(False)
        pen = QPen(theme.BORDER)
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
            APRILState.DORMANT: "rgb(113,113,122)",
            APRILState.LISTENING: "rgb(34,211,238)",
            APRILState.THINKING: "rgb(34,211,238)",
            APRILState.SPEAKING: "rgb(34,211,238)",
            APRILState.ACTING: "rgb(34,211,238)",
            APRILState.WARNING: "rgb(251,191,36)",
            APRILState.ERROR: "rgb(239,68,68)",
        }
        c = colors.get(state, "rgb(113,113,122)")
        self._state_pill.setStyleSheet(
            f"color: {c}; background: transparent; "
            f"border: 1px solid {c}; border-radius: 4px; "
            "font-size: 9px; font-family: 'Segoe UI Variable Display', Consolas; "
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

    def rowCount(self, _=QModelIndex()):
        return len(self._data)

    def columnCount(self, _=QModelIndex()):
        return 3

    def headerData(self, s, o, role=Qt.ItemDataRole.DisplayRole):
        if o == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self._HEADERS[s]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            return self._data[index.row()][index.column()]
        if role == Qt.ItemDataRole.ForegroundRole:
            status = self._data[index.row()][1]
            from PyQt6.QtGui import QBrush

            colors = {
                "running": QColor(34, 211, 238),
                "suspended": QColor(251, 191, 36),
                "background": QColor(140, 160, 180),
            }
            if index.column() == 1:
                return QBrush(colors.get(status, QColor(220, 240, 255)))
            return QBrush(QColor(220, 240, 255))


class _NodeModel(QAbstractTableModel):
    _HEADERS = ["Node", "Status", "Info"]

    def __init__(self):
        super().__init__()
        self._data: list[list[str]] = []

    def add(self, name, status, info):
        self._data.append([name, status, info])
        self.layoutChanged.emit()

    def rowCount(self, _=QModelIndex()):
        return len(self._data)

    def columnCount(self, _=QModelIndex()):
        return 3

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
                c = QColor(34, 211, 238) if status == "online" else QColor(239, 68, 68)
                return QBrush(c)
            return QBrush(QColor(220, 240, 255))


# ------------------------------------------------------------------ small widgets


class _Table(QTableView):

    def __init__(self, model):
        super().__init__()
        self.setModel(model)
        self.setStyleSheet(_table_style())
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.verticalHeader().hide()
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(False)
        self.setAlternatingRowColors(False)


class _StatCell(QFrame):

    def __init__(self, label: str, value: str, color: str):
        super().__init__()
        self._color = color
        self._label_str = label
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(2)
        self._val = QLabel(value)
        self._lbl = QLabel(label)
        lay.addWidget(self._val)
        lay.addWidget(self._lbl)
        self._apply_theme()

    def _apply_theme(self):
        is_light = theme.is_light_theme()
        bg = "rgba(0,0,0,10)" if is_light else "rgba(255,255,255,6)"
        border = (
            "1px solid rgba(0,0,0,18)" if is_light else "1px solid rgba(255,255,255,15)"
        )
        self.setStyleSheet(f"background: {bg}; border: {border}; border-radius: 8px;")

        self._val.setStyleSheet(
            f"color: {self._color}; font-size: 20px; font-family: 'Segoe UI Variable Display', Consolas; border: none; background: transparent;"
        )
        self._lbl.setStyleSheet(
            "color: rgb(113,113,122); font-size: 10px; border: none; background: transparent;"
        )

    def set_value(self, v: str):
        self._val.setText(v)


class _MetricCell(QFrame):

    def __init__(self, label: str, value: str):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(1)
        self._lbl = QLabel(label)
        self._val = QLabel(value)
        lay.addWidget(self._lbl)
        lay.addWidget(self._val)
        self._apply_theme()

    def _apply_theme(self):
        is_light = theme.is_light_theme()
        bg = "rgba(0,0,0,10)" if is_light else "rgba(255,255,255,6)"
        border = (
            "1px solid rgba(0,0,0,18)" if is_light else "1px solid rgba(255,255,255,15)"
        )
        txt = "rgb(30,30,42)" if is_light else "rgb(220,240,255)"
        self.setStyleSheet(f"background: {bg}; border: {border}; border-radius: 8px;")
        self._lbl.setStyleSheet(
            "color: rgb(113,113,122); font-size: 9px; border: none; background: transparent;"
        )
        self._val.setStyleSheet(
            f"color: {txt}; font-size: 13px; "
            f"font-family: 'Segoe UI Variable Display', Consolas; border: none; background: transparent;"
        )

    def set_value(self, v: str):
        self._val.setText(v)


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
            "font-size: 9px; font-family: 'Segoe UI Variable Display', Consolas; "
            "padding: 2px 6px; letter-spacing: 1px;"
        )


def _divider() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet(_divider_style())
    return line


def _divider_style() -> str:
    is_light = theme.is_light_theme()
    c = "rgba(0, 0, 0, 18)" if is_light else "rgba(255, 255, 255, 18)"
    return f"color: {c};"


# ------------------------------------------------------------------ style getters


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
        font-family: 'Segoe UI Variable Display', 'Segoe UI';
    }}
    QPushButton:hover {{ background: {hover_bg}; color: {hover_color}; }}
    """


def _btn_accent_style() -> str:
    return """
    QPushButton {
        background: rgba(34,211,238,160);
        color: rgb(10,10,20);
        border: none;
        border-radius: 6px;
        font-size: 11px;
        padding: 0 10px;
        font-family: 'Segoe UI Variable Display', 'Segoe UI';
    }
    QPushButton:hover { background: rgba(34,211,238,210); }
    """


def _tab_style() -> str:
    is_light = theme.is_light_theme()
    color = "rgb(115,115,125)" if is_light else "rgb(113,113,122)"
    selected_color = "rgb(8,145,178)" if is_light else "rgb(34,211,238)"
    hover_color = "rgb(30,30,42)" if is_light else "rgb(200,220,240)"
    return f"""
    QTabWidget::pane {{ border: none; background: transparent; }}
    QTabBar::tab {{
        background: transparent;
        color: {color};
        font-size: 11px;
        font-family: 'Segoe UI Variable Display', 'Segoe UI';
        padding: 6px 16px;
        border: none;
        border-bottom: 2px solid transparent;
    }}
    QTabBar::tab:selected {{
        color: {selected_color};
        border-bottom: 2px solid {selected_color};
    }}
    QTabBar::tab:hover {{ color: {hover_color}; }}
    """


def _table_style() -> str:
    is_light = theme.is_light_theme()
    color = "rgb(30,30,42)" if is_light else "rgb(220,240,255)"
    selected_bg = "rgba(8,145,178,30)" if is_light else "rgba(34,211,238,30)"
    border_color = "rgba(0,0,0,8)" if is_light else "rgba(255,255,255,8)"
    return f"""
    QTableView {{
        background: transparent;
        border: none;
        color: {color};
        font-size: 11px;
        font-family: 'Segoe UI', sans-serif;
        selection-background-color: {selected_bg};
        gridline-color: transparent;
    }}
    QTableView::item {{ padding: 4px 8px; border-bottom: 1px solid {border_color}; }}
    QTableView::item:selected {{ background: {selected_bg}; }}
    """


def _header_style() -> str:
    is_light = theme.is_light_theme()
    bg = "rgba(0,0,0,10)" if is_light else "rgba(255,255,255,6)"
    color = "rgb(115,115,125)" if is_light else "rgb(113,113,122)"
    return f"""
    QHeaderView::section {{
        background: {bg};
        color: {color};
        font-size: 10px;
        font-family: 'Segoe UI Mono', Consolas;
        border: none;
        padding: 4px 8px;
    }}
    """
