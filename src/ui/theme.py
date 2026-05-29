"""
ui/theme.py — APRIL design system.

Single source of truth for every colour, dimension, timing, and typography
token used across the APRIL surface system.  Supports Windows system
Light / Dark mode detection via registry query and refreshes dynamically.
"""

try:
    import winreg
except ImportError:
    winreg = None

from PyQt6.QtGui import QColor, QFont, QIcon
from PyQt6.QtCore import QSize

# ── Static accent / semantic colours (never change with theme) ─────────────

# Cyan — primary brand accent
CYAN = QColor(56, 189, 248)  # sky-400
CYAN_80 = QColor(56, 189, 248, 200)
CYAN_40 = QColor(56, 189, 248, 100)
CYAN_20 = QColor(56, 189, 248, 50)

# Amber — warning
AMBER = QColor(251, 191, 36)
AMBER_80 = QColor(251, 191, 36, 200)

# Red — error
RED = QColor(239, 68, 68)
RED_80 = QColor(239, 68, 68, 200)

# Emerald — dormant status dot
EMERALD = QColor(52, 211, 153)  # emerald-400

# Purple — acting/task state accent
VIOLET = QColor(167, 139, 250)  # violet-400

# ── Dynamic theme tokens (updated by refresh_theme()) ──────────────────────

# Backgrounds
BG_BASE = QColor(18, 18, 28, 210)  # main panel background
BG_SURFACE = QColor(255, 255, 255, 10)  # slightly elevated surface
BG_ELEVATED = QColor(255, 255, 255, 18)  # cards, inputs
BG_HOVER = QColor(255, 255, 255, 14)  # hover highlight

# Borders
BORDER = QColor(255, 255, 255, 28)
BORDER_DIM = QColor(255, 255, 255, 14)
BORDER_FOCUS = QColor(56, 189, 248, 140)

# Text
TEXT_PRIMARY = QColor(228, 235, 250)
TEXT_SECONDARY = QColor(148, 163, 184)  # slate-400
TEXT_MUTED = QColor(100, 116, 139)  # slate-500
TEXT_ACCENT = QColor(56, 189, 248)  # cyan
TEXT_CYAN = QColor(125, 211, 252)  # sky-300 (lighter for dark bg)

# ── Layout constants ────────────────────────────────────────────────────────

ORB_SIZE = 48
CORNER_MARGIN = 32
OVERLAY_WIDTH = 340
WORKSPACE_W = 740
WORKSPACE_H = 540
SETTINGS_W = 880
SETTINGS_H = 580

# ── Timing ──────────────────────────────────────────────────────────────────

TRANSITION_FAST = 120
TRANSITION_NORMAL = 220
ANIMATION_INTERVAL = 16  # ~60 fps


# ── System theme detection ──────────────────────────────────────────────────


def is_light_theme() -> bool:
    """Return True when Windows 'Apps use light theme' registry key is set."""
    if winreg is None:
        return False
    try:
        registry = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
        key = winreg.OpenKey(
            registry,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return value == 1
    except Exception:
        return False


def refresh_theme() -> None:
    """Update all dynamic colour tokens to match the current system theme."""
    global BG_BASE, BG_SURFACE, BG_ELEVATED, BG_HOVER
    global BORDER, BORDER_DIM, BORDER_FOCUS
    global TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, TEXT_ACCENT, TEXT_CYAN
    if is_light_theme():
        # ── Fluent Light — mica-white acrylic ───────────────────────────────
        BG_BASE = QColor(248, 249, 252, 215)
        BG_SURFACE = QColor(0, 0, 0, 8)
        BG_ELEVATED = QColor(0, 0, 0, 14)
        BG_HOVER = QColor(0, 0, 0, 7)

        BORDER = QColor(0, 0, 0, 36)
        BORDER_DIM = QColor(0, 0, 0, 18)
        BORDER_FOCUS = QColor(8, 145, 178, 140)

        TEXT_PRIMARY = QColor(15, 23, 42)  # slate-900
        TEXT_SECONDARY = QColor(71, 85, 105)  # slate-600
        TEXT_MUTED = QColor(148, 163, 184)  # slate-400
        TEXT_ACCENT = QColor(8, 145, 178)  # cyan-600
        TEXT_CYAN = QColor(6, 109, 138)  # deeper cyan for light bg
    else:
        # ── Fluent Dark — near-black acrylic ────────────────────────────────
        BG_BASE = QColor(14, 17, 27, 215)
        BG_SURFACE = QColor(255, 255, 255, 10)
        BG_ELEVATED = QColor(255, 255, 255, 18)
        BG_HOVER = QColor(255, 255, 255, 14)

        BORDER = QColor(255, 255, 255, 28)
        BORDER_DIM = QColor(255, 255, 255, 14)
        BORDER_FOCUS = QColor(56, 189, 248, 140)

        TEXT_PRIMARY = QColor(228, 235, 250)
        TEXT_SECONDARY = QColor(148, 163, 184)
        TEXT_MUTED = QColor(100, 116, 139)
        TEXT_ACCENT = QColor(56, 189, 248)
        TEXT_CYAN = QColor(125, 211, 252)


# Initialise on import
refresh_theme()


# ── Typography ──────────────────────────────────────────────────────────────


def ui_font(size: int = 11) -> QFont:
    """Segoe UI Variable Display — the Windows 11 system UI font."""
    f = QFont("Segoe UI Variable Display")
    f.setFamilies(["Segoe UI Variable Display", "Segoe UI", "Inter", "sans-serif"])
    f.setPointSize(size)
    return f


def mono_font(size: int = 10) -> QFont:
    """Cascadia Code → Segoe UI Mono → Consolas for code and labels."""
    f = QFont("Cascadia Code")
    f.setFamilies(["Cascadia Code", "Segoe UI Mono", "Consolas", "monospace"])
    f.setPointSize(size)
    return f


def label_font(size: int = 9) -> QFont:
    """Small all-caps label font."""
    f = ui_font(size)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)
    return f


# ── Icon helpers ────────────────────────────────────────────────────────────


def _icon_color() -> str:
    """CSS color string for icons that adapts to the active theme."""
    return (
        "rgb(71,85,105)"  # slate-600 on light
        if is_light_theme()
        else "rgb(148,163,184)"  # slate-400 on dark
    )


def _accent_color() -> str:
    return "rgb(8,145,178)" if is_light_theme() else "rgb(56,189,248)"


def get_icon(name: str, color: str | None = None, size: int = 16) -> QIcon:
    """
    Return a QIcon from qtawesome (Font Awesome / Material Design icons).
    Falls back to an empty QIcon if qtawesome is not installed.

    Common names used in APRIL:
      fa6s.microphone   fa6s.brain          fa6s.volume_high
      fa6s.bolt         fa6s.triangle_exclamation  fa6s.circle_xmark
      fa6s.clock_rotate_left   fa6s.copy   fa6s.keyboard
      fa6s.gear         fa6s.xmark          fa6s.chevron_up
      fa6s.house        fa6s.network_wired  fa6s.chart_bar
      fa6s.list         fa6s.circle_dot     fa6s.arrow_up_right_from_square
    """
    try:
        import qtawesome as qta

        c = color or _icon_color()
        return qta.icon(name, color=c, scale_factor=1.0)
    except Exception:
        return QIcon()
