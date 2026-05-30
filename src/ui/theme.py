"""
ui/theme.py — Premium Windows 11 Design System

Single source of truth for color tokens, typography, timing, and layout constants.
Supports Windows AppsUseLightTheme registry lookup and DWM AccentColor auto-calibration.
"""

try:
    import winreg
except ImportError:
    winreg = None

import os
import json
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPainterPath, QLinearGradient, QBrush
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QFrame

THEME_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json"
)

# ── Dynamic Theme Controls (Saved to/Loaded from config.json) ────────────────
ACCENT_REGISTRY_SYNC = True
ACCENT_PRESET = "champagne"
ACCENT_CUSTOM_HEX = "#c9a96e"
MICA_OPACITY = 95
MICA_BLUR_RADIUS = 60

# Preset accents (Curated designer color palettes for maximum premium aesthetic)
PRESETS = {
    "champagne": QColor(201, 169, 110),       # Muted Champagne Gold (#c9a96e)
    "sapphire": QColor(79, 109, 122),         # Steel Sapphire Blue (#4f6d7a)
    "sage": QColor(127, 154, 130),            # Soft Sage Green (#7f9a82)
    "blush": QColor(212, 163, 115),           # Muted Blush Peach (#d4a373)
    "lavender": QColor(138, 123, 167),        # Deep Lavender Violet (#8a7ba7)
    "silver": QColor(181, 181, 186),          # Premium Platinum Silver (#b5b5ba)
}

