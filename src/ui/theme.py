"""
ui/theme.py — Premium Windows 11 Design System

Single source of truth for color tokens, typography, timing, and layout constants.
Supports Windows AppsUseLightTheme registry lookup.
"""

try:
    import winreg
except ImportError:
    winreg = None

from PyQt6.QtGui import QColor, QFont, QIcon
from PyQt6.QtCore import QSize

# ── Colors — Windows Accent Blue & Status Dot Accents ────────────────────────
WINDOWS_ACCENT = QColor(0, 120, 212)       # Windows 11 Accent Blue (#0078d4)
WINDOWS_ACCENT_HOVER = QColor(0, 99, 177)  # Slightly darker hover blue
EMERALD = QColor(34, 197, 94)              # iOS-style status dot (Dormant)
AMBER = QColor(245, 158, 11)               # Warning
RED = QColor(239, 68, 68)                  # Error
VIOLET = QColor(139, 92, 246)              # Acting

# Legacy aliases for UI compatibility across phases
CYAN = WINDOWS_ACCENT
CYAN_80 = QColor(0, 120, 212, 200)
CYAN_40 = QColor(0, 120, 212, 100)
CYAN_20 = QColor(0, 120, 212, 50)
AMBER_80 = QColor(245, 158, 11, 200)
RED_80 = QColor(239, 68, 68, 200)


# ── Dynamic Theme Tokens (updated via refresh_theme()) ───────────────────────
BG_BASE = QColor(32, 32, 32, 225)          # Windows 11 dark Mica base (slightly more opaque for heavy blur effect)
BG_SURFACE = QColor(255, 255, 255, 8)      # Elevated panels
BG_ELEVATED = QColor(255, 255, 255, 14)    # Card base
BG_HOVER = QColor(255, 255, 255, 10)       # Hover highlights

BORDER = QColor(255, 255, 255, 20)         # Crisp thin border
BORDER_DIM = QColor(255, 255, 255, 10)
BORDER_FOCUS = QColor(0, 120, 212, 160)    # Windows Blue focused border

TEXT_PRIMARY = QColor(243, 243, 243)       # High contrast off-white
TEXT_SECONDARY = QColor(161, 161, 170)     # Zinc 400
TEXT_MUTED = QColor(113, 113, 122)         # Zinc 500
TEXT_ACCENT = WINDOWS_ACCENT               # Accent text

# ── Layout Constants ─────────────────────────────────────────────────────────
ORB_SIZE = 48
CORNER_MARGIN = 32
COMPACT_WIDTH = 320
OVERLAY_WIDTH = 320
WORKSPACE_W = 740
WORKSPACE_H = 540
SETTINGS_W = 880
SETTINGS_H = 580


# ── Timing ───────────────────────────────────────────────────────────────────
TRANSITION_FAST = 120
TRANSITION_NORMAL = 220
ANIMATION_INTERVAL = 16  # ~60 fps


def is_light_theme() -> bool:
    """Return True if Windows 'Apps use light theme' registry key is enabled."""
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
    """Update dynamic theme tokens based on Windows light/dark mode."""
    global BG_BASE, BG_SURFACE, BG_ELEVATED, BG_HOVER
    global BORDER, BORDER_DIM, BORDER_FOCUS
    global TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, TEXT_ACCENT

    if is_light_theme():
        # ── Windows 11 Light Mode (Mica Light) ──────────────────────────────
        BG_BASE = QColor(243, 243, 243, 225)
        BG_SURFACE = QColor(0, 0, 0, 8)
        BG_ELEVATED = QColor(0, 0, 0, 12)
        BG_HOVER = QColor(0, 0, 0, 6)

        BORDER = QColor(0, 0, 0, 24)
        BORDER_DIM = QColor(0, 0, 0, 12)
        BORDER_FOCUS = QColor(0, 120, 212, 140)

        TEXT_PRIMARY = QColor(24, 24, 27)          # Zinc 900
        TEXT_SECONDARY = QColor(82, 82, 91)       # Zinc 600
        TEXT_MUTED = QColor(161, 161, 170)        # Zinc 400
        TEXT_ACCENT = QColor(0, 99, 177)           # Slightly darker accent blue
    else:
        # ── Windows 11 Dark Mode (Mica Dark) ────────────────────────────────
        BG_BASE = QColor(32, 32, 32, 225)
        BG_SURFACE = QColor(255, 255, 255, 8)
        BG_ELEVATED = QColor(255, 255, 255, 14)
        BG_HOVER = QColor(255, 255, 255, 10)

        BORDER = QColor(255, 255, 255, 20)
        BORDER_DIM = QColor(255, 255, 255, 10)
        BORDER_FOCUS = QColor(0, 120, 212, 160)

        TEXT_PRIMARY = QColor(243, 243, 243)
        TEXT_SECONDARY = QColor(161, 161, 170)
        TEXT_MUTED = QColor(113, 113, 122)
        TEXT_ACCENT = WINDOWS_ACCENT


# Initialize tokens
refresh_theme()


# ── Typography ───────────────────────────────────────────────────────────────

def ui_font(size: int = 11) -> QFont:
    """Segoe UI Variable variant selection based on size for Fluent Design alignment."""
    if size >= 20:
        family = "Segoe UI Variable Display"
    elif size >= 11:
        family = "Segoe UI Variable Text"
    else:
        family = "Segoe UI Variable Small"
    
    f = QFont(family)
    f.setFamilies([family, "Segoe UI", "Inter", "sans-serif"])
    f.setPointSize(size)
    return f


def mono_font(size: int = 10) -> QFont:
    """Cascadia Code/Segoe UI Mono for logs, status cards, and timestamps."""
    f = QFont("Segoe UI Mono")
    f.setFamilies(["Segoe UI Mono", "Cascadia Code", "Consolas", "monospace"])
    f.setPointSize(size)
    return f


def label_font(size: int = 9) -> QFont:
    """Uppercase wide-spaced label font."""
    f = ui_font(size)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)
    return f


# ── Elevation / Shadows ──────────────────────────────────────────────────────

def create_shadow(color: QColor = QColor(0, 0, 0, 45), radius: float = 12, dx: float = 0, dy: float = 4):
    """Factory function for modern soft drop shadows."""
    try:
        from PyQt6.QtWidgets import QGraphicsDropShadowEffect
        shadow = QGraphicsDropShadowEffect()
        shadow.setColor(color)
        shadow.setBlurRadius(radius)
        shadow.setOffset(dx, dy)
        return shadow
    except Exception:
        return None



# ── Icon System (qtawesome integration) ──────────────────────────────────────

def _icon_color() -> str:
    """Adapts default icon color to theme contrast."""
    return "rgb(82, 82, 91)" if is_light_theme() else "rgb(161, 161, 170)"


def get_icon(name: str, color: str | None = None, size: int = 16) -> QIcon:
    """
    Load a vector icon from qtawesome (Font Awesome 6 Solid).
    Gracefully falls back to empty QIcon if dependencies fail.
    """
    try:
        import qtawesome as qta
        c = color or _icon_color()
        return qta.icon(name, color=c, scale_factor=1.0)
    except Exception:
        return QIcon()
