"""
SettingsPanel — mirror of the React settings system.

8 categories with progressive disclosure based on mode.
Fluent Design aesthetic adapting dynamically to Light/Dark system themes.
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
        self._active = None
        self._categories = _categories_for_mode(core.mode)

        self._setup_window()
        self._build_ui()
        self._select(self._categories[0]["id"])

        core.mode_changed.connect(self._on_mode_changed)

    def showEvent(self, event):
        theme.refresh_theme()
        self._apply_theme()
        super().showEvent(event)

    # ------------------------------------------------------------------ window

    def _setup_window(self):
        self.setFixedSize(860, 560)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")
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
        self._rail = QWidget()
        self._rail.setFixedWidth(200)
        self._rail.setStyleSheet(
            "background: transparent; border-right: 1px solid rgba(255,255,255,15);"
        )
        rail_lay = QVBoxLayout(self._rail)
        rail_lay.setContentsMargins(0, 0, 0, 0)
        rail_lay.setSpacing(0)

        hdr = QWidget()
        hdr.setFixedHeight(64)
        hdr.setStyleSheet(
            "border-bottom: 1px solid rgba(255,255,255,15); background: transparent;"
        )
        hdr_lay = QVBoxLayout(hdr)
        hdr_lay.setContentsMargins(20, 14, 20, 14)
        hdr_lay.setSpacing(2)
        title = QLabel("Settings")
        title.setFont(theme.ui_font(12))
        title.setStyleSheet(
            "color: rgb(165,243,252); font-size: 14px; font-weight: 300; border: none; background: transparent;"
        )
        self._mode_lbl = QLabel(self._core.mode.name.capitalize() + " mode")
        self._mode_lbl.setFont(theme.mono_font(9))
        self._mode_lbl.setStyleSheet(
            "color: rgb(113,113,122); font-size: 10px; border: none; background: transparent;"
        )
        hdr_lay.addWidget(title)
        hdr_lay.addWidget(self._mode_lbl)
        rail_lay.addWidget(hdr)

        search_wrap = QWidget()
        search_wrap.setFixedHeight(52)
        search_wrap.setStyleSheet("background: transparent;")
        sw_lay = QVBoxLayout(search_wrap)
        sw_lay.setContentsMargins(12, 10, 12, 10)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search settings…")
        self._search.setStyleSheet(_input_style())
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
        footer.setStyleSheet("background: transparent;")
        ft_lay = QHBoxLayout(footer)
        ft_lay.setContentsMargins(12, 8, 12, 8)
        self._reset_btn = QPushButton("↺  Reset to Defaults")
        self._reset_btn.setStyleSheet(_btn_warn_style())
        self._reset_btn.setFixedHeight(28)
        ft_lay.addWidget(self._reset_btn)
        rail_lay.addWidget(footer)

        root.addWidget(self._rail)

        # ---- Right content area ----
        content_wrap = QWidget()
        content_lay = QVBoxLayout(content_wrap)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(0)

        self._content_hdr = QWidget()
        self._content_hdr.setFixedHeight(64)
        self._content_hdr.setStyleSheet("background: transparent;")
        ch_lay = QHBoxLayout(self._content_hdr)
        ch_lay.setContentsMargins(28, 14, 20, 14)
        self._content_title = QLabel("—")
        self._content_title.setStyleSheet(
            "color: rgb(165,243,252); font-size: 16px; font-family: 'Segoe UI Variable Display',sans-serif; font-weight: 300; border: none; background: transparent;"
        )
        self._content_desc = QLabel("")
        self._content_desc.setStyleSheet(
            "color: rgb(113,113,122); font-size: 11px; font-family: 'Segoe UI',sans-serif; border: none; background: transparent;"
        )
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_col.addWidget(self._content_title)
        title_col.addWidget(self._content_desc)
        ch_lay.addLayout(title_col)
        ch_lay.addStretch()

        self._close_btn = QPushButton("✕")
        self._close_btn.setFixedSize(28, 28)
        self._close_btn.clicked.connect(self.close)
        ch_lay.addWidget(self._close_btn)
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
        self._apply_theme()

    # ------------------------------------------------------------------ theme

    def _apply_theme(self):
        is_light = theme.is_light_theme()
        txt_color = "rgb(30,30,42)" if is_light else "rgb(220,240,255)"
        title_color = "rgb(8,145,178)" if is_light else "rgb(34,211,238)"
        muted_color = "rgb(115,115,125)" if is_light else "rgb(113,113,122)"

        # Left rail border
        border_css = f"background: transparent; border-right: 1px solid {'rgba(0,0,0,15)' if is_light else 'rgba(255,255,255,15)'};"
        self._rail.setStyleSheet(border_css)

        # Labels
        self._mode_lbl.setStyleSheet(
            f"color: {muted_color}; font-size: 10px; font-family: 'Segoe UI Mono',Consolas; border: none; background: transparent;"
        )
        self._content_title.setStyleSheet(
            f"color: {title_color}; font-size: 16px; font-family: 'Segoe UI Variable Display',sans-serif; font-weight: 300; border: none; background: transparent;"
        )
        self._content_desc.setStyleSheet(
            f"color: {muted_color}; font-size: 11px; font-family: 'Segoe UI',sans-serif; border: none; background: transparent;"
        )

        # Inputs and controls
        self._search.setStyleSheet(_input_style())
        self._reset_btn.setStyleSheet(_btn_warn_style())
        self._close_btn.setStyleSheet(_btn_ghost_style())

        # Children inputs style refresh
        for edit in self.findChildren(QLineEdit):
            if edit != self._search:
                edit.setStyleSheet(_input_style())
        for combo in self.findChildren(QComboBox):
            combo.setStyleSheet(_combo_style())
        for slider in self.findChildren(QSlider):
            slider.setStyleSheet(_slider_style())
        for cb in self.findChildren(QCheckBox):
            cb.setStyleSheet(_checkbox_style())
        for lbl in self.findChildren(QLabel):
            # Section headers
            if lbl.text().isupper() and len(lbl.text()) < 30:
                lbl.setStyleSheet(
                    f"color: {muted_color}; font-size: 9px; letter-spacing: 1.5px; font-family: 'Segoe UI Mono', Consolas; padding-top: 4px; background: transparent; border: none;"
                )
            elif (
                lbl.parentWidget()
                and type(lbl.parentWidget()).__name__ == "QWidget"
                and lbl.objectName() != "content_desc"
            ):
                # Standard setting row label
                lbl.setStyleSheet(
                    f"color: {txt_color}; font-size: 12px; font-family: 'Segoe UI', sans-serif; background: transparent; border: none;"
                )

        self._rebuild_cat_buttons()
        self.update()

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
            btn.clicked.connect(lambda _, cid=cat["id"]: self._select(cid))
            self._cat_buttons[cat["id"]] = btn
            self._cat_layout.insertWidget(self._cat_layout.count() - 1, btn)

        # Style new buttons
        for cid, btn in self._cat_buttons.items():
            btn.setStyleSheet(
                _cat_btn_active() if cid == self._active else _cat_btn_style()
            )

    def _select(self, cat_id: str):
        self._active = cat_id
        for cid, btn in self._cat_buttons.items():
            btn.setChecked(cid == cat_id)
            btn.setStyleSheet(_cat_btn_active() if cid == cat_id else _cat_btn_style())

        cat = next((c for c in self._categories if c["id"] == cat_id), None)
        if cat:
            self._content_title.setText(cat["label"])
            self._content_desc.setText(cat["desc"])

        if cat_id in self._pages:
            self._stack.setCurrentWidget(self._pages[cat_id])

    def _filter_categories(self):
        self._rebuild_cat_buttons()
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
        p.fillRect(0, 0, self.width(), self.height(), theme.BG_BASE)

        grad = QLinearGradient(0, 0, 0, 100)
        grad.setColorAt(
            0,
            (
                QColor(255, 255, 255, 12)
                if not theme.is_light_theme()
                else QColor(0, 0, 0, 8)
            ),
        )
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
                      font-size: 11px; font-family: 'Segoe UI',sans-serif; }
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
    return lbl


def _toggle(label: str, default: bool) -> QWidget:
    row = QWidget()
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
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lbl = QLabel(label)
    lay.addWidget(lbl)
    lay.addStretch()
    cb = QComboBox()
    cb.addItems(options)
    cb.setFixedWidth(180)
    cb.setFixedHeight(28)
    lay.addWidget(cb)
    return row


def _slider_row(label: str, default: int) -> QWidget:
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lbl = QLabel(label)
    lay.addWidget(lbl)
    lay.addStretch()
    val_lbl = QLabel(str(default))
    val_lbl.setFixedWidth(32)
    val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    val_lbl.setStyleSheet(
        "color: rgb(34,211,238); font-size: 11px; font-family: 'Segoe UI Mono',Consolas;"
    )
    sl = QSlider(Qt.Orientation.Horizontal)
    sl.setRange(0, 100)
    sl.setValue(default)
    sl.setFixedWidth(140)
    sl.valueChanged.connect(lambda v: val_lbl.setText(str(v)))
    lay.addWidget(val_lbl)
    lay.addWidget(sl)
    return row


def _text_row(label: str, value: str) -> QWidget:
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lbl = QLabel(label)
    lay.addWidget(lbl)
    lay.addStretch()
    inp = QLineEdit(value)
    inp.setFixedWidth(200)
    inp.setFixedHeight(28)
    lay.addWidget(inp)
    return row


def _info_row(label: str, value: str) -> QWidget:
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lbl = QLabel(label)
    lay.addWidget(lbl)
    lay.addStretch()
    val = QLabel(value)
    val.setStyleSheet(
        "color: rgb(113,113,122); font-size: 11px; font-family: 'Segoe UI Mono',Consolas; background: transparent; border: none;"
    )
    lay.addWidget(val)
    return row


# ------------------------------------------------------------------ style constants


def _input_style() -> str:
    is_light = theme.is_light_theme()
    bg = "rgba(0,0,0,8)" if is_light else "rgba(255,255,255,8)"
    border = (
        "1px solid rgba(0,0,0,20)" if is_light else "1px solid rgba(255,255,255,20)"
    )
    color = "rgb(30,30,42)" if is_light else "rgb(220,240,255)"
    focus = "rgba(8,145,178,80)" if is_light else "rgba(34,211,238,80)"
    return f"""
    QLineEdit {{
        background: {bg};
        border: {border};
        border-radius: 6px;
        color: {color};
        font-size: 11px;
        font-family: 'Segoe UI', sans-serif;
        padding: 0 8px;
        height: 28px;
    }}
    QLineEdit:focus {{ border-color: {focus}; }}
    """


def _combo_style() -> str:
    is_light = theme.is_light_theme()
    bg = "rgba(0,0,0,8)" if is_light else "rgba(255,255,255,8)"
    border = (
        "1px solid rgba(0,0,0,20)" if is_light else "1px solid rgba(255,255,255,20)"
    )
    color = "rgb(30,30,42)" if is_light else "rgb(220,240,255)"
    focus = "rgba(8,145,178,80)" if is_light else "rgba(34,211,238,80)"
    popup_bg = "rgb(240,240,245)" if is_light else "rgb(18,18,28)"
    popup_border = (
        "1px solid rgba(0,0,0,20)" if is_light else "1px solid rgba(255,255,255,20)"
    )
    popup_sel = "rgba(8,145,178,40)" if is_light else "rgba(34,211,238,40)"
    return f"""
    QComboBox {{
        background: {bg};
        border: {border};
        border-radius: 6px;
        color: {color};
        font-size: 11px;
        font-family: 'Segoe UI', sans-serif;
        padding: 0 8px;
    }}
    QComboBox:focus {{ border-color: {focus}; }}
    QComboBox::drop-down {{ border: none; width: 20px; }}
    QComboBox QAbstractItemView {{
        background: {popup_bg};
        border: {popup_border};
        color: {color};
        selection-background-color: {popup_sel};
    }}
    """


def _slider_style() -> str:
    is_light = theme.is_light_theme()
    groove = "rgba(0,0,0,15)" if is_light else "rgba(255,255,255,15)"
    handle = "rgb(8,145,178)" if is_light else "rgb(34,211,238)"
    subpage = "rgba(8,145,178,120)" if is_light else "rgba(34,211,238,120)"
    return f"""
    QSlider::groove:horizontal {{
        height: 4px;
        background: {groove};
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        width: 12px; height: 12px;
        margin: -4px 0;
        border-radius: 6px;
        background: {handle};
    }}
    QSlider::sub-page:horizontal {{
        background: {subpage};
        border-radius: 2px;
    }}
    """


def _checkbox_style() -> str:
    is_light = theme.is_light_theme()
    border = (
        "1px solid rgba(0,0,0,30)" if is_light else "1px solid rgba(255,255,255,30)"
    )
    bg = "rgba(0,0,0,8)" if is_light else "rgba(255,255,255,8)"
    checked = "rgb(8,145,178)" if is_light else "rgb(34,211,238)"
    return f"""
    QCheckBox::indicator {{
        width: 16px; height: 16px; border-radius: 4px;
        border: {border}; background: {bg};
    }}
    QCheckBox::indicator:checked {{ background: {checked}; border-color: {checked}; }}
    """


def _cat_btn_style() -> str:
    is_light = theme.is_light_theme()
    color = "rgb(115,115,125)" if is_light else "rgb(113,113,122)"
    hover_bg = "rgba(0,0,0,8)" if is_light else "rgba(255,255,255,8)"
    hover_color = "rgb(30,30,42)" if is_light else "rgb(200,220,240)"
    return f"""
    QPushButton {{
        background: transparent;
        color: {color};
        border: none;
        border-radius: 6px;
        font-size: 12px;
        font-family: 'Segoe UI Variable Display', 'Segoe UI';
        text-align: left;
        padding: 0 10px;
    }}
    QPushButton:hover {{ background: {hover_bg}; color: {hover_color}; }}
    """


def _cat_btn_active() -> str:
    is_light = theme.is_light_theme()
    bg = "rgba(8,145,178,25)" if is_light else "rgba(34,211,238,25)"
    color = "rgb(8,145,178)" if is_light else "rgb(34,211,238)"
    return f"""
    QPushButton {{
        background: {bg};
        color: {color};
        border: none;
        border-radius: 6px;
        font-size: 12px;
        font-family: 'Segoe UI Variable Display', 'Segoe UI';
        text-align: left;
        padding: 0 10px;
    }}
    """


def _btn_ghost_style() -> str:
    is_light = theme.is_light_theme()
    bg = "rgba(0,0,0,8)" if is_light else "rgba(255,255,255,8)"
    border = (
        "1px solid rgba(0,0,0,20)" if is_light else "1px solid rgba(255,255,255,20)"
    )
    color = "rgb(80,80,95)" if is_light else "rgb(180,200,220)"
    hover_bg = "rgba(0,0,0,15)" if is_light else "rgba(255,255,255,15)"
    return f"""
    QPushButton {{
        background: {bg};
        color: {color};
        border: {border};
        border-radius: 6px;
        font-size: 11px;
    }}
    QPushButton:hover {{ background: {hover_bg}; }}
    """


def _btn_warn_style() -> str:
    is_light = theme.is_light_theme()
    color = "rgb(115,115,125)" if is_light else "rgb(113,113,122)"
    return f"""
    QPushButton {{
        background: transparent;
        color: {color};
        border: none;
        font-size: 11px;
        font-family: 'Segoe UI', sans-serif;
        text-align: left;
    }}
    QPushButton:hover {{ color: rgb(251,191,36); }}
    """
