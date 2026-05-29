"""
SettingsPanel — mirror of the React settings system.

8 categories with progressive disclosure based on mode.
Opens as a centred frameless window, Escape/✕ to dismiss.
"""

from __future__ import annotations
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPainter, QColor, QPen, QPainterPath, QLinearGradient
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

# ------------------------------------------------------------------ categories


def _categories_for_mode(mode: APRILMode) -> list[dict]:
    all_cats = [
        dict(
            id="general",
            label="General",
            desc="Core APRIL operational behaviour",
            modes=[APRILMode.AMBIENT, APRILMode.FOCUS, APRILMode.TACTICAL],
        ),
        dict(
            id="voice",
            label="Voice",
            desc="Speech pipeline and conversational interaction",
            modes=[APRILMode.AMBIENT, APRILMode.FOCUS, APRILMode.TACTICAL],
        ),
        dict(
            id="intelligence",
            label="Intelligence",
            desc="Inference and reasoning configuration",
            modes=[APRILMode.FOCUS, APRILMode.TACTICAL],
        ),
        dict(
            id="nodes",
            label="Nodes",
            desc="Distributed orchestration infrastructure",
            modes=[APRILMode.FOCUS, APRILMode.TACTICAL],
        ),
        dict(
            id="integrations",
            label="Integrations",
            desc="External ecosystem integration",
            modes=[APRILMode.FOCUS, APRILMode.TACTICAL],
        ),
        dict(
            id="behaviors",
            label="Behaviors",
            desc="Behavior-layer tuning",
            modes=[APRILMode.FOCUS, APRILMode.TACTICAL],
        ),
        dict(
            id="diagnostics",
            label="Diagnostics",
            desc="Runtime introspection and orchestration visibility",
            modes=[APRILMode.TACTICAL],
        ),
        dict(
            id="system",
            label="System",
            desc="Low-level runtime and internal system controls",
            modes=[APRILMode.TACTICAL],
        ),
    ]
    return [c for c in all_cats if mode in c["modes"]]


# ------------------------------------------------------------------ panel


