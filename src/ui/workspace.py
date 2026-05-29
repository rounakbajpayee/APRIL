"""
TacticalWorkspace — the full diagnostic and orchestration surface.

Design language (Fluent 2 / WinUI 3)
─────────────────────────────────────
• Icon-enhanced tab bar: Tasks, Nodes, Diagnostics, Log.
• Clean metric cells that adapt to light / dark theme.
• Table models no longer hard-code dark-mode text colors.
• Acrylic frosted-glass background.
• Subtle top-edge gloss + Fluent border ring.
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
    QTabWidget,
    QTableView,
    QHeaderView,
    QFrame,
    QScrollArea,
    QAbstractItemView,
    QApplication,
)

from .state import APRILCore, APRILMode, APRILState, Corner
from . import theme

# ── Workspace ────────────────────────────────────────────────────────────────


class TacticalWorkspace(QWidget):
    """Tactical mode — expanded operational workspace."""

    def __init__(self, core: APRILCore, parent: QWidget | None = None) -> None:
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

    def _setup_window(self) -> None:
        self.setFixedSize(theme.WORKSPACE_W, theme.WORKSPACE_H)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(14)

        # ── Title bar ─────────────────────────────────────────────────────
        bar = QHBoxLayout()
        bar.setSpacing(10)

        self._logo_lbl = QLabel()
        self._logo_lbl.setFixedSize(18, 18)
        bar.addWidget(self._logo_lbl)

        self._title = QLabel("APRIL  /  Tactical")
        self._title.setFont(theme.ui_font(13))
        bar.addWidget(self._title)

        bar.addStretch()

        self._state_pill = _StatePill("DORMANT")
        bar.addWidget(self._state_pill)

        self._focus_btn = QPushButton()
        self._focus_btn.setIcon(theme.get_icon("fa6s.chevron_down"))
        self._focus_btn.setToolTip("Collapse to Focus mode")
        self._focus_btn.setFixedSize(28, 28)
        self._focus_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._focus_btn.clicked.connect(self._core.collapse)
        bar.addWidget(self._focus_btn)

        self._close_btn = QPushButton()
        self._close_btn.setIcon(theme.get_icon("fa6s.xmark"))
        self._close_btn.setToolTip("Close")
        self._close_btn.setFixedSize(28, 28)
        self._close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._close_btn.clicked.connect(self._collapse)
        bar.addWidget(self._close_btn)

        root.addLayout(bar)
        self._div_top = _HDivider()
        root.addWidget(self._div_top)

        # ── Tab widget ─────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        for label, icon_name, build_fn in [
            ("Tasks", "fa6s.list_check", self._build_tasks_tab),
            ("Nodes", "fa6s.network_wired", self._build_nodes_tab),
            ("Diagnostics", "fa6s.chart_bar", self._build_diag_tab),
            ("Log", "fa6s.scroll", self._build_log_tab),
        ]:
            tab_widget = build_fn()
            self._tabs.addTab(tab_widget, theme.get_icon(icon_name), label)

        root.addWidget(self._tabs)

        self._apply_theme()

    # ------------------------------------------------------------------ tabs

    def _build_tasks_tab(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 14, 0, 0)
        layout.setSpacing(10)

        # Summary stat cells
        summary = QHBoxLayout()
        summary.setSpacing(10)
        self._task_stat_running = _StatCell("Running", "0", "rgb(56,189,248)")
        self._task_stat_paused = _StatCell("Suspended", "0", "rgb(251,191,36)")
        self._task_stat_done = _StatCell("Complete", "0", "rgb(74,222,128)")
        for cell in [self._task_stat_running, self._task_stat_paused, self._task_stat_done]:
            summary.addWidget(cell)
        layout.addLayout(summary)

        self._task_div = _HDivider()
        layout.addWidget(self._task_div)

        self._task_model = _TaskModel()
        self._task_tv = _DataTable(self._task_model)
        layout.addWidget(self._task_tv)

        act = QHBoxLayout()
        act.addStretch()
        self._task_btns: list[QPushButton] = []
        for label, icon_name in [
            ("Resume", "fa6s.play"),
            ("Cancel", "fa6s.stop"),
            ("Clear Done", "fa6s.trash"),
        ]:
            btn = QPushButton(label)
            btn.setIcon(theme.get_icon(icon_name))
            btn.setFixedHeight(28)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            act.addWidget(btn)
            self._task_btns.append(btn)
        layout.addLayout(act)
        return w

    def _build_nodes_tab(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 14, 0, 0)
        layout.setSpacing(10)

        self._node_model = _NodeModel()
        self._node_model.add("mac (inference)", "online", "Ollama · Qdrant · Oracle")
        self._node_model.add("dell (apps)", "online", "Docker stack · StoragePool")
        self._node_model.add("cortex (gateway)", "online", "LiteLLM v1.82.3")
        self._node_tv = _DataTable(self._node_model)
        layout.addWidget(self._node_tv)

        act = QHBoxLayout()
        act.addStretch()
        self._node_btns: list[QPushButton] = []
        for label, icon_name, accent in [
            ("Ping", "fa6s.satellite_dish", False),
            ("Remove", "fa6s.trash", False),
            ("Add Node…", "fa6s.plus", True),
        ]:
            btn = QPushButton(label)
            btn.setIcon(theme.get_icon(icon_name))
            btn.setFixedHeight(28)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            act.addWidget(btn)
            self._node_btns.append(btn)
        layout.addLayout(act)
        return w

    def _build_diag_tab(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 14, 0, 0)
        layout.setSpacing(12)

        grid = QHBoxLayout()
        grid.setSpacing(10)
        self._cpu_cell = _MetricCell("CPU", "—", "fa6s.microchip")
        self._mem_cell = _MetricCell("Memory", "—", "fa6s.memory")
        self._lat_cell = _MetricCell("Latency", "—", "fa6s.stopwatch")
        self._sess_cell = _MetricCell("Session", "—", "fa6s.clock")
        for cell in [self._cpu_cell, self._mem_cell, self._lat_cell, self._sess_cell]:
            grid.addWidget(cell)
        layout.addLayout(grid)

        self._diag_div = _HDivider()
        layout.addWidget(self._diag_div)

        self._spark_label = QLabel("Response latency (last 60 s)")
        self._spark_label.setFont(theme.mono_font(9))
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
        w.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 14, 0, 0)
        layout.setSpacing(6)

        self._log_area = QLabel()
        self._log_area.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._log_area.setWordWrap(True)
        self._log_entries: list[str] = []
        self._refresh_log()

        scroll = QScrollArea()
        scroll.setWidget(self._log_area)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:vertical { width: 4px; background: transparent; }"
            "QScrollBar::handle:vertical { background: rgba(148,163,184,80); border-radius: 2px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        layout.addWidget(scroll)

        act = QHBoxLayout()
        act.addStretch()
        self._clear_btn = QPushButton("Clear Log")
        self._clear_btn.setIcon(theme.get_icon("fa6s.trash"))
        self._clear_btn.setFixedHeight(28)
        self._clear_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._clear_btn.clicked.connect(self._clear_log)
        act.addWidget(self._clear_btn)
        layout.addLayout(act)
        return w

    # ------------------------------------------------------------------ theme

    def _apply_theme(self) -> None:
        light = theme.is_light_theme()
        title_color = "rgb(8,145,178)" if light else "rgb(56,189,248)"
        muted = "rgb(100,116,139)" if light else "rgb(100,116,139)"
        txt = "rgb(15,23,42)" if light else "rgb(220,230,248)"

        # Logo icon
        ic = theme.get_icon("fa6s.circle_dot", color=title_color)
        self._logo_lbl.setPixmap(ic.pixmap(18, 18))

        # Title
        self._title.setStyleSheet(
            f"color: {title_color}; font-size: 13px; font-weight: 600; "
            f"font-family: 'Segoe UI Variable Display', sans-serif; background: transparent;"
        )

        # Tabs
        self._tabs.setStyleSheet(_tab_css())

        # Icon buttons
        icon_btn_css = _icon_btn_css()
        icon_c = "rgb(71,85,105)" if light else "rgb(148,163,184)"
        self._focus_btn.setStyleSheet(icon_btn_css)
        self._focus_btn.setIcon(theme.get_icon("fa6s.chevron_down", color=icon_c))
        self._close_btn.setStyleSheet(icon_btn_css)
        self._close_btn.setIcon(theme.get_icon("fa6s.xmark", color=icon_c))

        # Dividers
        div_css = _divider_css()
        self._div_top.setStyleSheet(div_css)
        if hasattr(self, "_task_div"):
            self._task_div.setStyleSheet(div_css)
        if hasattr(self, "_diag_div"):
            self._diag_div.setStyleSheet(div_css)

        # Stat / metric cells
        for cell in [self._task_stat_running, self._task_stat_paused, self._task_stat_done]:
            cell.apply_theme()
        for cell in [self._cpu_cell, self._mem_cell, self._lat_cell, self._sess_cell]:
            cell.apply_theme()

        # Tables
        table_css = _table_css()
        header_css = _header_css()
        for tv in [self._task_tv, self._node_tv]:
            tv.setStyleSheet(table_css)
            tv.horizontalHeader().setStyleSheet(header_css)

        # Task buttons
        for btn in self._task_btns:
            btn.setStyleSheet(_ghost_btn_css())
        # Node buttons (last one is accent)
        for i, btn in enumerate(self._node_btns):
            btn.setStyleSheet(
                _accent_btn_css() if i == len(self._node_btns) - 1 else _ghost_btn_css()
            )
        self._clear_btn.setStyleSheet(_ghost_btn_css())

        # State pill
        self._on_state_changed(self._core.state)

        # Sparkline / log
        if hasattr(self, "_spark_label"):
            self._spark_label.setStyleSheet(
                f"color: {muted}; font-size: 9px; font-family: 'Cascadia Code', Consolas; "
                f"background: transparent;"
            )
        self._log_area.setStyleSheet(
            f"color: {txt}; font-family: 'Cascadia Code', Consolas; "
            f"font-size: 10px; line-height: 1.7; background: transparent;"
        )

    # ------------------------------------------------------------------ animation

    def _setup_animation(self) -> None:
        self._opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self._opacity_anim.setDuration(theme.TRANSITION_NORMAL)
        self._opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def expand(self) -> None:
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
        try:
            self._opacity_anim.finished.disconnect(self._on_collapse_done)
        except Exception:
            pass
        if hasattr(self, "_diag_timer"):
            self._diag_timer.stop()
        self._core.set_mode(APRILMode.FOCUS)

    # ------------------------------------------------------------------ positioning

    def _reposition(self, corner: Corner) -> None:
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

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 20, 20)

        p.setClipPath(path)
        p.fillRect(0, 0, self.width(), self.height(), theme.BG_BASE)

        grad = QLinearGradient(0, 0, 0, 80)
        grad.setColorAt(0, QColor(255, 255, 255, 18 if not theme.is_light_theme() else 35))
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

    def _refresh_diag(self) -> None:
        import random

        self._cpu_cell.set_value(f"{random.randint(5, 40)} %")
        self._mem_cell.set_value(f"{random.uniform(0.8, 2.0):.1f} GB")
        self._lat_cell.set_value(f"{random.randint(80, 400)} ms")
        elapsed = int(time.monotonic()) % 3600
        self._sess_cell.set_value(f"{elapsed // 60}m {elapsed % 60}s")
        self._sparkline.push(random.randint(80, 400))

    def _refresh_log(self) -> None:
        self._log_area.setText("\n".join(self._log_entries))

    def _clear_log(self) -> None:
        self._log_entries.clear()
        self._refresh_log()

    def append_log(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_entries.append(f"[{ts}]  {msg}")
        if len(self._log_entries) > 200:
            self._log_entries = self._log_entries[-200:]
        self._refresh_log()

    # ------------------------------------------------------------------ slots

    def _on_mode_changed(self, mode: APRILMode) -> None:
        if mode == APRILMode.TACTICAL:
            self.expand()
        elif self.isVisible():
            self._collapse()

    def _on_state_changed(self, state: APRILState) -> None:
        colors = {
            APRILState.DORMANT: ("rgb(100,116,139)", "rgb(148,163,184)"),
            APRILState.LISTENING: ("rgb(8,145,178)", "rgb(56,189,248)"),
            APRILState.THINKING: ("rgb(8,145,178)", "rgb(56,189,248)"),
            APRILState.SPEAKING: ("rgb(8,145,178)", "rgb(56,189,248)"),
            APRILState.ACTING: ("rgb(124,58,237)", "rgb(167,139,250)"),
            APRILState.WARNING: ("rgb(180,130,10)", "rgb(251,191,36)"),
            APRILState.ERROR: ("rgb(185,28,28)", "rgb(248,113,113)"),
        }
        lc, dc = colors.get(state, ("rgb(100,116,139)", "rgb(148,163,184)"))
        c = lc if theme.is_light_theme() else dc
        self._state_pill.update_state(state.name, c)
        self._state_pill.setStyleSheet(
            f"color: {c}; background: transparent; "
            f"border: 1px solid {c}30; border-radius: 5px; "
            f"font-size: 9px; font-family: 'Cascadia Code', Consolas; "
            f"padding: 2px 8px; letter-spacing: 0.8px;"
        )


# ── Table models ─────────────────────────────────────────────────────────────


class _TaskModel(QAbstractTableModel):
    _HEADERS = ["Task", "Status", "Elapsed"]

    def __init__(self) -> None:
        super().__init__()
        self._data: list[list[str]] = []

    def add(self, name: str, status: str, elapsed: str) -> None:
        self._data.append([name, status, elapsed])
        self.layoutChanged.emit()

    def rowCount(self, _=QModelIndex()) -> int:
        return len(self._data)

    def columnCount(self, _=QModelIndex()) -> int:
        return 3

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self._HEADERS[section]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self._data[index.row()][index.column()]
        if role == Qt.ItemDataRole.ForegroundRole:
            light = theme.is_light_theme()
            if index.column() == 1:
                status = self._data[index.row()][1]
                status_colors = {
                    "running": QColor(8, 145, 178) if light else QColor(56, 189, 248),
                    "suspended": QColor(180, 130, 10) if light else QColor(251, 191, 36),
                    "background": QColor(100, 116, 139),
                }
                return QBrush(status_colors.get(status, QColor(100, 116, 139)))
            return QBrush(QColor(15, 23, 42) if light else QColor(220, 230, 248))
        return None


class _NodeModel(QAbstractTableModel):
    _HEADERS = ["Node", "Status", "Services"]

    def __init__(self) -> None:
        super().__init__()
        self._data: list[list[str]] = []

    def add(self, name: str, status: str, info: str) -> None:
        self._data.append([name, status, info])
        self.layoutChanged.emit()

    def rowCount(self, _=QModelIndex()) -> int:
        return len(self._data)

    def columnCount(self, _=QModelIndex()) -> int:
        return 3

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self._HEADERS[section]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self._data[index.row()][index.column()]
        if role == Qt.ItemDataRole.ForegroundRole:
            light = theme.is_light_theme()
            if index.column() == 1:
                status = self._data[index.row()][1]
                c = (
                    QColor(8, 145, 178)
                    if (status == "online" and light)
                    else QColor(56, 189, 248) if status == "online" else QColor(239, 68, 68)
                )
                return QBrush(c)
            return QBrush(QColor(15, 23, 42) if light else QColor(220, 230, 248))
        return None


# ── Small widgets ─────────────────────────────────────────────────────────────


class _DataTable(QTableView):
    def __init__(self, model: QAbstractTableModel) -> None:
        super().__init__()
        self.setModel(model)
        self.setStyleSheet(_table_css())
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setStyleSheet(_header_css())
        self.verticalHeader().hide()
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(False)
        self.setAlternatingRowColors(False)


class _StatCell(QFrame):
    def __init__(self, label: str, value: str, color: str) -> None:
        super().__init__()
        self._color = color
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(3)
        self._val = QLabel(value)
        self._val.setFont(theme.ui_font(22))
        self._lbl = QLabel(label)
        self._lbl.setFont(theme.label_font(9))
        lay.addWidget(self._val)
        lay.addWidget(self._lbl)
        self.apply_theme()

    def apply_theme(self) -> None:
        light = theme.is_light_theme()
        bg = "rgba(0,0,0,6)" if light else "rgba(255,255,255,6)"
        border = "rgba(0,0,0,14)" if light else "rgba(255,255,255,12)"
        muted = "rgb(148,163,184)" if light else "rgb(100,116,139)"
        self.setStyleSheet(
            f"QFrame {{ background: {bg}; border: 1px solid {border}; border-radius: 10px; }}"
        )
        self._val.setStyleSheet(f"color: {self._color}; background: transparent; border: none;")
        self._lbl.setStyleSheet(
            f"color: {muted}; font-size: 9px; letter-spacing: 1px; "
            f"background: transparent; border: none; text-transform: uppercase;"
        )

    def set_value(self, v: str) -> None:
        self._val.setText(v)


class _MetricCell(QFrame):
    def __init__(self, label: str, value: str, icon_name: str = "") -> None:
        super().__init__()
        self._icon_name = icon_name
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(4)

        icon_row = QHBoxLayout()
        icon_row.setSpacing(5)
        self._icon_lbl = QLabel()
        self._icon_lbl.setFixedSize(12, 12)
        icon_row.addWidget(self._icon_lbl)
        self._lbl = QLabel(label)
        self._lbl.setFont(theme.label_font(8))
        icon_row.addWidget(self._lbl)
        icon_row.addStretch()
        lay.addLayout(icon_row)

        self._val = QLabel(value)
        self._val.setFont(theme.mono_font(13))
        lay.addWidget(self._val)

        self.apply_theme()

    def apply_theme(self) -> None:
        light = theme.is_light_theme()
        bg = "rgba(0,0,0,6)" if light else "rgba(255,255,255,6)"
        border = "rgba(0,0,0,14)" if light else "rgba(255,255,255,12)"
        txt = "rgb(15,23,42)" if light else "rgb(220,230,248)"
        muted = "rgb(148,163,184)" if light else "rgb(100,116,139)"
        self.setStyleSheet(
            f"QFrame {{ background: {bg}; border: 1px solid {border}; border-radius: 10px; }}"
        )
        self._val.setStyleSheet(f"color: {txt}; background: transparent; border: none;")
        self._lbl.setStyleSheet(
            f"color: {muted}; font-size: 8px; letter-spacing: 1.2px; "
            f"background: transparent; border: none;"
        )
        if self._icon_name:
            ic = theme.get_icon(self._icon_name, color=muted)
            self._icon_lbl.setPixmap(ic.pixmap(12, 12))

    def set_value(self, v: str) -> None:
        self._val.setText(v)


class _Sparkline(QWidget):
    MAX = 60

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(54)
        self._data: list[int] = []

    def push(self, v: int) -> None:
        self._data.append(v)
        if len(self._data) > self.MAX:
            self._data.pop(0)
        self.update()

    def paintEvent(self, _) -> None:  # noqa: N802
        if len(self._data) < 2:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        mn, mx = min(self._data), max(self._data)
        rng = mx - mn or 1
        pts = [
            (i * w / (self.MAX - 1), h - (v - mn) / rng * (h - 6) - 3)
            for i, v in enumerate(self._data)
        ]

        path = QPainterPath()
        path.moveTo(pts[0][0], pts[0][1])
        for x, y in pts[1:]:
            path.lineTo(x, y)

        light = theme.is_light_theme()
        line_color = QColor(8, 145, 178, 200) if light else QColor(56, 189, 248, 200)
        pen = QPen(line_color)
        pen.setWidthF(1.6)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.end()


class _StatePill(QLabel):
    def __init__(self, text: str) -> None:
        super().__init__(text)

    def update_state(self, text: str, color: str) -> None:
        self.setText(text)


class _HDivider(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFixedHeight(1)
        self.setStyleSheet(_divider_css())


# ── Style functions ───────────────────────────────────────────────────────────


def _divider_css() -> str:
    c = "rgba(0,0,0,16)" if theme.is_light_theme() else "rgba(255,255,255,14)"
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


def _ghost_btn_css() -> str:
    light = theme.is_light_theme()
    bg = "rgba(0,0,0,6)" if light else "rgba(255,255,255,7)"
    border = "rgba(0,0,0,16)" if light else "rgba(255,255,255,14)"
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


def _accent_btn_css() -> str:
    light = theme.is_light_theme()
    bg = "rgba(8,145,178,190)" if light else "rgba(56,189,248,175)"
    hover = "rgba(8,145,178,230)" if light else "rgba(56,189,248,215)"
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


def _tab_css() -> str:
    light = theme.is_light_theme()
    color = "rgb(100,116,139)"
    sel = "rgb(8,145,178)" if light else "rgb(56,189,248)"
    hover = "rgb(15,23,42)" if light else "rgb(220,230,248)"
    return f"""
