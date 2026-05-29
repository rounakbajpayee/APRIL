"""
SettingsPanel — 8-category settings surface.

Design language (Fluent 2 / WinUI 3)
─────────────────────────────────────
• Left navigation rail: icon + label per category, search box.
• Right content area: scrollable per-category settings page.
• Acrylic glass background + subtle top gloss.
• All inputs, sliders, checkboxes, and combos adapt to light / dark theme.
• showEvent refreshes theme on every open so it always matches the system.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QSize
from PyQt6.QtGui import QPainter, QColor, QPen, QPainterPath, QLinearGradient, QCursor
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QFrame,
    QScrollArea,
    QLineEdit,
    QCheckBox,
    QSlider,
    QComboBox,
    QSizePolicy,
    QApplication,
)

from .state import APRILCore, APRILMode
from . import theme

# ── Category definitions ──────────────────────────────────────────────────────

_ALL_CATEGORIES = [
    dict(
        id="general",
        label="General",
        icon="fa6s.house",
        desc="Core operational behaviour",
        modes=[APRILMode.AMBIENT, APRILMode.FOCUS, APRILMode.TACTICAL],
    ),
    dict(
        id="voice",
        label="Voice",
        icon="fa6s.microphone",
        desc="Speech pipeline and dictation",
        modes=[APRILMode.AMBIENT, APRILMode.FOCUS, APRILMode.TACTICAL],
    ),
    dict(
        id="intelligence",
        label="Intelligence",
        icon="fa6s.brain",
        desc="Inference and reasoning configuration",
        modes=[APRILMode.FOCUS, APRILMode.TACTICAL],
    ),
    dict(
        id="nodes",
        label="Nodes",
        icon="fa6s.network_wired",
        desc="Distributed orchestration infrastructure",
        modes=[APRILMode.FOCUS, APRILMode.TACTICAL],
    ),
    dict(
        id="integrations",
        label="Integrations",
        icon="fa6s.plug",
        desc="External ecosystem connections",
        modes=[APRILMode.FOCUS, APRILMode.TACTICAL],
    ),
    dict(
        id="behaviors",
        label="Behaviors",
        icon="fa6s.sliders",
        desc="Behavior-layer tuning",
        modes=[APRILMode.FOCUS, APRILMode.TACTICAL],
    ),
    dict(
        id="diagnostics",
        label="Diagnostics",
        icon="fa6s.chart_bar",
        desc="Runtime introspection",
        modes=[APRILMode.TACTICAL],
    ),
    dict(
        id="system",
        label="System",
        icon="fa6s.circle_half_stroke",
        desc="Low-level runtime controls",
        modes=[APRILMode.TACTICAL],
    ),
]


def _categories_for_mode(mode: APRILMode) -> list[dict]:
    return [c for c in _ALL_CATEGORIES if mode in c["modes"]]


# ── Settings panel ────────────────────────────────────────────────────────────


class SettingsPanel(QWidget):

    def __init__(self, core: APRILCore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._core = core
        self._active_id: str | None = None
        self._cat_buttons: dict[str, QPushButton] = {}
        self._categories = _categories_for_mode(core.mode)

        self._setup_window()
        self._build_ui()

        if self._categories:
            self._select(self._categories[0]["id"])

        core.mode_changed.connect(self._on_mode_changed)

    def showEvent(self, event) -> None:  # noqa: N802
        theme.refresh_theme()
        self._apply_theme()
        super().showEvent(event)

    # ------------------------------------------------------------------ window

    def _setup_window(self) -> None:
        self.setFixedSize(theme.SETTINGS_W, theme.SETTINGS_H)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Dialog
        )
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            screen.center().x() - self.width() // 2,
            screen.center().y() - self.height() // 2,
        )

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Left navigation rail ──────────────────────────────────────────
        self._rail = QWidget()
        self._rail.setFixedWidth(210)
        self._rail.setObjectName("rail")
        rail_lay = QVBoxLayout(self._rail)
        rail_lay.setContentsMargins(0, 0, 0, 0)
        rail_lay.setSpacing(0)

        # Rail header
        rail_hdr = QWidget()
        rail_hdr.setFixedHeight(70)
        rail_hdr.setObjectName("rail_hdr")
        hdr_lay = QVBoxLayout(rail_hdr)
        hdr_lay.setContentsMargins(20, 16, 20, 16)
        hdr_lay.setSpacing(2)

        self._brand_icon_lbl = QLabel()
        self._brand_icon_lbl.setFixedSize(20, 20)
        hdr_lay.addWidget(self._brand_icon_lbl)

        title_row = QHBoxLayout()
        self._settings_title = QLabel("Settings")
        self._settings_title.setFont(theme.ui_font(13))
        title_row.addWidget(self._settings_title)
        title_row.addStretch()
        hdr_lay.addLayout(title_row)

        rail_lay.addWidget(rail_hdr)

        # Search
        search_wrap = QWidget()
        search_wrap.setFixedHeight(50)
        search_wrap.setStyleSheet("background: transparent;")
        sw_lay = QVBoxLayout(search_wrap)
        sw_lay.setContentsMargins(12, 8, 12, 8)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search settings…")
        self._search.setClearButtonEnabled(True)
        self._search.setFixedHeight(30)
        self._search.textChanged.connect(self._filter_categories)
        sw_lay.addWidget(self._search)
        rail_lay.addWidget(search_wrap)

        # Category list
        self._cat_scroll = QScrollArea()
        self._cat_scroll.setWidgetResizable(True)
        self._cat_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._cat_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { width: 3px; background: transparent; }"
            "QScrollBar::handle:vertical { background: rgba(148,163,184,60); border-radius: 1px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        cat_container = QWidget()
        cat_container.setStyleSheet("background: transparent;")
        self._cat_layout = QVBoxLayout(cat_container)
        self._cat_layout.setContentsMargins(10, 6, 10, 10)
        self._cat_layout.setSpacing(2)
        self._cat_layout.addStretch()
        self._cat_scroll.setWidget(cat_container)
        rail_lay.addWidget(self._cat_scroll, 1)

        # Rail footer
        rail_footer = QWidget()
        rail_footer.setFixedHeight(56)
        rail_footer.setStyleSheet("background: transparent;")
        rf_lay = QHBoxLayout(rail_footer)
        rf_lay.setContentsMargins(12, 10, 12, 10)
        self._reset_btn = QPushButton("Reset to Defaults")
        self._reset_btn.setIcon(theme.get_icon("fa6s.rotate_left"))
        self._reset_btn.setFixedHeight(30)
        self._reset_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        rf_lay.addWidget(self._reset_btn)
        rail_lay.addWidget(rail_footer)

        root.addWidget(self._rail)

        # ── Right content area ────────────────────────────────────────────
        content_wrap = QWidget()
        content_wrap.setStyleSheet("background: transparent;")
        content_lay = QVBoxLayout(content_wrap)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(0)

        # Content header
        self._content_hdr = QWidget()
        self._content_hdr.setFixedHeight(70)
        self._content_hdr.setStyleSheet("background: transparent;")
        ch_lay = QHBoxLayout(self._content_hdr)
        ch_lay.setContentsMargins(28, 16, 20, 16)
        ch_lay.setSpacing(12)

        # Category icon in header
        self._content_icon_lbl = QLabel()
        self._content_icon_lbl.setFixedSize(22, 22)
        ch_lay.addWidget(self._content_icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        self._content_title = QLabel("—")
        self._content_title.setFont(theme.ui_font(14))
        self._content_desc = QLabel("")
        self._content_desc.setFont(theme.ui_font(10))
        title_col.addWidget(self._content_title)
        title_col.addWidget(self._content_desc)
        ch_lay.addLayout(title_col)
        ch_lay.addStretch()

        self._mode_badge = QLabel("AMBIENT MODE")
        self._mode_badge.setFont(theme.label_font(8))
        ch_lay.addWidget(self._mode_badge)

        self._close_btn = QPushButton()
        self._close_btn.setIcon(theme.get_icon("fa6s.xmark"))
        self._close_btn.setToolTip("Close (Esc)")
        self._close_btn.setFixedSize(30, 30)
        self._close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._close_btn.clicked.connect(self.close)
        ch_lay.addWidget(self._close_btn)
        content_lay.addWidget(self._content_hdr)

        # Rail / content divider
        self._rail_div = _VDivider()
        # (rendered as part of painting, not as a widget divider here)

        # Stack of setting pages
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent;")
        self._pages: dict[str, QWidget] = {}
        for cat in _ALL_CATEGORIES:
            page = _build_page(cat["id"])
            self._pages[cat["id"]] = page
            self._stack.addWidget(page)
        content_lay.addWidget(self._stack, 1)

        root.addWidget(content_wrap, 1)

        self._rebuild_cat_buttons()
        self._apply_theme()

    # ------------------------------------------------------------------ theme

    def _apply_theme(self) -> None:
        light = theme.is_light_theme()
        accent = "rgb(8,145,178)" if light else "rgb(56,189,248)"
        title_color = "rgb(15,23,42)" if light else "rgb(220,230,248)"
        muted = "rgb(100,116,139)"
        rail_border = "rgba(0,0,0,14)" if light else "rgba(255,255,255,12)"

        # Rail border (right edge only)
        self._rail.setStyleSheet(
            f"QWidget#rail {{ background: transparent; border-right: 1px solid {rail_border}; }}"
        )

        # Rail header
        rail_hdr_border = "rgba(0,0,0,12)" if light else "rgba(255,255,255,10)"
        self._brand_icon_lbl.setPixmap(
            theme.get_icon("fa6s.circle_dot", color=accent).pixmap(18, 18)
        )
        self._settings_title.setStyleSheet(
            f"color: {accent}; font-size: 13px; font-weight: 600; "
            f"font-family: 'Segoe UI Variable Display', sans-serif; background: transparent; border: none;"
        )

        # Search field
        self._search.setStyleSheet(_input_css())

        # Reset button
        self._reset_btn.setStyleSheet(_warn_btn_css())
        self._reset_btn.setIcon(theme.get_icon("fa6s.rotate_left", color="rgb(185,28,28)"))

        # Mode badge
        self._mode_badge.setStyleSheet(
            f"color: {muted}; font-size: 8px; letter-spacing: 1.4px; "
            f"font-family: 'Segoe UI Variable Display', sans-serif; background: transparent; border: none;"
        )
        self._mode_badge.setText(f"{self._core.mode.name}  MODE")

        # Content header
        self._content_title.setStyleSheet(
            f"color: {title_color}; font-size: 14px; font-weight: 300; "
            f"font-family: 'Segoe UI Variable Display', sans-serif; background: transparent; border: none;"
        )
        self._content_desc.setStyleSheet(
            f"color: {muted}; font-size: 10px; "
            f"font-family: 'Segoe UI Variable Display', sans-serif; background: transparent; border: none;"
        )
        self._close_btn.setStyleSheet(_icon_btn_css())
        self._close_btn.setIcon(
            theme.get_icon("fa6s.xmark", color="rgb(71,85,105)" if light else "rgb(148,163,184)")
        )

        # Cascade theme to all child controls
        for edit in self.findChildren(QLineEdit):
            if edit is not self._search:
                edit.setStyleSheet(_input_css())
        for combo in self.findChildren(QComboBox):
            combo.setStyleSheet(_combo_css())
        for sl in self.findChildren(QSlider):
            sl.setStyleSheet(_slider_css())
        for cb in self.findChildren(QCheckBox):
            cb.setStyleSheet(_checkbox_css())
        for lbl in self.findChildren(QLabel):
            txt = lbl.text()
            if txt.isupper() and 2 < len(txt) < 32:
                lbl.setStyleSheet(
                    f"color: {muted}; font-size: 9px; letter-spacing: 1.4px; "
                    f"font-family: 'Segoe UI Variable Display', sans-serif; "
                    f"background: transparent; border: none; padding-top: 6px;"
                )
            elif (
                lbl
                not in (
                    self._settings_title,
                    self._content_title,
                    self._content_desc,
                    self._mode_badge,
                    self._brand_icon_lbl,
                    self._content_icon_lbl,
                )
                and lbl.objectName() not in ("brand_icon", "content_icon")
                and not txt.isupper()
            ):
                lbl.setStyleSheet(
                    f"color: {title_color}; font-size: 12px; "
                    f"font-family: 'Segoe UI Variable Display', sans-serif; "
                    f"background: transparent; border: none;"
                )

        self._rebuild_cat_buttons()
        self.update()

    def _rebuild_cat_buttons(self) -> None:
        while self._cat_layout.count() > 1:
            item = self._cat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        query = self._search.text().lower()
        self._cat_buttons.clear()

        for cat in self._categories:
            if query and query not in cat["label"].lower():
                continue
            btn = _NavButton(cat["label"], cat["icon"])
            btn.setCheckable(True)
            btn.clicked.connect(lambda _checked, cid=cat["id"]: self._select(cid))
            self._cat_buttons[cat["id"]] = btn
            self._cat_layout.insertWidget(self._cat_layout.count() - 1, btn)

        for cid, btn in self._cat_buttons.items():
            btn.set_active(cid == self._active_id)

    def _select(self, cat_id: str) -> None:
        self._active_id = cat_id
        for cid, btn in self._cat_buttons.items():
            btn.set_active(cid == cat_id)

        cat = next((c for c in self._categories if c["id"] == cat_id), None)
        if cat:
            self._content_title.setText(cat["label"])
            self._content_desc.setText(cat["desc"])
            ic = theme.get_icon(
                cat["icon"],
                color="rgb(8,145,178)" if theme.is_light_theme() else "rgb(56,189,248)",
            )
            self._content_icon_lbl.setPixmap(ic.pixmap(20, 20))

        if cat_id in self._pages:
            self._stack.setCurrentWidget(self._pages[cat_id])

    def _filter_categories(self) -> None:
        self._rebuild_cat_buttons()
        if self._active_id and self._active_id in self._cat_buttons:
            self._select(self._active_id)
        elif self._cat_buttons:
            self._select(next(iter(self._cat_buttons)))

    # ------------------------------------------------------------------ painting

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 20, 20)

        p.setClipPath(path)
        p.fillRect(0, 0, self.width(), self.height(), theme.BG_BASE)

        grad = QLinearGradient(0, 0, 0, 100)
        grad.setColorAt(0, QColor(255, 255, 255, 18 if not theme.is_light_theme() else 35))
        grad.setColorAt(1, QColor(0, 0, 0, 0))
        p.fillRect(0, 0, self.width(), 100, grad)

        p.setClipping(False)
        pen = QPen(theme.BORDER)
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.end()

    # ------------------------------------------------------------------ keyboard

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------------------ slots

    def _on_mode_changed(self, mode: APRILMode) -> None:
        self._categories = _categories_for_mode(mode)
        self._mode_badge.setText(f"{mode.name}  MODE")
        self._rebuild_cat_buttons()
        if self._cat_buttons:
            self._select(next(iter(self._cat_buttons)))


# ── Nav button with icon ──────────────────────────────────────────────────────


class _NavButton(QPushButton):
    def __init__(self, label: str, icon_name: str) -> None:
        super().__init__(label)
        self._icon_name = icon_name
        self.setCheckable(True)
        self.setFixedHeight(36)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setIconSize(QSize(14, 14))
        self.set_active(False)

    def set_active(self, active: bool) -> None:
        light = theme.is_light_theme()
        accent = "rgb(8,145,178)" if light else "rgb(56,189,248)"
        inactive_c = "rgb(100,116,139)"
        hover_c = "rgb(15,23,42)" if light else "rgb(220,230,248)"
        active_bg = "rgba(8,145,178,12)" if light else "rgba(56,189,248,10)"
        hover_bg = "rgba(0,0,0,6)" if light else "rgba(255,255,255,6)"

        if active:
            self.setIcon(theme.get_icon(self._icon_name, color=accent))
            self.setStyleSheet(f"""