class SettingsPanel(QWidget):
    def __init__(self, core: APRILCore, parent=None):
        super().__init__(parent)
        self._core = core
        self._active = None  # FIX-08: initialize before _build_ui / signal handlers
        self._categories = _categories_for_mode(core.mode)

        self._setup_window()
        self._build_ui()
        self._select(self._categories[0]["id"])

        core.mode_changed.connect(self._on_mode_changed)

    # ------------------------------------------------------------------ window

    def _setup_window(self):
        self.setFixedSize(860, 560)
        # FIX-04: opaque background — no WA_TranslucentBackground
        self.setStyleSheet("background: rgb(10, 10, 18);")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Dialog
        )
        self._center()

    def _center(self):
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.center().x() - self.width() // 2
        y = screen.center().y() - self.height() // 2
        self.move(x, y)

    # ------------------------------------------------------------------ ui

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Left rail ----
        rail = QWidget()
        rail.setFixedWidth(200)
        rail.setStyleSheet(
            "background: transparent; border-right: 1px solid rgba(255,255,255,15);"
        )
        rail_lay = QVBoxLayout(rail)
        rail_lay.setContentsMargins(0, 0, 0, 0)
        rail_lay.setSpacing(0)

        hdr = QWidget()
        hdr.setFixedHeight(64)
        hdr.setStyleSheet("border-bottom: 1px solid rgba(255,255,255,15);")
        hdr_lay = QVBoxLayout(hdr)
        hdr_lay.setContentsMargins(20, 14, 20, 14)
        hdr_lay.setSpacing(2)
        title = QLabel("Settings")
        title.setStyleSheet(
            "color: rgb(165,243,252); font-size: 14px; font-family: 'Inter','Segoe UI'; font-weight: 300; border: none;"
        )
        self._mode_lbl = QLabel(self._core.mode.name.capitalize() + " mode")
        self._mode_lbl.setStyleSheet(
            "color: rgb(113,113,122); font-size: 10px; font-family: 'JetBrains Mono',Consolas; border: none;"
        )
        hdr_lay.addWidget(title)
        hdr_lay.addWidget(self._mode_lbl)
        rail_lay.addWidget(hdr)

        search_wrap = QWidget()
        search_wrap.setFixedHeight(52)
        search_wrap.setStyleSheet(
            "border-bottom: 1px solid rgba(255,255,255,8); background: transparent;"
        )
        sw_lay = QVBoxLayout(search_wrap)
        sw_lay.setContentsMargins(12, 10, 12, 10)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search settings…")
        self._search.setStyleSheet(_INPUT_STYLE)
        self._search.textChanged.connect(self._filter_categories)
        sw_lay.addWidget(self._search)
        rail_lay.addWidget(search_wrap)

        self._cat_scroll = QScrollArea()
        self._cat_scroll.setWidgetResizable(True)
        self._cat_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._cat_scroll.setStyleSheet("background: transparent;")
        cat_container = QWidget()
        cat_container.setStyleSheet("background: transparent;")
        self._cat_layout = QVBoxLayout(cat_container)
        self._cat_layout.setContentsMargins(8, 8, 8, 8)
        self._cat_layout.setSpacing(2)
        self._cat_layout.addStretch()
        self._cat_scroll.setWidget(cat_container)
        rail_lay.addWidget(self._cat_scroll, 1)

        footer = QWidget()
        footer.setFixedHeight(52)
        footer.setStyleSheet(
            "border-top: 1px solid rgba(255,255,255,15); background: transparent;"
        )
        ft_lay = QHBoxLayout(footer)
        ft_lay.setContentsMargins(12, 8, 12, 8)
        reset_btn = QPushButton("↺  Reset to Defaults")
        reset_btn.setStyleSheet(_BTN_WARN)
        reset_btn.setFixedHeight(28)
        ft_lay.addWidget(reset_btn)
        rail_lay.addWidget(footer)

        root.addWidget(rail)

        # ---- Right content area ----
        content_wrap = QWidget()
        content_lay = QVBoxLayout(content_wrap)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(0)

        self._content_hdr = QWidget()
        self._content_hdr.setFixedHeight(64)
        self._content_hdr.setStyleSheet(
            "border-bottom: 1px solid rgba(255,255,255,15); background: transparent;"
        )
        ch_lay = QHBoxLayout(self._content_hdr)
        ch_lay.setContentsMargins(28, 14, 20, 14)
        self._content_title = QLabel("—")
        self._content_title.setStyleSheet(
            "color: rgb(165,243,252); font-size: 16px; font-family: 'Inter','Segoe UI'; font-weight: 300; border: none;"
        )
        self._content_desc = QLabel("")
        self._content_desc.setStyleSheet(
            "color: rgb(113,113,122); font-size: 11px; font-family: 'Inter','Segoe UI'; border: none;"
        )
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_col.addWidget(self._content_title)
        title_col.addWidget(self._content_desc)
        ch_lay.addLayout(title_col)
        ch_lay.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(_BTN_GHOST)
        close_btn.clicked.connect(self.close)
        ch_lay.addWidget(close_btn)
        content_lay.addWidget(self._content_hdr)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent;")
        self._pages: dict[str, QWidget] = {}
        for cat in _categories_for_mode(APRILMode.TACTICAL):
            page = _build_page(cat["id"])
            self._pages[cat["id"]] = page
            self._stack.addWidget(page)
        content_lay.addWidget(self._stack, 1)

        root.addWidget(content_wrap, 1)

        self._rebuild_cat_buttons()

    def _rebuild_cat_buttons(self):
        while self._cat_layout.count() > 1:
            item = self._cat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        query = self._search.text().lower()
        self._cat_buttons: dict[str, QPushButton] = {}

        for cat in self._categories:
            if query and query not in cat["label"].lower():
                continue
            btn = QPushButton(cat["label"])
            btn.setCheckable(True)
            btn.setFixedHeight(32)
            btn.setStyleSheet(_CAT_BTN_STYLE)
            btn.clicked.connect(lambda _, cid=cat["id"]: self._select(cid))
            self._cat_buttons[cat["id"]] = btn
            self._cat_layout.insertWidget(self._cat_layout.count() - 1, btn)

    def _select(self, cat_id: str):
        self._active = cat_id
        for cid, btn in self._cat_buttons.items():
            btn.setChecked(cid == cat_id)
            btn.setStyleSheet(_CAT_BTN_ACTIVE if cid == cat_id else _CAT_BTN_STYLE)

        cat = next((c for c in self._categories if c["id"] == cat_id), None)
        if cat:
            self._content_title.setText(cat["label"])
            self._content_desc.setText(cat["desc"])

        if cat_id in self._pages:
            self._stack.setCurrentWidget(self._pages[cat_id])

    def _filter_categories(self):
        self._rebuild_cat_buttons()
        # FIX-08: guard _active being None before first _select()
        if self._active and self._active in self._cat_buttons:
            self._select(self._active)
        elif self._cat_buttons:
            self._select(next(iter(self._cat_buttons)))

    # ------------------------------------------------------------------ painting

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 20, 20)

        p.setClipPath(path)
        p.fillRect(0, 0, self.width(), self.height(), QColor(10, 10, 18, 222))

        grad = QLinearGradient(0, 0, 0, 100)
        grad.setColorAt(0, QColor(255, 255, 255, 12))
        grad.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(0, 0, self.width(), 100, grad)

        p.setClipping(False)
        pen = QPen(QColor(255, 255, 255, 28))
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.end()

    # ------------------------------------------------------------------ keyboard

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------------------ slots

    def _on_mode_changed(self, mode: APRILMode):
        self._categories = _categories_for_mode(mode)
        self._mode_lbl.setText(mode.name.capitalize() + " mode")
        self._rebuild_cat_buttons()
        if self._cat_buttons:
            first = next(iter(self._cat_buttons))
            self._select(first)