QTabWidget::pane {{ border: none; background: transparent; }}
QTabBar::tab {{
    background: transparent;
    color: {color};
    font-size: 11px;
    font-family: 'Segoe UI Variable Display', 'Segoe UI';
    padding: 8px 18px;
    border: none;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{
    color: {sel};
    border-bottom: 2px solid {sel};
}}
QTabBar::tab:hover {{ color: {hover}; }}
"""


def _table_css() -> str:
    light = theme.is_light_theme()
    color = "rgb(15,23,42)" if light else "rgb(220,230,248)"
    sel_bg = "rgba(8,145,178,20)" if light else "rgba(56,189,248,18)"
    row_border = "rgba(0,0,0,8)" if light else "rgba(255,255,255,8)"
    return f"""
QTableView {{
    background: transparent;
    border: none;
    color: {color};
    font-size: 11px;
    font-family: 'Segoe UI Variable Display', 'Segoe UI';
    selection-background-color: {sel_bg};
    gridline-color: transparent;
}}
QTableView::item {{
    padding: 6px 10px;
    border-bottom: 1px solid {row_border};
}}
QTableView::item:selected {{ background: {sel_bg}; }}
"""


def _header_css() -> str:
    light = theme.is_light_theme()
    bg = "rgba(0,0,0,5)" if light else "rgba(255,255,255,5)"
    color = "rgb(100,116,139)"
    return f"""
QHeaderView::section {{
    background: {bg};
    color: {color};
    font-size: 9px;
    font-family: 'Segoe UI Variable Display', sans-serif;
    letter-spacing: 1px;
    border: none;
    padding: 6px 10px;
    text-transform: uppercase;
}}
"""