QPushButton {{
    background: {active_bg};
    color: {accent};
    border: none;
    border-left: 2px solid {accent};
    border-radius: 7px;
    font-size: 12px;
    font-family: 'Segoe UI Variable Display', 'Segoe UI';
    font-weight: 600;
    padding: 0 12px 0 10px;
    text-align: left;
}}
""")
        else:
            self.setIcon(theme.get_icon(self._icon_name, color=inactive_c))
            self.setStyleSheet(f"""
QPushButton {{
    background: transparent;
    color: {inactive_c};
    border: none;
    border-left: 2px solid transparent;
    border-radius: 7px;
    font-size: 12px;
    font-family: 'Segoe UI Variable Display', 'Segoe UI';
    padding: 0 12px 0 10px;
    text-align: left;
}}
QPushButton:hover {{ background: {hover_bg}; color: {hover_c}; }}
""")


class _VDivider(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setFrameShape(QFrame.Shape.VLine)
        self.setFixedWidth(1)


# ── Page builders ─────────────────────────────────────────────────────────────


def _build_page(cat_id: str) -> QWidget:
    builders = {
        "general": _page_general,
        "voice": _page_voice,
        "intelligence": _page_intelligence,
        "nodes": _page_nodes,
        "integrations": _page_integrations,
        "behaviors": _page_behaviors,
        "diagnostics": _page_diagnostics,
        "system": _page_system,
    }
    fn = builders.get(cat_id, _page_placeholder)
    wrapper = QWidget()
    wrapper.setStyleSheet("background: transparent;")
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setStyleSheet(
        "QScrollArea { background: transparent; border: none; }"
        "QScrollBar:vertical { width: 4px; background: transparent; }"
        "QScrollBar::handle:vertical { background: rgba(148,163,184,80); border-radius: 2px; }"
        "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
    )
    inner = fn()
    inner.setStyleSheet("background: transparent;")
    scroll.setWidget(inner)
    lay = QVBoxLayout(wrapper)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(scroll)
    return wrapper


def _page_general() -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(28, 20, 28, 20)
    lay.setSpacing(16)
    lay.addWidget(_section("Presence"))
    lay.addWidget(_toggle("Start on login", True))
    lay.addWidget(_toggle("Show in taskbar", False))
    lay.addWidget(_combo_row("Default mode", ["Ambient", "Focus", "Tactical"]))
    lay.addWidget(_combo_row("Presence profile", ["Minimal", "Balanced", "Immersive"]))
    lay.addWidget(_section("Invocation"))
    lay.addWidget(_text_row("Wake phrase", "Hey April"))
    lay.addWidget(_toggle("Push-to-talk fallback", True))
    lay.addWidget(_slider_row("Trigger sensitivity", 70))
    lay.addWidget(_section("Appearance"))
    lay.addWidget(_combo_row("Theme", ["System default", "Always light", "Always dark"]))
    lay.addWidget(_toggle("Corner orb visible", True))
    lay.addWidget(
        _combo_row("Default corner", ["Bottom right", "Bottom left", "Top right", "Top left"])
    )
    lay.addStretch()
    return w


def _page_voice() -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(28, 20, 28, 20)
    lay.setSpacing(16)
    lay.addWidget(_section("Speech Recognition"))
    lay.addWidget(_combo_row("Engine", ["Whisper (local)", "Azure STT", "Google STT"]))
    lay.addWidget(_slider_row("Silence threshold (ms)", 600))
    lay.addWidget(_toggle("Show live transcription", True))
    lay.addWidget(_toggle("Auto-correct with LLM cleanup", True))
    lay.addWidget(_section("Text-to-Speech"))
    lay.addWidget(_combo_row("Voice", ["af_alloy", "af_bella", "am_adam"]))
    lay.addWidget(_slider_row("Speed", 100))
    lay.addWidget(_slider_row("Volume", 80))
    lay.addWidget(_section("Audio"))
    lay.addWidget(_combo_row("Input device", ["Default microphone"]))
    lay.addWidget(_toggle("Noise suppression", True))
    lay.addWidget(_toggle("Echo cancellation", True))
    lay.addStretch()
    return w


def _page_intelligence() -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(28, 20, 28, 20)
    lay.setSpacing(16)
    lay.addWidget(_section("Model"))
    lay.addWidget(
        _combo_row("Primary model", ["cloud-gemini-flash", "cloud-deepseek-v3", "local-qwen-7b"])
    )
    lay.addWidget(_combo_row("Fallback model", ["cloud-deepseek-v3", "local-qwen-7b"]))
    lay.addWidget(_slider_row("Temperature", 70))
    lay.addWidget(_slider_row("Max tokens (k)", 16))
    lay.addWidget(_section("Context"))
    lay.addWidget(_toggle("Rolling context window", True))
    lay.addWidget(_slider_row("Context depth (turns)", 20))
    lay.addWidget(_toggle("Persist across sessions", False))
    lay.addStretch()
    return w


def _page_nodes() -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(28, 20, 28, 20)
    lay.setSpacing(16)
    lay.addWidget(_section("Node Registry"))
    lay.addWidget(_info_row("mac (inference)", "online · 100.70.3.86"))
    lay.addWidget(_info_row("dell (apps)", "online · 100.103.208.28"))
    lay.addWidget(_info_row("cortex (LiteLLM)", "online · cortex.home.lan"))
    lay.addWidget(_section("Routing"))
    lay.addWidget(_combo_row("Task routing", ["Auto", "Local-first", "Cloud-first"]))
    lay.addWidget(_toggle("Failover to cloud", True))
    lay.addWidget(_slider_row("Timeout (s)", 30))
    lay.addStretch()
    return w


def _page_integrations() -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(28, 20, 28, 20)
    lay.setSpacing(16)
    lay.addWidget(_section("Connected Services"))
    for name, connected in [
        ("Oracle (knowledge store)", True),
        ("Vikunja (tasks)", True),
        ("n8n (connector)", True),
        ("Telegram bot", True),
        ("Discord", False),
    ]:
        lay.addWidget(_toggle(name, connected))
    lay.addWidget(_section("API Keys"))
    lay.addWidget(_text_row("OpenRouter key", "sk-or-…  (stored in keychain)"))
    lay.addStretch()
    return w


def _page_behaviors() -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(28, 20, 28, 20)
    lay.setSpacing(16)
    lay.addWidget(_section("Interruption Handling"))
    lay.addWidget(
        _combo_row("On new critical notification", ["Pause and notify", "Queue", "Ignore"])
    )
    lay.addWidget(_toggle("Allow mid-sentence interruption", True))
    lay.addWidget(_section("Idle Behavior"))
    lay.addWidget(_combo_row("After 5 min idle", ["Stay ambient", "Collapse to minimal", "Sleep"]))
    lay.addWidget(_toggle("Idle breathing animation", True))
    lay.addWidget(_section("Continuity"))
    lay.addWidget(_toggle("Resume suspended tasks on wake", True))
    lay.addWidget(_toggle("Restore last mode on start", False))
    lay.addStretch()
    return w


def _page_diagnostics() -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(28, 20, 28, 20)
    lay.setSpacing(16)
    lay.addWidget(_section("Runtime Metrics"))
    lay.addWidget(_info_row("Uptime", "—"))
    lay.addWidget(_info_row("Total requests", "—"))
    lay.addWidget(_info_row("Avg latency", "—"))
    lay.addWidget(_info_row("Errors (session)", "0"))
    lay.addWidget(_section("Logging"))
    lay.addWidget(_combo_row("Log level", ["INFO", "DEBUG", "WARNING", "ERROR"]))
    lay.addWidget(_toggle("Write to disk", False))
    lay.addStretch()
    return w


def _page_system() -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(28, 20, 28, 20)
    lay.setSpacing(16)
    lay.addWidget(_section("Runtime"))
    lay.addWidget(_info_row("APRIL version", "0.1.0-alpha"))
    lay.addWidget(_info_row("Python", "3.13"))
    lay.addWidget(_info_row("PyQt6", "6.7"))
    lay.addWidget(_toggle("Hardware acceleration", True))
    lay.addWidget(_toggle("Experimental features", False))
    lay.addWidget(_section("Danger Zone"))
    danger_btn = QPushButton("Factory Reset…")
    danger_btn.setIcon(theme.get_icon("fa6s.triangle_exclamation", color="rgb(239,68,68)"))
    danger_btn.setFixedHeight(34)
    danger_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    danger_btn.setStyleSheet("""
