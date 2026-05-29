from PyQt6.QtGui import QColor, QFont

# Color tokens — mirror the React design system
CYAN = QColor(34, 211, 238)
CYAN_80 = QColor(34, 211, 238, 200)
CYAN_40 = QColor(34, 211, 238, 100)
CYAN_20 = QColor(34, 211, 238, 50)
AMBER = QColor(251, 191, 36)
AMBER_80 = QColor(251, 191, 36, 200)
RED = QColor(239, 68, 68)
RED_80 = QColor(239, 68, 68, 200)

BG_BASE = QColor(10, 10, 15, 230)
BG_SURFACE = QColor(255, 255, 255, 12)
BG_ELEVATED = QColor(255, 255, 255, 20)
BORDER = QColor(255, 255, 255, 25)
BORDER_DIM = QColor(255, 255, 255, 12)

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


def mono_font(size: int = 11) -> QFont:
    f = QFont("Consolas")
    f.setFamilies(["JetBrains Mono", "Consolas", "Courier New"])
    f.setPointSize(size)
    return f


def ui_font(size: int = 11) -> QFont:
    f = QFont("Segoe UI")
    f.setFamilies(["Inter", "Segoe UI"])
    f.setPointSize(size)
    return f