# ------------------------------------------------------------------ page builders


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
    w = QWidget()
    w.setStyleSheet("background: transparent;")
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setStyleSheet("background: transparent;")
    inner = fn()
    inner.setStyleSheet("background: transparent;")
    scroll.setWidget(inner)
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(scroll)
    return w


def _page_general() -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(28, 20, 28, 20)
    lay.setSpacing(20)
    lay.addWidget(_section("Presence"))
    lay.addWidget(_toggle("Start on login", True))
    lay.addWidget(_toggle("Show in taskbar", False))
    lay.addWidget(_combo_row("Default mode", ["Ambient", "Focus", "Tactical"]))
    lay.addWidget(_combo_row("Presence profile", ["Minimal", "Balanced", "Immersive"]))
    lay.addWidget(_section("Invocation"))
    lay.addWidget(_text_row("Wake phrase", "Hey April"))
    lay.addWidget(_toggle("Push-to-talk fallback", True))
    lay.addWidget(_slider_row("Trigger sensitivity", 70))
    lay.addStretch()
    return w


def _page_voice() -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(28, 20, 28, 20)
    lay.setSpacing(20)
    lay.addWidget(_section("Speech Recognition"))
    lay.addWidget(_combo_row("Engine", ["Whisper (local)", "Azure STT", "Google STT"]))
    lay.addWidget(_slider_row("Silence threshold (ms)", 600))
    lay.addWidget(_toggle("Show live transcription", True))
    lay.addWidget(_section("Text-to-Speech"))
    lay.addWidget(_combo_row("Voice", ["af_alloy", "af_bella", "am_adam"]))
    lay.addWidget(_slider_row("Speed", 100))
    lay.addWidget(_slider_row("Volume", 80))
    lay.addWidget(_section("Audio"))
    lay.addWidget(_combo_row("Input device", ["Default microphone"]))
    lay.addWidget(_toggle("Noise suppression", True))
    lay.addStretch()
    return w