QPushButton {
    background: rgba(239,68,68,12);
    color: rgb(239,68,68);
    border: 1px solid rgba(239,68,68,50);
    border-radius: 8px;
    font-size: 12px;
    font-family: 'Segoe UI Variable Display', 'Segoe UI';
    padding: 0 16px;
}
QPushButton:hover { background: rgba(239,68,68,22); }
""")
    lay.addWidget(danger_btn)
    lay.addStretch()
    return w


def _page_placeholder() -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl = QLabel("Coming soon")
    lbl.setStyleSheet("color: rgb(100,116,139); font-size: 13px;")
    lay.addWidget(lbl)
    return w


# ── Setting row widgets ───────────────────────────────────────────────────────


def _section(title: str) -> QLabel:
    lbl = QLabel(title.upper())
    return lbl


def _toggle(label: str, default: bool) -> QWidget:
    row = QWidget()
    row.setStyleSheet("background: transparent;")
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lbl = QLabel(label)
    lay.addWidget(lbl)
    lay.addStretch()
    cb = QCheckBox()
    cb.setChecked(default)
    lay.addWidget(cb)
    return row


def _combo_row(label: str, options: list[str]) -> QWidget:
    row = QWidget()
    row.setStyleSheet("background: transparent;")
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lbl = QLabel(label)
    lay.addWidget(lbl)
    lay.addStretch()
    cb = QComboBox()
    cb.addItems(options)
    cb.setFixedWidth(190)
    cb.setFixedHeight(30)
    lay.addWidget(cb)
    return row


def _slider_row(label: str, default: int) -> QWidget:
    row = QWidget()
    row.setStyleSheet("background: transparent;")
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lbl = QLabel(label)
    lay.addWidget(lbl)
    lay.addStretch()
    light = theme.is_light_theme()
    accent = "rgb(8,145,178)" if light else "rgb(56,189,248)"
    val_lbl = QLabel(str(default))
    val_lbl.setFixedWidth(36)
    val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    val_lbl.setStyleSheet(
        f"color: {accent}; font-size: 11px; font-family: 'Cascadia Code', Consolas; background: transparent;"
    )
    sl = QSlider(Qt.Orientation.Horizontal)
    sl.setRange(0, 100)
    sl.setValue(default)
    sl.setFixedWidth(150)
    sl.valueChanged.connect(lambda v: val_lbl.setText(str(v)))
    lay.addWidget(val_lbl)
    lay.addWidget(sl)
    return row


def _text_row(label: str, value: str) -> QWidget:
    row = QWidget()
    row.setStyleSheet("background: transparent;")
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lbl = QLabel(label)
    lay.addWidget(lbl)
    lay.addStretch()
    inp = QLineEdit(value)
    inp.setFixedWidth(210)
    inp.setFixedHeight(30)
    lay.addWidget(inp)
    return row


def _info_row(label: str, value: str) -> QWidget:
    row = QWidget()
    row.setStyleSheet("background: transparent;")
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lbl = QLabel(label)
    lay.addWidget(lbl)
    lay.addStretch()
    val = QLabel(value)
    val.setStyleSheet(
        "color: rgb(100,116,139); font-size: 11px; font-family: 'Cascadia Code', Consolas; "
        "background: transparent; border: none;"
    )
    lay.addWidget(val)
    return row


# ── Style functions ───────────────────────────────────────────────────────────


def _icon_btn_css() -> str:
    light = theme.is_light_theme()
    hover = "rgba(0,0,0,7)" if light else "rgba(255,255,255,8)"
    return f"""