def load_theme_config() -> None:
    """Load theme configuration from config.json if available."""
    global ACCENT_REGISTRY_SYNC, ACCENT_PRESET, ACCENT_CUSTOM_HEX, MICA_OPACITY, MICA_BLUR_RADIUS, LAST_ACTIVE_PAGE
    if os.path.exists(THEME_CONFIG_PATH):
        try:
            with open(THEME_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                ACCENT_REGISTRY_SYNC = data.get("accent_registry_sync", True)
                ACCENT_PRESET = data.get("accent_preset", "champagne")
                ACCENT_CUSTOM_HEX = data.get("accent_custom_hex", "#c9a96e")
                MICA_OPACITY = data.get("mica_opacity", 95)
                MICA_BLUR_RADIUS = data.get("mica_blur_radius", 60)
                LAST_ACTIVE_PAGE = data.get("last_active_page", "Home")
        except Exception:
            pass

def save_theme_config() -> None:
    """Save theme configuration to config.json."""
    data = {}
    if os.path.exists(THEME_CONFIG_PATH):
        try:
            with open(THEME_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
    data.update({
        "accent_registry_sync": ACCENT_REGISTRY_SYNC,
        "accent_preset": ACCENT_PRESET,
        "accent_custom_hex": ACCENT_CUSTOM_HEX,
        "mica_opacity": MICA_OPACITY,
        "mica_blur_radius": MICA_BLUR_RADIUS,
        "last_active_page": LAST_ACTIVE_PAGE
    })
    try:
        with open(THEME_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def get_dwm_accent_color() -> QColor | None:
    """Read Windows AccentColor from registry (HKCU\\Software\\Microsoft\\Windows\\DWM)."""
    if winreg is None:
        return None
    try:
        registry = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
        key = winreg.OpenKey(
            registry,
            r"Software\Microsoft\Windows\DWM",
        )
        val, _ = winreg.QueryValueEx(key, "AccentColor")
        # val is a DWORD containing 0xAABBGGRR (ABGR format)
        b = (val >> 16) & 0xff
        g = (val >> 8) & 0xff
        r = val & 0xff
        return QColor(r, g, b)
    except Exception:
        return None

# ── Dynamic Theme Tokens (updated via refresh_theme()) ───────────────────────
WINDOWS_ACCENT = QColor(201, 169, 110)
WINDOWS_ACCENT_HOVER = QColor(176, 144, 85)
EMERALD = QColor(34, 197, 94)
AMBER = QColor(245, 158, 11)
RED = QColor(239, 68, 68)
VIOLET = QColor(139, 92, 246)

# Legacy aliases for UI compatibility across phases
CYAN = WINDOWS_ACCENT
CYAN_80 = QColor(201, 169, 110, 200)
CYAN_40 = QColor(201, 169, 110, 100)
CYAN_20 = QColor(201, 169, 110, 50)
AMBER_80 = QColor(245, 158, 11, 200)
RED_80 = QColor(239, 68, 68, 200)

BG_BASE = QColor(32, 32, 32, 242)
BG_SURFACE = QColor(255, 255, 255, 8)
BG_ELEVATED = QColor(255, 255, 255, 14)
BG_HOVER = QColor(255, 255, 255, 10)

BORDER = QColor(255, 255, 255, 20)
BORDER_DIM = QColor(255, 255, 255, 10)
BORDER_FOCUS = QColor(201, 169, 110, 160)

TEXT_PRIMARY = QColor(243, 243, 243)
TEXT_SECONDARY = QColor(161, 161, 170)
TEXT_MUTED = QColor(113, 113, 122)
TEXT_ACCENT = WINDOWS_ACCENT


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
    """Update dynamic theme tokens based on configuration and system settings."""
    global BG_BASE, BG_SURFACE, BG_ELEVATED, BG_HOVER
    global BORDER, BORDER_DIM, BORDER_FOCUS
    global TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, TEXT_ACCENT
    global WINDOWS_ACCENT, WINDOWS_ACCENT_HOVER, CYAN, CYAN_80, CYAN_40, CYAN_20

    load_theme_config()

    # Determine dynamic accent
    accent = None
    if ACCENT_REGISTRY_SYNC:
        accent = get_dwm_accent_color()
    
    if accent is None:
        if ACCENT_PRESET in PRESETS:
            accent = PRESETS[ACCENT_PRESET]
        else:
            accent = QColor(ACCENT_CUSTOM_HEX)
            if not accent.isValid():
                accent = PRESETS["champagne"]

    WINDOWS_ACCENT = accent
    
    # Calculate hover color (adjust brightness slightly)
    h, s, v, a = accent.getHsv()
    if v > 128:
        v = max(0, v - 25)
    else:
        v = min(255, v + 25)
    WINDOWS_ACCENT_HOVER = QColor.fromHsv(h, s, v, a)

    CYAN = WINDOWS_ACCENT
    CYAN_80 = QColor(accent.red(), accent.green(), accent.blue(), 200)
    CYAN_40 = QColor(accent.red(), accent.green(), accent.blue(), 100)
    CYAN_20 = QColor(accent.red(), accent.green(), accent.blue(), 50)

    alpha_val = int(MICA_OPACITY * 2.55)

    if is_light_theme():
        # ── Windows 11 Light Mode (Mica Light) ──────────────────────────────
        BG_BASE = QColor(243, 243, 243, alpha_val)
        BG_SURFACE = QColor(0, 0, 0, 8)
        BG_ELEVATED = QColor(0, 0, 0, 12)
        BG_HOVER = QColor(0, 0, 0, 6)

        BORDER = QColor(0, 0, 0, 24)
        BORDER_DIM = QColor(0, 0, 0, 12)
        BORDER_FOCUS = QColor(accent.red(), accent.green(), accent.blue(), 140)

        TEXT_PRIMARY = QColor(24, 24, 27)          # Zinc 900
        TEXT_SECONDARY = QColor(82, 82, 91)       # Zinc 600
        TEXT_MUTED = QColor(161, 161, 170)        # Zinc 400
        TEXT_ACCENT = WINDOWS_ACCENT_HOVER
    else:
        # ── Windows 11 Dark Mode (Mica Dark) ────────────────────────────────
        BG_BASE = QColor(32, 32, 32, alpha_val)
        BG_SURFACE = QColor(255, 255, 255, 8)
        BG_ELEVATED = QColor(255, 255, 255, 14)
        BG_HOVER = QColor(255, 255, 255, 10)

        BORDER = QColor(255, 255, 255, 20)
        BORDER_DIM = QColor(255, 255, 255, 10)
        BORDER_FOCUS = QColor(accent.red(), accent.green(), accent.blue(), 160)

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


class MicaFrame(QFrame):
    """
    Premium Fluent Design frame painting a dynamic Mica gradient,
    subtle noise texture, and elegant top-left highlight border.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = self.rect()
        w, h = rect.width(), rect.height()
        radius = 16
        
        is_light = is_light_theme()
        alpha = int(MICA_OPACITY * 2.55)
        
        # 1. Paint background linear gradient matching Windows 11 Mica
        grad = QLinearGradient(0, 0, 0, h)
        if is_light:
            grad.setColorAt(0.0, QColor(246, 246, 246, alpha))
            grad.setColorAt(1.0, QColor(238, 238, 238, alpha))
        else:
            grad.setColorAt(0.0, QColor(36, 36, 36, alpha))
            grad.setColorAt(1.0, QColor(24, 24, 24, alpha))
            
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), radius, radius)
        
        # 2. Add dynamic, organic, pseudo-random noise texture overlay to simulate real material roughness
        p.setPen(QColor(255, 255, 255, 4) if not is_light else QColor(0, 0, 0, 3))
        # Draw a beautiful, performant noise pattern using seed hash
        for x in range(3, w - 3, 2):
            h_val = (x * 37) & 0xfff
            for y in range(3, h - 3, 2):
                if ((h_val + y * 59) % 7) == 0:
                    p.drawPoint(x, y)
                    
        # 3. Dual-Tone highlight & shadow bevel outline
        # Draw top-left highlight border (semi-transparent light)
        tl_path = QPainterPath()
        tl_path.moveTo(radius, 1)
        tl_path.lineTo(w - radius, 1)
        tl_path.arcTo(w - radius * 2 - 1, 1, radius * 2, radius * 2, 90, -45)
        tl_path.moveTo(radius, 1)
        tl_path.arcTo(1, 1, radius * 2, radius * 2, 90, 90)
        tl_path.lineTo(1, h - radius)
        tl_path.arcTo(1, h - radius * 2 - 1, radius * 2, radius * 2, 180, 45)
        
        tl_pen = QPen()
        tl_pen.setWidthF(1.0)
        tl_grad = QLinearGradient(0, 0, w, h)
        if is_light:
            tl_grad.setColorAt(0.0, QColor(255, 255, 255, 180))
            tl_grad.setColorAt(0.4, QColor(255, 255, 255, 90))
            tl_grad.setColorAt(1.0, QColor(255, 255, 255, 10))
        else:
            tl_grad.setColorAt(0.0, QColor(255, 255, 255, 45))
            tl_grad.setColorAt(0.4, QColor(255, 255, 255, 15))
            tl_grad.setColorAt(1.0, QColor(255, 255, 255, 5))
        tl_pen.setBrush(tl_grad)
        p.setPen(tl_pen)
        p.drawPath(tl_path)
        
        # Draw bottom-right shadow border
        br_path = QPainterPath()
        br_path.moveTo(w - 1, radius)
        br_path.lineTo(w - 1, h - radius)
        br_path.arcTo(w - radius * 2 - 1, h - radius * 2 - 1, radius * 2, radius * 2, 0, -90)
        br_path.lineTo(radius, h - 1)
        
        br_pen = QPen()
        br_pen.setWidthF(1.0)
        br_grad = QLinearGradient(w, 0, 0, h)
        if is_light:
            br_grad.setColorAt(0.0, QColor(0, 0, 0, 45))
            br_grad.setColorAt(1.0, QColor(0, 0, 0, 15))
        else:
            br_grad.setColorAt(0.0, QColor(0, 0, 0, 140))
            br_grad.setColorAt(1.0, QColor(0, 0, 0, 60))
        br_pen.setBrush(br_grad)
        p.setPen(br_pen)
        p.drawPath(br_path)
        
        p.end()


def apply_fluent_effects(widget, use_acrylic: bool = False) -> None:
    """Apply native Windows 11 Mica/Acrylic background to a QWidget using Win32 DWM API."""
    import sys
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = int(widget.winId())
        dwmapi = ctypes.windll.dwmapi
        
        # 1. Enable Immersive Dark Mode on window title/borders if dark theme
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        dark_val = ctypes.c_int(0 if is_light_theme() else 1)
        dwmapi.DwmSetWindowAttribute(
            hwnd,
            20,
            ctypes.byref(dark_val),
            ctypes.sizeof(dark_val)
        )
        
        # 2. Set DWM Backdrop Type (Mica or Acrylic)
        # DWM_SYSTEMBACKDROP_TYPE = 38
        # DWMSBT_MAINWINDOW = 2 (Mica), DWMSBT_TRANSIENTWINDOW = 3 (Acrylic)
        backdrop_val = ctypes.c_int(3 if use_acrylic else 2)
        dwmapi.DwmSetWindowAttribute(
            hwnd,
            38,
            ctypes.byref(backdrop_val),
            ctypes.sizeof(backdrop_val)
        )
    except Exception as e:
        print(f"[Theme] Failed to apply Fluent DWM effects: {e}")