def _page_intelligence() -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(28, 20, 28, 20)
    lay.setSpacing(20)
    lay.addWidget(_section("Model"))
    lay.addWidget(
        _combo_row(
            "Primary model",
            ["cloud-gemini-flash", "cloud-deepseek-v3", "local-qwen-7b"],
        )
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
    lay.setSpacing(20)
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
    lay.setSpacing(20)
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
    lay.setSpacing(20)
    lay.addWidget(_section("Interruption Handling"))
    lay.addWidget(
        _combo_row(
            "On new critical notification", ["Pause and notify", "Queue", "Ignore"]
        )
    )
    lay.addWidget(_toggle("Allow mid-sentence interruption", True))
    lay.addWidget(_section("Idle Behavior"))
    lay.addWidget(
        _combo_row("After 5 min idle", ["Stay ambient", "Collapse to minimal", "Sleep"])
    )
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
    lay.setSpacing(20)
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
    lay.setSpacing(20)
    lay.addWidget(_section("Runtime"))
    lay.addWidget(_info_row("APRIL version", "0.1.0-alpha"))
    lay.addWidget(_info_row("Python", "3.12"))
    lay.addWidget(_info_row("PyQt6", "6.7"))
    lay.addWidget(_toggle("Hardware acceleration", True))
    lay.addWidget(_toggle("Experimental features", False))
    lay.addWidget(_section("Danger Zone"))
    danger_btn = QPushButton("Factory Reset…")
    danger_btn.setFixedHeight(32)
    danger_btn.setStyleSheet("""
        QPushButton { background: rgba(239,68,68,20); color: rgb(239,68,68);
                      border: 1px solid rgba(239,68,68,60); border-radius: 6px;
                      font-size: 11px; font-family: 'Inter','Segoe UI'; }
        QPushButton:hover { background: rgba(239,68,68,40); }
    """)
    lay.addWidget(danger_btn)
    lay.addStretch()
    return w


def _page_placeholder() -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl = QLabel("Coming soon")
    lbl.setStyleSheet("color: rgb(113,113,122); font-size: 13px;")
    lay.addWidget(lbl)
    return w


# ------------------------------------------------------------------ setting rows


def _section(title: str) -> QLabel:
    lbl = QLabel(title.upper())
    lbl.setStyleSheet(
        "color: rgb(113,113,122); font-size: 9px; letter-spacing: 1.5px; "
        "font-family: 'JetBrains Mono', Consolas; padding-top: 4px;"
    )
    return lbl


def _toggle(label: str, default: bool) -> QWidget:
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lbl = QLabel(label)
    lbl.setStyleSheet(
        "color: rgb(200,220,240); font-size: 12px; font-family: 'Inter','Segoe UI';"
    )
    lay.addWidget(lbl)
    lay.addStretch()
    cb = QCheckBox()
    cb.setChecked(default)
    cb.setStyleSheet("""
        QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px;
                               border: 1px solid rgba(255,255,255,30); background: rgba(255,255,255,8); }
        QCheckBox::indicator:checked { background: rgb(34,211,238); border-color: rgb(34,211,238); }
    """)
    lay.addWidget(cb)
    return row


def _combo_row(label: str, options: list[str]) -> QWidget:
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lbl = QLabel(label)
    lbl.setStyleSheet(
        "color: rgb(200,220,240); font-size: 12px; font-family: 'Inter','Segoe UI';"
    )
    lay.addWidget(lbl)
    lay.addStretch()
    cb = QComboBox()
    cb.addItems(options)
    cb.setFixedWidth(180)
    cb.setFixedHeight(28)
    cb.setStyleSheet(_COMBO_STYLE)
    lay.addWidget(cb)
    return row


def _slider_row(label: str, default: int) -> QWidget:
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lbl = QLabel(label)
    lbl.setStyleSheet(
        "color: rgb(200,220,240); font-size: 12px; font-family: 'Inter','Segoe UI';"
    )
    lay.addWidget(lbl)
    lay.addStretch()
    val_lbl = QLabel(str(default))
    val_lbl.setFixedWidth(32)
    val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    val_lbl.setStyleSheet(
        "color: rgb(34,211,238); font-size: 11px; font-family: 'JetBrains Mono',Consolas;"
    )
    sl = QSlider(Qt.Orientation.Horizontal)
    sl.setRange(0, 100)
    sl.setValue(default)
    sl.setFixedWidth(140)
    sl.setStyleSheet(_SLIDER_STYLE)
    sl.valueChanged.connect(lambda v: val_lbl.setText(str(v)))
    lay.addWidget(val_lbl)
    lay.addWidget(sl)
    return row


def _text_row(label: str, value: str) -> QWidget:
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lbl = QLabel(label)
    lbl.setStyleSheet(
        "color: rgb(200,220,240); font-size: 12px; font-family: 'Inter','Segoe UI';"
    )
    lay.addWidget(lbl)
    lay.addStretch()
    inp = QLineEdit(value)
    inp.setFixedWidth(200)
    inp.setFixedHeight(28)
    inp.setStyleSheet(_INPUT_STYLE)
    lay.addWidget(inp)
    return row


def _info_row(label: str, value: str) -> QWidget:
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lbl = QLabel(label)
    lbl.setStyleSheet(
        "color: rgb(200,220,240); font-size: 12px; font-family: 'Inter','Segoe UI';"
    )
    lay.addWidget(lbl)
    lay.addStretch()
    val = QLabel(value)
    val.setStyleSheet(
        "color: rgb(113,113,122); font-size: 11px; font-family: 'JetBrains Mono',Consolas;"
    )
    lay.addWidget(val)
    return row


# ------------------------------------------------------------------ style constants

_INPUT_STYLE = """
QLineEdit {
    background: rgba(255,255,255,8);
    border: 1px solid rgba(255,255,255,20);
    border-radius: 6px;
    color: rgb(220,240,255);
    font-size: 11px;
    font-family: 'Inter','Segoe UI';
    padding: 0 8px;
    height: 28px;
}
QLineEdit:focus { border-color: rgba(34,211,238,80); }
"""

_COMBO_STYLE = """
QComboBox {
    background: rgba(255,255,255,8);
    border: 1px solid rgba(255,255,255,20);
    border-radius: 6px;
    color: rgb(220,240,255);
    font-size: 11px;
    font-family: 'Inter','Segoe UI';
    padding: 0 8px;
}
QComboBox:focus { border-color: rgba(34,211,238,80); }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView {
    background: rgb(18,18,28);
    border: 1px solid rgba(255,255,255,20);
    color: rgb(220,240,255);
    selection-background-color: rgba(34,211,238,40);
}
"""

_SLIDER_STYLE = """
QSlider::groove:horizontal {
    height: 4px;
    background: rgba(255,255,255,15);
    border-radius: 2px;
}
QSlider::handle:horizontal {
    width: 12px; height: 12px;
    margin: -4px 0;
    border-radius: 6px;
    background: rgb(34,211,238);
}
QSlider::sub-page:horizontal {
    background: rgba(34,211,238,120);
    border-radius: 2px;
}
"""

_CAT_BTN_STYLE = """
QPushButton {
    background: transparent;
    color: rgb(113,113,122);
    border: none;
    border-radius: 6px;
    font-size: 12px;
    font-family: 'Inter','Segoe UI';
    text-align: left;
    padding: 0 10px;
}
QPushButton:hover { background: rgba(255,255,255,8); color: rgb(200,220,240); }
"""

_CAT_BTN_ACTIVE = """
QPushButton {
    background: rgba(34,211,238,25);
    color: rgb(34,211,238);
    border: none;
    border-radius: 6px;
    font-size: 12px;
    font-family: 'Inter','Segoe UI';
    text-align: left;
    padding: 0 10px;
}
"""

_BTN_GHOST = """
QPushButton {
    background: rgba(255,255,255,8);
    color: rgb(180,200,220);
    border: 1px solid rgba(255,255,255,20);
    border-radius: 6px;
    font-size: 11px;
}
QPushButton:hover { background: rgba(255,255,255,15); }
"""

_BTN_WARN = """
QPushButton {
    background: transparent;
    color: rgb(113,113,122);
    border: none;
    font-size: 11px;
    font-family: 'Inter','Segoe UI';
    text-align: left;
}
QPushButton:hover { color: rgb(251,191,36); }
"""