QPushButton {{
    background: transparent;
    border: none;
    border-radius: 7px;
    padding: 4px;
}}
QPushButton:hover {{ background: {hover}; }}
"""


def _input_css() -> str:
    light = theme.is_light_theme()
    bg = "rgba(0,0,0,6)" if light else "rgba(255,255,255,7)"
    border = "rgba(0,0,0,18)" if light else "rgba(255,255,255,15)"
    color = "rgb(15,23,42)" if light else "rgb(220,230,248)"
    focus = "rgba(8,145,178,100)" if light else "rgba(56,189,248,100)"
    placeholder = "rgb(148,163,184)"
    return f"""
QLineEdit {{
    background: {bg};
    border: 1px solid {border};
    border-radius: 7px;
    color: {color};
    font-size: 11px;
    font-family: 'Segoe UI Variable Display', 'Segoe UI';
    padding: 0 10px;
}}
QLineEdit:focus {{ border-color: {focus}; }}
QLineEdit::placeholder {{ color: {placeholder}; }}
"""


def _combo_css() -> str:
    light = theme.is_light_theme()
    bg = "rgba(0,0,0,6)" if light else "rgba(255,255,255,7)"
    border = "rgba(0,0,0,18)" if light else "rgba(255,255,255,15)"
    color = "rgb(15,23,42)" if light else "rgb(220,230,248)"
    popup_bg = "rgb(245,246,250)" if light else "rgb(20,24,38)"
    sel = "rgba(8,145,178,30)" if light else "rgba(56,189,248,28)"
    focus = "rgba(8,145,178,100)" if light else "rgba(56,189,248,100)"
    return f"""
