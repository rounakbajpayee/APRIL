"""
ui/workspace.py — Tactical / Expanded View

Design language (Windows 11 Premium Mica):
- Translucent dark/light Mica base.
- Tab bar with Windows Accent blue underline indicators.
- Dictation history relocated to the "Dictation" tab, supporting hover-expansion.
- Borderless scrollable QTextEdit for history cards.
- Integrated bottom-right capsule toolbars for copy/edit actions.
- Inline Tab Configuration page to pin/unpin and reorder tabs.
"""

from __future__ import annotations

import math
import time
import random
from datetime import datetime

from PyQt6.QtCore import (
    Qt,
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
    QAbstractTableModel,
    QModelIndex,
    pyqtSignal,
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
    QStackedWidget,
    QCheckBox,
    QTextEdit,
)

from .state import APRILCore, APRILMode, APRILState, Corner
from . import theme

# ── History Card Widget for Dictation Tab ────────────────────────────────────

class _HistoryCard(QFrame):
    """
    A single dictation entry card.
    
    - Displays as a compact single-line row by default.
    - On mouse hover: expands vertically to occupy the scroll area, enables
      wrapping/scrollbars, and reveals a bottom-right action capsule.
    - Uses a borderless QTextEdit to support scrollable multiline editing.
    """
    hovered = pyqtSignal(object)  # Emits self when hovered
    unhovered = pyqtSignal(object)  # Emits self when hover leaves

    def __init__(
        self,
        text: str,
        index: int,
        on_copy,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._index = index
        self._on_copy = on_copy
        self._hovered = False
        self._is_editing = False
        self.setMouseTracking(True)

        self.setObjectName("HistoryCard")
        self.setFixedHeight(38)

        # Main Layout
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(12, 6, 12, 6)
        self._layout.setSpacing(4)

        # Top row: Status dot + Text edit area
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)

        # Recency dot
        self._dot = QLabel("●")
        self._dot.setFixedWidth(8)
        self._dot.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        top_row.addWidget(self._dot)

        # Multiline text edit (borderless)
        self._text_edit = QTextEdit(text)
        self._text_edit.setFrameShape(QFrame.Shape.NoFrame)
        self._text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._text_edit.setReadOnly(True)
        self._text_edit.setFont(theme.ui_font(11))
        # Style QScrollBar programmatically or hide
        self._text_edit.document().documentLayout().documentSizeChanged.connect(self._adjust_scroll)
        top_row.addWidget(self._text_edit, 1)

        self._layout.addLayout(top_row)

        # Bottom row: Stretch + Action capsule (hidden until hover)
        self._action_row = QHBoxLayout()
        self._action_row.setContentsMargins(0, 0, 0, 0)
        self._action_row.addStretch()

        # Capsule toolbar frame
        self._capsule = QFrame()
        self._capsule.setObjectName("ActionCapsule")
        capsule_lay = QHBoxLayout(self._capsule)
        capsule_lay.setContentsMargins(6, 4, 6, 4)
        capsule_lay.setSpacing(6)

        # Pencil Edit Button
        self._edit_btn = QPushButton()
        self._edit_btn.setToolTip("Edit text")
        self._edit_btn.setFixedSize(22, 22)
        self._edit_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._edit_btn.clicked.connect(self._toggle_edit)

        # Copy Button
        self._copy_btn = QPushButton()
        self._copy_btn.setToolTip("Copy to clipboard")
        self._copy_btn.setFixedSize(22, 22)
        self._copy_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._copy_btn.clicked.connect(lambda: self._on_copy(self._text_edit.toPlainText()))

        capsule_lay.addWidget(self._edit_btn)
        capsule_lay.addWidget(self._copy_btn)

        self._action_row.addWidget(self._capsule)
        self._layout.addLayout(self._action_row)

        self._capsule.setVisible(False)
        self.apply_theme()

    def _adjust_scroll(self) -> None:
        pass

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        self.hovered.emit(self)
        self.apply_theme()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        # If active editing focus is inside the QTextEdit, don't collapse immediately on leave
        if self._is_editing:
            return
        self._hovered = False
        self.unhovered.emit(self)
        self.apply_theme()
        super().leaveEvent(event)

    def _toggle_edit(self) -> None:
        self._is_editing = not self._is_editing
        self._text_edit.setReadOnly(not self._is_editing)
        if self._is_editing:
            self._text_edit.setFocus()
            self._edit_btn.setToolTip("Save text")
        else:
            self._edit_btn.setToolTip("Edit text")
            # Unfocus
            self._text_edit.clearFocus()
            self.apply_theme()

    def set_expanded(self, expanded: bool) -> None:
        if expanded:
            self.setFixedHeight(160)
            self._text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self._capsule.setVisible(True)
        else:
            self._is_editing = False
            self._text_edit.setReadOnly(True)
            self._edit_btn.setToolTip("Edit text")
            self.setFixedHeight(38)
            self._text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._capsule.setVisible(False)
            self._hovered = False
            self.apply_theme()

    def get_text(self) -> str:
        return self._text_edit.toPlainText()

    def apply_theme(self) -> None:
        light = theme.is_light_theme()
        
        # Dot Color
        if self._index == 0:
            dot_color = "rgb(0, 120, 212)" if light else "rgb(0, 120, 212)" # Accent Blue
        elif self._index < 3:
            dot_color = "rgb(113, 113, 122)" # Zinc 500
        else:
            dot_color = "rgb(63, 63, 70)" # Zinc 700

        self._dot.setStyleSheet(
            f"color: {dot_color}; font-size: 8px; background: transparent; border: none;"
        )

        # QTextEdit Colors
        text_color = "rgb(24, 24, 27)" if light else "rgb(243, 243, 243)"
        
        # Card Background
        if self._hovered or self._is_editing:
            bg = "rgba(0, 0, 0, 10)" if light else "rgba(255, 255, 255, 12)"
            border_c = "rgba(0, 0, 0, 20)" if light else "rgba(255, 255, 255, 18)"
        else:
            bg = "transparent"
            border_c = "transparent"

        self.setStyleSheet(f"""
            QFrame#HistoryCard {{
                background: {bg};
                border: 1px solid {border_c};
                border-radius: 8px;
            }}
        """)

        self._text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                border: none;
                color: {text_color};
                font-size: 11px;
                font-family: 'Segoe UI Variable Display', 'Segoe UI';
            }}
        """)

        # Capsule Toolbar Style
        capsule_bg = "rgba(240, 240, 240, 220)" if light else "rgba(53, 53, 53, 200)"
        capsule_border = "rgba(0, 0, 0, 20)" if light else "rgba(255, 255, 255, 12)"
        self._capsule.setStyleSheet(f"""
            QFrame#ActionCapsule {{
                background: {capsule_bg};
                border: 1px solid {capsule_border};
                border-radius: 12px;
            }}
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background: rgba(0, 0, 0, 15) if {light} else rgba(255, 255, 255, 15);
            }}
        """)

        # Buttons Icons
        icon_color = "rgb(82, 82, 91)" if light else "rgb(161, 161, 170)"
        pencil_icon = "fa6s.pen" if not self._is_editing else "fa6s.check"
        self._edit_btn.setIcon(theme.get_icon(pencil_icon, color=icon_color))
        self._copy_btn.setIcon(theme.get_icon("fa6s.copy", color=icon_color))

class TacticalWorkspace(QWidget):
    """Expanded View — full diagnostics, orchestration, and dictation history."""

    def __init__(self, core: APRILCore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._core = core
        self._history_cards: list[_HistoryCard] = []
        self._pinned_tabs = ["Tasks", "Nodes", "Diagnostics", "Dictation", "Log"]

        self._setup_window()
        self._build_ui()
        self._setup_animation()

        core.mode_changed.connect(self._on_mode_changed)
        core.state_changed.connect(self._on_state_changed)
        core.corner_changed.connect(self._reposition)

        self.hide()

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

    def _build_ui(self) -> None:
        # Main stacked container to toggle configuration view
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(12, 12, 12, 12)
        self._main_layout.setSpacing(0)

        # Styled base frame to support Mica background painting and drop shadow
        self._base_frame = QFrame()
        self._base_frame.setObjectName("WorkspaceBase")
        
        # Apply premium drop shadow
        shadow = theme.create_shadow(QColor(0, 0, 0, 85), radius=20, dy=6)
        if shadow:
            self._base_frame.setGraphicsEffect(shadow)

        self._base_layout = QVBoxLayout(self._base_frame)
        self._base_layout.setContentsMargins(18, 18, 18, 18)
        self._base_layout.setSpacing(12)

        self._main_layout.addWidget(self._base_frame)

        # ── Title / Header Bar ───────────────────────────────────────────────
        header = QHBoxLayout()
        header.setSpacing(10)

        self._logo_lbl = QLabel()
        self._logo_lbl.setFixedSize(18, 18)
        header.addWidget(self._logo_lbl)

        # Plain "APRIL" name header (no slash/tag)
        self._title = QLabel("APRIL")
        self._title.setFont(theme.ui_font(13))
        header.addWidget(self._title)

        header.addStretch()

        self._state_pill = _StatePill("DORMANT")
        header.addWidget(self._state_pill)

        # Single Header Toggle Button (switch Expanded <-> Compact)
        self._toggle_btn = QPushButton()
        self._toggle_btn.setToolTip("Toggle Compact view")
        self._toggle_btn.setFixedSize(28, 28)
        self._toggle_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._toggle_btn.clicked.connect(self._core.collapse)
        header.addWidget(self._toggle_btn)

        # Close button (closes back to Status Dot)
        self._close_btn = QPushButton()
        self._close_btn.setToolTip("Close menu")
        self._close_btn.setFixedSize(28, 28)
        self._close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._close_btn.clicked.connect(self._collapse)
        header.addWidget(self._close_btn)

        self._base_layout.addLayout(header)

        self._div_top = _HDivider()
        self._base_layout.addWidget(self._div_top)

        # ── Stack for Workspace Views / Tab Config Pane ───────────────────────────
        self._stack = QStackedWidget()
        self._base_layout.addWidget(self._stack, 1)

        # ── Custom Sidebar Navigation Page (Index 0) ─────────────────────────
        self._workspace_container = QWidget()
        self._workspace_container.setStyleSheet("background: transparent;")
        workspace_lay = QHBoxLayout(self._workspace_container)
        workspace_lay.setContentsMargins(0, 0, 0, 0)
        workspace_lay.setSpacing(18)

        # Left Sidebar Panel
        self._sidebar = QWidget()
        self._sidebar.setFixedWidth(160)
        self._sidebar.setStyleSheet("background: transparent;")
        self._sidebar_layout = QVBoxLayout(self._sidebar)
        self._sidebar_layout.setContentsMargins(0, 0, 8, 0)
        self._sidebar_layout.setSpacing(6)

        # Gear configuration button (placed at the bottom of the sidebar)
        self._gear_btn = QPushButton()
        self._gear_btn.setToolTip("Configure tabs")
        self._gear_btn.setFixedSize(26, 26)
        self._gear_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._gear_btn.clicked.connect(self._open_config_pane)

        # Add vertical buttons container inside sidebar
        self._sidebar_btn_layout = QVBoxLayout()
        self._sidebar_btn_layout.setContentsMargins(0, 0, 0, 0)
        self._sidebar_btn_layout.setSpacing(4)
        self._sidebar_layout.addLayout(self._sidebar_btn_layout)
        
        self._sidebar_layout.addStretch()
        
        # Bottom row in sidebar for the gear settings button
        gear_row = QHBoxLayout()
        gear_row.setContentsMargins(4, 0, 4, 4)
        gear_row.addWidget(self._gear_btn)
        gear_row.addStretch()
        self._sidebar_layout.addLayout(gear_row)

        workspace_lay.addWidget(self._sidebar)

        # Right Pages Stack
        self._pages_stack = QStackedWidget()
        self._pages_stack.setStyleSheet("background: transparent;")
        workspace_lay.addWidget(self._pages_stack, 1)

        self._stack.addWidget(self._workspace_container)

        # Build all page instances
        self._pages_cache = {
            "Tasks": self._build_tasks_tab(),
            "Nodes": self._build_nodes_tab(),
            "Diagnostics": self._build_diag_tab(),
            "Dictation": self._build_dictation_tab(),
            "Log": self._build_log_tab(),
        }

        self._tab_icons = {
            "Tasks": "fa6s.list-check",
            "Nodes": "fa6s.network-wired",
            "Diagnostics": "fa6s.chart-bar",
            "Dictation": "fa6s.microphone",
            "Log": "fa6s.scroll",
        }

        # Tab Config Panel (Index 1)
        self._config_pane = QWidget()
        self._build_config_pane()
        self._stack.addWidget(self._config_pane)

        # Populates sidebar buttons according to self._pinned_tabs
        self._refresh_tab_widget()
        self._apply_theme()

    def _refresh_tab_widget(self) -> None:
        # Clear sidebar buttons
        while self._sidebar_btn_layout.count() > 0:
            item = self._sidebar_btn_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        # Clear pages stack
        while self._pages_stack.count() > 0:
            w = self._pages_stack.widget(0)
            self._pages_stack.removeWidget(w)

        self._sidebar_buttons = {}
        for tab_name in self._pinned_tabs:
            if tab_name in self._pages_cache:
                page = self._pages_cache[tab_name]
                self._pages_stack.addWidget(page)

                btn = QPushButton(f"  {tab_name}")
                btn.setCheckable(True)
                btn.setFixedHeight(34)
                btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                
                # Dynamic style mapping
                btn.setStyleSheet(_sidebar_btn_css())
                
                # Wire tab switching
                btn.clicked.connect(lambda checked, name=tab_name: self._switch_tab(name))
                
                self._sidebar_btn_layout.addWidget(btn)
                self._sidebar_buttons[tab_name] = btn

        # Select first tab by default
        if self._pinned_tabs:
            self._switch_tab(self._pinned_tabs[0])

    def _switch_tab(self, name: str) -> None:
        if name not in self._sidebar_buttons:
            return
            
        is_light = theme.is_light_theme()
        normal_c = "rgb(82, 82, 91)" if is_light else "rgb(161, 161, 170)"
        active_c = "rgb(0, 120, 212)" if is_light else "rgb(96, 205, 255)"

        for tab_name, btn in self._sidebar_buttons.items():
            is_active = (tab_name == name)
            btn.setChecked(is_active)
            btn.setIcon(theme.get_icon(self._tab_icons[tab_name], color=active_c if is_active else normal_c))

        page = self._pages_cache[name]
        self._pages_stack.setCurrentWidget(page)

    # ── Tabs Builders ────────────────────────────────────────────────────────

    def _build_tasks_tab(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(10)

        summary = QHBoxLayout()
        summary.setSpacing(10)
        self._task_stat_running = _StatCell("Running", "0", "rgb(0, 120, 212)")
        self._task_stat_paused = _StatCell("Suspended", "0", "rgb(245, 158, 11)")
        self._task_stat_done = _StatCell("Complete", "0", "rgb(34, 197, 94)")
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
        layout.setContentsMargins(0, 4, 0, 0)
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
            ("Ping", "fa6s.satellite-dish", False),
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
        layout.setContentsMargins(0, 4, 0, 0)
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

    def _build_dictation_tab(self) -> QWidget:
        """Creates the Dictation Tab containing history cards."""
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(10)

        # Scroll area for dictations
        self._dictation_scroll = QScrollArea()
        self._dictation_scroll.setWidgetResizable(True)
        self._dictation_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:vertical { width: 4px; background: transparent; }"
            "QScrollBar::handle:vertical { background: rgba(161,161,170,80); border-radius: 2px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

        self._dictation_container = QWidget()
        self._dictation_container.setStyleSheet("background: transparent;")
        self._dictation_layout = QVBoxLayout(self._dictation_container)
        self._dictation_layout.setContentsMargins(0, 0, 0, 0)
        self._dictation_layout.setSpacing(4)
        self._dictation_layout.addStretch()

        self._dictation_scroll.setWidget(self._dictation_container)
        layout.addWidget(self._dictation_scroll)
        return w

    def _build_log_tab(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 4, 0, 0)
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
            "QScrollBar::handle:vertical { background: rgba(161,161,170,80); border-radius: 2px; }"
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

    # ── Tab Customization Configuration Pane ─────────────────────────────────

    def _build_config_pane(self) -> None:
        """Build layout for reordering/pinning tabs."""
        layout = QVBoxLayout(self._config_pane)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        title = QLabel("CONFIGURE WORKSPACE TABS")
        title.setFont(theme.label_font(9))
        layout.addWidget(title)

        # Scroll list of tabs configurations
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        self._config_container = QWidget()
        self._config_container.setStyleSheet("background: transparent;")
        self._config_layout = QVBoxLayout(self._config_container)
        self._config_layout.setContentsMargins(0, 0, 0, 0)
        self._config_layout.setSpacing(6)
        
        scroll.setWidget(self._config_container)
        layout.addWidget(scroll, 1)

        # Action Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFont(theme.ui_font(11))
        cancel_btn.setFixedHeight(30)
        cancel_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        cancel_btn.setStyleSheet(_ghost_btn_css())
        cancel_btn.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        
        save_btn = QPushButton("Save Settings")
        save_btn.setFont(theme.ui_font(11))
        save_btn.setFixedHeight(30)
        save_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        save_btn.setStyleSheet(_accent_btn_css())
        save_btn.clicked.connect(self._save_config)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _open_config_pane(self) -> None:
        """Prepares and opens the config tab settings page."""
        # Clear previous rows
        while self._config_layout.count() > 0:
            item = self._config_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._config_checkboxes = {}
        all_possible = ["Tasks", "Nodes", "Diagnostics", "Dictation", "Log"]
        order = [t for t in self._pinned_tabs] + [t for t in all_possible if t not in self._pinned_tabs]

        for idx, tab_name in enumerate(order):
            row = QFrame()
            row.setObjectName("ConfigRow")
            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(10, 6, 10, 6)
            row_lay.setSpacing(10)

            drag = QLabel("⋮⋮")
            drag.setFont(theme.ui_font(12))
            drag.setStyleSheet("color: rgb(113, 113, 122); background: transparent;")
            row_lay.addWidget(drag)

            cb = QCheckBox(tab_name)
            cb.setFont(theme.ui_font(11))
            cb.setChecked(tab_name in self._pinned_tabs)
            row_lay.addWidget(cb, 1)
            self._config_checkboxes[tab_name] = cb

            up_btn = QPushButton()
            up_btn.setIcon(theme.get_icon("fa6s.chevron-up"))
            up_btn.setFixedSize(24, 24)
            up_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            up_btn.setStyleSheet(_config_btn_css())
            up_btn.clicked.connect(lambda _, name=tab_name: self._move_tab_config(name, -1))

            down_btn = QPushButton()
            down_btn.setIcon(theme.get_icon("fa6s.chevron-down"))
            down_btn.setFixedSize(24, 24)
            down_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            down_btn.setStyleSheet(_config_btn_css())
            down_btn.clicked.connect(lambda _, name=tab_name: self._move_tab_config(name, 1))

            row_lay.addWidget(up_btn)
            row_lay.addWidget(down_btn)

            row.setStyleSheet(f"""
                QFrame#ConfigRow {{
                    background: rgba(255, 255, 255, 6) if {not theme.is_light_theme()} else rgba(0, 0, 0, 5);
                    border: 1px solid rgba(255,255,255,8) if {not theme.is_light_theme()} else rgba(0,0,0,8);
                    border-radius: 6px;
                }}
            """)
            self._config_layout.addWidget(row)

        self._stack.setCurrentIndex(1)

    def _move_tab_config(self, tab_name: str, direction: int) -> None:
        """Moves tabs list up/down dynamically in the customization order."""
        rows = []
        for i in range(self._config_layout.count()):
            w = self._config_layout.itemAt(i).widget()
            if w:
                rows.append(w)
        
        names = [w.findChild(QCheckBox).text() for w in rows]
        idx = names.index(tab_name)
        new_idx = idx + direction
        if 0 <= new_idx < len(names):
            names[idx], names[new_idx] = names[new_idx], names[idx]
            self._rebuild_config_rows(names)

    def _rebuild_config_rows(self, ordered_names: list[str]) -> None:
        checkboxes_states = {k: cb.isChecked() for k, cb in self._config_checkboxes.items()}
        
        while self._config_layout.count() > 0:
            item = self._config_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        self._config_checkboxes.clear()
        
        for name in ordered_names:
            row = QFrame()
            row.setObjectName("ConfigRow")
            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(10, 6, 10, 6)
            row_lay.setSpacing(10)

            drag = QLabel("⋮⋮")
            drag.setFont(theme.ui_font(12))
            drag.setStyleSheet("color: rgb(113, 113, 122); background: transparent;")
            row_lay.addWidget(drag)

            cb = QCheckBox(name)
            cb.setFont(theme.ui_font(11))
            cb.setChecked(checkboxes_states.get(name, True))
            row_lay.addWidget(cb, 1)
            self._config_checkboxes[name] = cb

            up_btn = QPushButton()
            up_btn.setIcon(theme.get_icon("fa6s.chevron-up"))
            up_btn.setFixedSize(24, 24)
            up_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            up_btn.setStyleSheet(_config_btn_css())
            up_btn.clicked.connect(lambda _, name=name: self._move_tab_config(name, -1))

            down_btn = QPushButton()
            down_btn.setIcon(theme.get_icon("fa6s.chevron-down"))
            down_btn.setFixedSize(24, 24)
            down_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            down_btn.setStyleSheet(_config_btn_css())
            down_btn.clicked.connect(lambda _, name=name: self._move_tab_config(name, 1))

            row_lay.addWidget(up_btn)
            row_lay.addWidget(down_btn)

            row.setStyleSheet(f"""
                QFrame#ConfigRow {{
                    background: rgba(255, 255, 255, 6) if {not theme.is_light_theme()} else rgba(0, 0, 0, 5);
                    border: 1px solid rgba(255,255,255,8) if {not theme.is_light_theme()} else rgba(0,0,0,8);
                    border-radius: 6px;
                }}
            """)
            self._config_layout.addWidget(row)

    def _save_config(self) -> None:
        """Saves dynamic tab order & visible items, updates workspace UI."""
        ordered = []
        for i in range(self._config_layout.count()):
            w = self._config_layout.itemAt(i).widget()
            if w:
                ordered.append(w.findChild(QCheckBox).text())
                
        self._pinned_tabs = [name for name in ordered if self._config_checkboxes[name].isChecked()]
        self._refresh_tab_widget()
        self._stack.setCurrentIndex(0)

    # ── History/Dictations Loading ───────────────────────────────────────────

    def _load_snapshot_history(self) -> None:
        while self._dictation_layout.count() > 1:
            item = self._dictation_layout.takeAt(0)
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
            print(f"[Workspace] Failed to load history: {exc}")

    def _add_history_card(self, text: str) -> None:
        if not text or not text.strip():
            return

        for card in self._history_cards:
            if card.get_text() == text:
                return

        for card in self._history_cards:
            card._index += 1
            card.apply_theme()

        card = _HistoryCard(
            text,
            index=0,
            on_copy=self._copy_text,
            parent=self._dictation_container,
        )
        card.hovered.connect(self._on_card_hovered)
        card.unhovered.connect(self._on_card_unhovered)

        self._dictation_layout.insertWidget(0, card)
        self._history_cards.insert(0, card)

        if len(self._history_cards) > 10:
            oldest = self._history_cards.pop()
            self._dictation_layout.removeWidget(oldest)
            oldest.deleteLater()

    def add_transcript(self, text: str) -> None:
        """Public API (safe to call via bridge) to dynamically push new dictations."""
        if text and text.strip() and text != "—" and not text.endswith("…"):
            self._add_history_card(text)

    def _on_card_hovered(self, hovered_card: _HistoryCard) -> None:
        for card in self._history_cards:
            if card is not hovered_card:
                card.setVisible(False)
        hovered_card.set_expanded(True)

    def _on_card_unhovered(self, hovered_card: _HistoryCard) -> None:
        for card in self._history_cards:
            card.setVisible(True)
            card.set_expanded(False)

    def _copy_text(self, text: str) -> None:
        if text:
            QApplication.clipboard().setText(text)
            self._core.notification_passive.emit("Copied", "Text copied to clipboard.")

    # ── Theme Application ────────────────────────────────────────────────────

    def _apply_theme(self) -> None:
        light = theme.is_light_theme()
        accent_color = "rgb(0, 120, 212)"
        muted = "rgb(113, 113, 122)"
        txt = "rgb(24, 24, 27)" if light else "rgb(243, 243, 243)"

        # Logo icon
        ic = theme.get_icon("fa6s.circle-dot", color=accent_color)
        self._logo_lbl.setPixmap(ic.pixmap(18, 18))

        # Title
        self._title.setStyleSheet(
            f"color: {accent_color}; font-size: 13px; font-weight: 600; "
            f"font-family: 'Segoe UI Variable Display', sans-serif; background: transparent;"
        )

        # Tab Corner Gear Button
        icon_c = "rgb(82, 82, 91)" if light else "rgb(161, 161, 170)"
        self._gear_btn.setStyleSheet(_icon_btn_css())
        self._gear_btn.setIcon(theme.get_icon("fa6s.gear", color=icon_c))

        # Sidebar navigation buttons refresh
        for tab_name, btn in self._sidebar_buttons.items():
            btn.setStyleSheet(_sidebar_btn_css())
            is_active = btn.isChecked()
            btn.setIcon(theme.get_icon(self._tab_icons[tab_name], color=accent_color if is_active else icon_c))

        # Header Icon buttons (toggle and close)
        icon_btn_css = _icon_btn_css()
        self._toggle_btn.setStyleSheet(icon_btn_css)
        self._toggle_btn.setIcon(theme.get_icon("fa6s.compress", color=icon_c))
        self._close_btn.setStyleSheet(icon_btn_css)
        self._close_btn.setIcon(theme.get_icon("fa6s.xmark", color=icon_c))

        # Dividers
        div_css = _divider_css()
        self._div_top.setStyleSheet(div_css)
        if hasattr(self, "_task_div"):
            self._task_div.setStyleSheet(div_css)
        if hasattr(self, "_diag_div"):
            self._diag_div.setStyleSheet(div_css)

        # Stat cells
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

        # Buttons
        for btn in self._task_btns:
            btn.setStyleSheet(_ghost_btn_css())
        for i, btn in enumerate(self._node_btns):
            btn.setStyleSheet(
                _accent_btn_css() if i == len(self._node_btns) - 1 else _ghost_btn_css()
            )
        self._clear_btn.setStyleSheet(_ghost_btn_css())

        # State badge
        self._on_state_changed(self._core.state)

        # Sparkline/Log
        if hasattr(self, "_spark_label"):
            self._spark_label.setStyleSheet(
                f"color: {muted}; font-size: 9px; font-family: 'Cascadia Code', Consolas; "
                f"background: transparent;"
            )
        self._log_area.setStyleSheet(
            f"color: {txt}; font-family: 'Cascadia Code', Consolas; "
            f"font-size: 10px; line-height: 1.7; background: transparent;"
        )

        # Update base frame paint borders mimicking Windows 11 Fluent frame
        self._base_frame.setStyleSheet(f"""
            QFrame#WorkspaceBase {{
                background: {theme.BG_BASE.name()};
                border: 1px solid {theme.BORDER.name()};
                border-radius: 16px;
            }}
        """)

        # Re-apply history cards themes
        for card in self._history_cards:
            card.apply_theme()

        self.update()

    # ── Lifecycle / Animation Hooks ──────────────────────────────────────────

    def _setup_animation(self) -> None:
        self._opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self._opacity_anim.setDuration(theme.TRANSITION_NORMAL)
        self._opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

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
        self._core.set_mode(APRILMode.AMBIENT)

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

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw translucent background only inside margins
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        p.end()

    # ── Diagnostic Refresh Slots ─────────────────────────────────────────────

    def _refresh_diag(self) -> None:
        self._cpu_cell.set_value(f"{random.randint(4, 25)} %")
        self._mem_cell.set_value(f"{random.uniform(0.9, 1.6):.1f} GB")
        self._lat_cell.set_value(f"{random.randint(60, 280)} ms")
        elapsed = int(time.monotonic()) % 3600
        self._sess_cell.set_value(f"{elapsed // 60}m {elapsed % 60}s")
        self._sparkline.push(random.randint(60, 280))

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

    def _on_mode_changed(self, mode: APRILMode) -> None:
        if mode == APRILMode.TACTICAL:
            self.expand()
        elif self.isVisible():
            self._collapse()

    def _on_state_changed(self, state: APRILState) -> None:
        colors = {
            APRILState.DORMANT: ("rgb(113, 113, 122)", "rgb(113, 113, 122)"), # Zinc 500
            APRILState.LISTENING: ("rgb(0, 120, 212)", "rgb(0, 120, 212)"), # Windows Blue
            APRILState.THINKING: ("rgb(0, 120, 212)", "rgb(0, 120, 212)"),
            APRILState.SPEAKING: ("rgb(0, 120, 212)", "rgb(0, 120, 212)"),
            APRILState.ACTING: ("rgb(139, 92, 246)", "rgb(139, 92, 246)"), # Violet
            APRILState.WARNING: ("rgb(245, 158, 11)", "rgb(245, 158, 11)"), # Amber
            APRILState.ERROR: ("rgb(239, 68, 68)", "rgb(239, 68, 68)"), # Red
        }
        lc, dc = colors.get(state, ("rgb(113, 113, 122)", "rgb(113, 113, 122)"))
        c = lc if theme.is_light_theme() else dc
        self._state_pill.update_state(state.name, c)
        self._state_pill.setStyleSheet(
            f"color: {c}; background: transparent; "
            f"border: 1px solid {c}30; border-radius: 5px; "
            f"font-size: 9px; font-family: 'Cascadia Code', Consolas; "
            f"padding: 2px 8px; letter-spacing: 0.8px;"
        )

# ── Dynamic Table Models ──────────────────────────────────────────────────────

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
                    "running": QColor(0, 120, 212),
                    "suspended": QColor(245, 158, 11),
                    "background": QColor(113, 113, 122),
                }
                return QBrush(status_colors.get(status, QColor(113, 113, 122)))
            return QBrush(QColor(24, 24, 27) if light else QColor(243, 243, 243))
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
                    QColor(0, 120, 212)
                    if status == "online"
                    else QColor(239, 68, 68)
                )
                return QBrush(c)
            return QBrush(QColor(24, 24, 27) if light else QColor(243, 243, 243))
        return None

# ── Metric Cells & Custom Table Styling ───────────────────────────────────────

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
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(2)
        self._val = QLabel(value)
        self._val.setFont(theme.ui_font(20))
        self._lbl = QLabel(label)
        self._lbl.setFont(theme.label_font(9))
        lay.addWidget(self._val)
        lay.addWidget(self._lbl)
        self.apply_theme()

    def apply_theme(self) -> None:
        light = theme.is_light_theme()
        bg = "rgba(0,0,0,6)" if light else "rgba(255,255,255,6)"
        border = "rgba(0,0,0,12)" if light else "rgba(255,255,255,10)"
        muted = "rgb(113, 113, 122)"
        self.setStyleSheet(
            f"QFrame {{ background: {bg}; border: 1px solid {border}; border-radius: 8px; }}"
        )
        self._val.setStyleSheet(f"color: {self._color}; background: transparent; border: none;")
        self._lbl.setStyleSheet(
            f"color: {muted}; font-size: 8px; letter-spacing: 0.8px; "
            f"background: transparent; border: none; text-transform: uppercase;"
        )

    def set_value(self, v: str) -> None:
        self._val.setText(v)

class _MetricCell(QFrame):
    def __init__(self, label: str, value: str, icon_name: str = "") -> None:
        super().__init__()
        self._icon_name = icon_name
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
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
        self._val.setFont(theme.mono_font(12))
        lay.addWidget(self._val)

        self.apply_theme()

    def apply_theme(self) -> None:
        light = theme.is_light_theme()
        bg = "rgba(0,0,0,6)" if light else "rgba(255,255,255,6)"
        border = "rgba(0,0,0,12)" if light else "rgba(255,255,255,10)"
        txt = "rgb(24, 24, 27)" if light else "rgb(243, 243, 243)"
        muted = "rgb(113, 113, 122)"
        self.setStyleSheet(
            f"QFrame {{ background: {bg}; border: 1px solid {border}; border-radius: 8px; }}"
        )
        self._val.setStyleSheet(f"color: {txt}; background: transparent; border: none;")
        self._lbl.setStyleSheet(
            f"color: {muted}; font-size: 8px; letter-spacing: 1px; "
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
        
        # Calculate graphic points
        pts = [
            (i * w / (self.MAX - 1), h - (v - mn) / rng * (h - 8) - 4)
            for i, v in enumerate(self._data)
        ]

        # Draw a beautiful smooth cubic Bezier curve
        path = QPainterPath()
        path.moveTo(pts[0][0], pts[0][1])
        for i in range(len(pts) - 1):
            p1 = pts[i]
            p2 = pts[i+1]
            dx = p2[0] - p1[0]
            # Control points for horizontal tangent smoothing
            cp1_x = p1[0] + dx / 3.0
            cp1_y = p1[1]
            cp2_x = p1[0] + 2.0 * dx / 3.0
            cp2_y = p2[1]
            path.cubicTo(cp1_x, cp1_y, cp2_x, cp2_y, p2[0], p2[1])

        # Fill path under the curve with a soft transparent gradient
        fill_path = QPainterPath(path)
        fill_path.lineTo(pts[-1][0], h)
        fill_path.lineTo(pts[0][0], h)
        fill_path.closeSubpath()

        light = theme.is_light_theme()
        grad = QLinearGradient(0, 0, 0, h)
        c_top = QColor(0, 120, 212, 45) if light else QColor(96, 205, 255, 45)
        c_bottom = QColor(0, 120, 212, 0) if light else QColor(96, 205, 255, 0)
        grad.setColorAt(0.0, c_top)
        grad.setColorAt(1.0, c_bottom)
        
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawPath(fill_path)

        # Draw the main curved stroke line
        line_color = QColor(0, 120, 212, 220) if light else QColor(96, 205, 255, 220)
        pen = QPen(line_color)
        pen.setWidthF(1.8)
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

# ── Stylesheets Definitions ──────────────────────────────────────────────────

def _divider_css() -> str:
    c = "rgba(0,0,0,12)" if theme.is_light_theme() else "rgba(255,255,255,10)"
    return f"color: {c}; background: {c}; border: none;"

def _icon_btn_css() -> str:
    light = theme.is_light_theme()
    hover = "rgba(0,0,0,6)" if light else "rgba(255,255,255,8)"
    pressed = "rgba(0,0,0,12)" if light else "rgba(255,255,255,12)"
    return f"""
        QPushButton {{
            background: transparent;
            border: none;
            border-radius: 6px;
            padding: 4px;
        }}
        QPushButton:hover   {{ background: {hover}; }}
        QPushButton:pressed {{ background: {pressed}; }}
    """

def _config_btn_css() -> str:
    light = theme.is_light_theme()
    hover = "rgba(0,0,0,6)" if light else "rgba(255,255,255,8)"
    return f"""
        QPushButton {{
            background: transparent;
            border: none;
            border-radius: 4px;
        }}
        QPushButton:hover {{ background: {hover}; }}
    """

def _sidebar_btn_css() -> str:
    """Vertical sidebar navigation button styling mimicking Windows 11 Settings rail."""
    is_light = theme.is_light_theme()
    color = "rgb(82, 82, 91)" if is_light else "rgb(161, 161, 170)"
    sel_color = "rgb(0, 120, 212)" if is_light else "rgb(96, 205, 255)"
    hover_bg = "rgba(0, 0, 0, 10)" if is_light else "rgba(255, 255, 255, 10)"
    active_bg = "rgba(0, 120, 212, 16)" if is_light else "rgba(255, 255, 255, 12)"
    txt = "rgb(24, 24, 27)" if is_light else "rgb(243, 243, 243)"
    border_c = "rgba(0, 120, 212, 220)" if is_light else "rgba(96, 205, 255, 220)"
    return f"""
        QPushButton {{
            background: transparent;
            color: {color};
            border: none;
            border-radius: 6px;
            font-size: 11px;
            font-family: 'Segoe UI Variable Text', 'Segoe UI';
            text-align: left;
            padding: 8px 12px;
        }}
        QPushButton:hover {{
            background: {hover_bg};
            color: {txt};
        }}
        QPushButton:checked {{
            background: {active_bg};
            color: {sel_color};
            font-weight: 600;
            border-left: 3px solid {border_c};
            border-top-left-radius: 0px;
            border-bottom-left-radius: 0px;
            padding-left: 9px;
        }}
    """

def _ghost_btn_css() -> str:
    light = theme.is_light_theme()
    bg = "rgba(0,0,0,4)" if light else "rgba(255,255,255,4)"
    border = "rgba(0,0,0,12)" if light else "rgba(255,255,255,10)"
    color = "rgb(82, 82, 91)" if light else "rgb(161, 161, 170)"
    hover_bg = "rgba(0,0,0,8)" if light else "rgba(255,255,255,8)"
    hover_c = "rgb(24, 24, 27)" if light else "rgb(243, 243, 243)"
    return f"""
        QPushButton {{
            background: {bg};
            color: {color};
            border: 1px solid {border};
            border-radius: 6px;
            font-size: 11px;
            font-family: 'Segoe UI Variable Text', 'Segoe UI';
            padding: 0 12px;
        }}
        QPushButton:hover   {{ background: {hover_bg}; color: {hover_c}; }}
        QPushButton:pressed {{ background: {bg}; }}
    """

def _accent_btn_css() -> str:
    bg = "rgba(0, 120, 212, 220)"
    hover = "rgba(0, 120, 212, 255)"
    return f"""
        QPushButton {{
            background: {bg};
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 11px;
            font-family: 'Segoe UI Variable Text', 'Segoe UI';
            font-weight: 600;
            padding: 0 14px;
        }}
        QPushButton:hover   {{ background: {hover}; }}
        QPushButton:pressed {{ background: {bg}; }}
    """

def _table_css() -> str:
    light = theme.is_light_theme()
    color = "rgb(24, 24, 27)" if light else "rgb(243, 243, 243)"
    sel_bg = "rgba(0, 120, 212, 16)" if light else "rgba(255, 255, 255, 12)"
    hover_bg = "rgba(0, 0, 0, 8)" if light else "rgba(255, 255, 255, 8)"
    row_border = "rgba(0,0,0,8)" if light else "rgba(255,255,255,8)"
    return f"""
        QTableView {{
            background: transparent;
            border: none;
            color: {color};
            font-size: 11px;
            font-family: 'Segoe UI Variable Text', 'Segoe UI';
            selection-background-color: {sel_bg};
            gridline-color: transparent;
        }}
        QTableView::item {{
            padding: 8px 12px;
            border-bottom: 1px solid {row_border};
            border-radius: 4px;
        }}
        QTableView::item:selected {{
            background: {sel_bg};
            color: {color};
        }}
        QTableView::item:hover {{
            background: {hover_bg};
        }}
    """

def _header_css() -> str:
    light = theme.is_light_theme()
    bg = "rgba(0,0,0,4)" if light else "rgba(255,255,255,4)"
    color = "rgb(113, 113, 122)"
    return f"""
        QHeaderView::section {{
            background: {bg};
            color: {color};
            font-size: 9px;
            font-family: 'Segoe UI Variable Display', sans-serif;
            font-weight: 600;
            letter-spacing: 0.8px;
            border: none;
            padding: 6px 12px;
            text-transform: uppercase;
        }}
    """

