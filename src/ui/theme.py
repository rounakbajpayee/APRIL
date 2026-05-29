try:
    import winreg
except ImportError:
    winreg = None

from PyQt6.QtGui import QColor, QFont

# Core Color tokens
CYAN = QColor(34, 211, 238)
CYAN_80 = QColor(34, 211, 238, 200)
CYAN_40 = QColor(34, 211, 238, 100)
CYAN_20 = QColor(34, 211, 238, 50)
AMBER = QColor(251, 191, 36)
AMBER_80 = QColor(251, 191, 36, 200)
RED = QColor(239, 68, 68)
RED_80 = QColor(239, 68, 68, 200)

# These will be updated dynamically via refresh_theme()
BG_BASE = QColor(10, 10, 15, 190)
BG_SURFACE = QColor(255, 255, 255, 12)
BG_ELEVATED = QColor(255, 255, 255, 20)
BORDER = QColor(255, 255, 255, 30)
BORDER_DIM = QColor(255, 255, 255, 15)

TEXT_PRIMARY = QColor(220, 240, 255)
TEXT_MUTED = QColor(113, 113, 122)
TEXT_CYAN = QColor(165, 243, 252)

# Layout
ORB_SIZE = 48
CORNER_MARGIN = 32
OVERLAY_WIDTH = 320
WORKSPACE_W = 720
WORKSPACE_H = 520

# Timing (ms)
TRANSITION_FAST = 150
TRANSITION_NORMAL = 250
ANIMATION_INTERVAL = 16  # ~60fps


def is_light_theme() -> bool:
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


def refresh_theme():
    global BG_BASE, BG_SURFACE, BG_ELEVATED, BORDER, BORDER_DIM, TEXT_PRIMARY, TEXT_MUTED, TEXT_CYAN
    if is_light_theme():
        # Fluent Light Mode: Acrylic white
        BG_BASE = QColor(245, 245, 250, 190)
        BG_SURFACE = QColor(0, 0, 0, 15)
        BG_ELEVATED = QColor(0, 0, 0, 25)
        BORDER = QColor(0, 0, 0, 40)
        BORDER_DIM = QColor(0, 0, 0, 20)
        TEXT_PRIMARY = QColor(30, 30, 42)
        TEXT_MUTED = QColor(115, 115, 125)
        TEXT_CYAN = QColor(8, 145, 178)
    else:
        # Fluent Dark Mode: Acrylic dark grey
        BG_BASE = QColor(15, 15, 23, 190)
        BG_SURFACE = QColor(255, 255, 255, 12)
        BG_ELEVATED = QColor(255, 255, 255, 20)
        BORDER = QColor(255, 255, 255, 30)
        BORDER_DIM = QColor(255, 255, 255, 15)
        TEXT_PRIMARY = QColor(220, 240, 255)
        TEXT_MUTED = QColor(113, 113, 122)
        TEXT_CYAN = QColor(165, 243, 252)


# Initialize colors
refresh_theme()


def mono_font(size: int = 11) -> QFont:
    f = QFont("Segoe UI Mono")
    f.setFamilies(["Segoe UI Mono", "Cascadia Code", "Consolas", "Courier New"])
    f.setPointSize(size)
    return f


def ui_font(size: int = 11) -> QFont:
    f = QFont("Segoe UI Variable Display")
    f.setFamilies(["Segoe UI Variable Display", "Segoe UI", "Inter"])
    f.setPointSize(size)
    return f