QComboBox {{
    background: {bg};
    border: 1px solid {border};
    border-radius: 7px;
    color: {color};
    font-size: 11px;
    font-family: 'Segoe UI Variable Display', 'Segoe UI';
    padding: 0 10px;
}}
QComboBox:focus {{ border-color: {focus}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {popup_bg};
    border: 1px solid {border};
    border-radius: 8px;
    color: {color};
    selection-background-color: {sel};
    padding: 4px;
}}
"""


def _slider_css() -> str:
    light = theme.is_light_theme()
    groove = "rgba(0,0,0,12)" if light else "rgba(255,255,255,12)"
    handle = "rgb(8,145,178)" if light else "rgb(56,189,248)"
    sub = "rgba(8,145,178,110)" if light else "rgba(56,189,248,100)"
    return f"""
QSlider::groove:horizontal {{
    height: 4px;
    background: {groove};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 14px; height: 14px;
    margin: -5px 0;
    border-radius: 7px;
    background: {handle};
}}
QSlider::sub-page:horizontal {{
    background: {sub};
    border-radius: 2px;
}}
"""


def _checkbox_css() -> str:
    light = theme.is_light_theme()
    border = "rgba(0,0,0,28)" if light else "rgba(255,255,255,25)"
    bg = "rgba(0,0,0,6)" if light else "rgba(255,255,255,6)"
    checked = "rgb(8,145,178)" if light else "rgb(56,189,248)"
    return f"""
QCheckBox::indicator {{
    width: 18px; height: 18px;
    border-radius: 5px;
    border: 1px solid {border};
    background: {bg};
}}
QCheckBox::indicator:checked {{
    background: {checked};
    border-color: {checked};
}}
"""


def _warn_btn_css() -> str:
    return """
QPushButton {
    background: rgba(239,68,68,8);
    color: rgb(239,68,68);
    border: 1px solid rgba(239,68,68,30);
    border-radius: 7px;
    font-size: 11px;
    font-family: 'Segoe UI Variable Display', 'Segoe UI';
    padding: 0 12px;
}
QPushButton:hover { background: rgba(239,68,68,16); }
"""
