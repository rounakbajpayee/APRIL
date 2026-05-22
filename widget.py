"""
widget.py - APRIL floating status widget implemented in PyQt6.

The public APRILWidget interface is preserved for the rest of the runtime,
but the internals are rebuilt around Qt signals, custom painting, and a
frameless translucent window so the widget can look and behave like a small
Jarvis-style HUD instead of a Tk canvas with Win32 shaping hacks.
"""

from __future__ import annotations

import json
import math
import os
import sys
import threading
from typing import Any
from datetime import datetime, timezone

from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    QObject,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QAction,
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QRadialGradient,
    QTextCursor,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from debug_log import read_recent_events
from state_engine import get_widget_snapshot_data, get_widget_snapshot_lines


STATES = {
    "idle": {"color": "#9aa0a6", "label": "APRIL"},
    "listening": {"color": "#47e38d", "label": "Listening"},
    "thinking": {"color": "#f7b84b", "label": "Thinking"},
    "speaking": {"color": "#61a8ff", "label": "Speaking"},
    "error": {"color": "#ff5a67", "label": "Error"},
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
HISTORY_PATH = os.path.join(BASE_DIR, "logs", "ui_history.json")
TRACE_PATH = os.path.join(BASE_DIR, "logs", "startup_trace.log")

MAX_HISTORY_ITEMS = 40
RECENT_DEBUG_EVENTS = 10
RECENT_SNAPSHOT_LINES = 8

PAD_X = 18
PAD_Y = 11
RADIUS = 30
MIN_WIDTH = 188
MAX_WIDTH = 420
MESSAGE_WRAP_WIDTH = 360
ICON_SIZE = 24
NODE_MAX_WIDTH = 92
ANCHOR_FROM_BOTTOM = 50
AUTO_COLLAPSE_MS = 7000
MESSAGE_HOLD_MS = 9000
COLLAPSED_SIZE = 46
PANEL_WIDTH = 560
PANEL_HEIGHT = 640
PANEL_MIN_WIDTH = 500
PANEL_MIN_HEIGHT = 560
HEADER_HEIGHT = 86
PANEL_MARGIN = 14
PANEL_INSET = 16

BG = QColor("#070a0f")
BORDER = QColor("#1d2d3b")
HIGHLIGHT = QColor(255, 255, 255, 20)
TEXT = QColor("#f4f7fb")
MUTED = QColor("#8d9cac")
PANEL_BG = QColor("#09111a")
PANEL_BORDER = QColor("#235171")
PANEL_GLOW = QColor("#39b6ff")
PANEL_AMBER = QColor("#f4b55f")
CARD_BG = QColor("#0d1620")
CARD_BORDER = QColor("#224258")
CARD_LABEL = QColor("#71afd6")
CARD_VALUE = QColor("#edf5ff")
TIMELINE_BG = QColor("#081018")
FIELD_BG = QColor("#0b1520")
FIELD_BORDER = QColor("#224258")
INPUT_FOCUS = QColor("#39b6ff")
WINDOW_BG = "#060a0f"
HUD_FONT = "Bahnschrift"
BODY_FONT = "Segoe UI"
MONO_FONT = "Consolas"


def trace_startup(message: str) -> None:
    os.makedirs(os.path.dirname(TRACE_PATH), exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    with open(TRACE_PATH, "a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} [widget] {message}\n")


class _QtBridge(QObject):
    state_signal = pyqtSignal(str, str, str)
    output_signal = pyqtSignal(str, str)
    config_signal = pyqtSignal(dict)
    refresh_signal = pyqtSignal()
    destroy_signal = pyqtSignal()
    config_refresh_signal = pyqtSignal(dict)
    panel_submit_signal = pyqtSignal(str)
    quit_signal = pyqtSignal()


def _color(hex_value: str, alpha: int | None = None) -> QColor:
    color = QColor(hex_value)
    if alpha is not None:
        color.setAlpha(alpha)
    return color


class TimelineFeed(QTextEdit):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet(
            """
            QTextEdit {
                background: #081018;
                color: #f4f7fb;
                border: 1px solid #24445b;
                border-radius: 16px;
                padding: 10px;
                selection-background-color: #1f4966;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 10px;
                margin: 8px 2px 8px 0;
            }
            QScrollBar::handle:vertical {
                background: #28506b;
                border-radius: 5px;
                min-height: 28px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            """
        )

    def append_entry(self, role: str, text: str) -> None:
        clean = " ".join(str(text).strip().split())
        if not clean:
            return
        color = {
            "user": "#dce8f7",
            "assistant": "#f4f6f8",
            "system": "#5a6a7a",
        }.get(role, "#f4f6f8")
        label = {
            "user": "YOU",
            "assistant": "APRIL",
            "system": "SYSTEM",
        }.get(role, "APRIL")
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        safe_text = (
            clean.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        cursor.insertHtml(
            f"<div style='margin-top:6px;'>"
            f"<span style='color:#6e8dad;font-size:10px;font-weight:700;letter-spacing:1px;'>{label}</span><br>"
            f"<span style='color:{color};font-size:13px;'>{safe_text}</span>"
            f"</div>"
        )
        cursor.insertBlock()
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def set_entries(self, history: list[tuple[str, str]]) -> None:
        self.clear()
        for role, text in history:
            self.append_entry(role, text)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.viewport().rect().adjusted(1, 1, -1, -1)
        if rect.width() <= 0 or rect.height() <= 0:
            return

        scan_pen = QPen(QColor(57, 182, 255, 16), 1)
        painter.setPen(scan_pen)
        for y in range(rect.top() + 6, rect.bottom(), 8):
            painter.drawLine(rect.left() + 10, y, rect.right() - 10, y)

        accent_pen = QPen(QColor(244, 181, 95, 76), 1.2)
        painter.setPen(accent_pen)
        painter.drawLine(rect.left() + 12, rect.top() + 10, rect.left() + 54, rect.top() + 10)
        painter.drawLine(rect.right() - 54, rect.bottom() - 10, rect.right() - 12, rect.bottom() - 10)


class SummaryCard(QWidget):
    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._title = title
        self._value = "--"
        self.setMinimumHeight(64)

    def set_value(self, value: str) -> None:
        self._value = " ".join(str(value or "--").split()) or "--"
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), 14, 14)

        gradient = QLinearGradient(QPointF(rect.topLeft()), QPointF(rect.bottomLeft()))
        gradient.setColorAt(0.0, QColor("#0f1a25"))
        gradient.setColorAt(0.6, QColor("#0c141d"))
        gradient.setColorAt(1.0, QColor("#081018"))
        painter.fillPath(path, gradient)
        painter.setPen(QPen(CARD_BORDER, 1.2))
        painter.drawPath(path)

        painter.setPen(QPen(QColor(57, 182, 255, 82), 1.4))
        painter.drawLine(rect.left() + 12, rect.top() + 10, rect.left() + 54, rect.top() + 10)
        painter.setPen(QPen(QColor(244, 181, 95, 64), 1.0))
        painter.drawLine(rect.right() - 46, rect.bottom() - 10, rect.right() - 12, rect.bottom() - 10)

        painter.setPen(CARD_LABEL)
        painter.setFont(QFont(MONO_FONT, 8, QFont.Weight.Bold))
        painter.drawText(rect.adjusted(12, 10, -12, -12), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, self._title)

        painter.setPen(CARD_VALUE)
        painter.setFont(QFont(HUD_FONT, 9, QFont.Weight.DemiBold))
        value_rect = rect.adjusted(12, 27, -12, -10)
        painter.drawText(value_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap, self._value)


class ResizeGrip(QWidget):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self._dragging = False
        self._start_global = QPoint()
        self._start_size = QSize()
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._dragging = True
        self._start_global = event.globalPosition().toPoint()
        self._start_size = self.window().size()
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if not self._dragging:
            return
        delta = event.globalPosition().toPoint() - self._start_global
        window = self.window()
        width = max(PANEL_MIN_WIDTH, self._start_size.width() + delta.x())
        height = max(PANEL_MIN_HEIGHT, self._start_size.height() + delta.y())
        if hasattr(window, "set_panel_size"):
            window.set_panel_size(width, height)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._dragging = False
        event.accept()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#65c8ff"), 1.2)
        painter.setPen(pen)
        painter.drawLine(7, 18, 18, 7)
        painter.drawLine(11, 18, 18, 11)
        painter.drawLine(15, 18, 18, 15)
        painter.setPen(QPen(QColor(244, 181, 95, 92), 1.0))
        painter.drawLine(5, 18, 8, 18)


class ContextPanel(QWidget):
    def __init__(self, host: "PillWindow"):
        super().__init__(host)
        self.host = host
        self._build_ui()
        self._apply_style()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(PANEL_INSET, HEADER_HEIGHT - 4, PANEL_INSET, PANEL_INSET)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(4, 0, 4, 0)
        header_row.setSpacing(8)
        self.title_label = QLabel("APRIL", self)
        self.mode_chip = QLabel("CONTEXT", self)
        self.close_button = QPushButton("X", self)
        self.close_button.setFixedSize(30, 30)
        self.close_button.clicked.connect(self.host._collapse_text_panel)
        header_row.addWidget(self.title_label, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header_row.addStretch(1)
        header_row.addWidget(self.mode_chip, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header_row.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        card_row_1 = QHBoxLayout()
        card_row_1.setSpacing(8)
        card_row_2 = QHBoxLayout()
        card_row_2.setSpacing(8)

        self.card_status = SummaryCard("STATE", self)
        self.card_focus = SummaryCard("FOCUS", self)
        self.card_transcript = SummaryCard("LAST HEARD", self)
        self.card_reply = SummaryCard("LAST REPLY", self)

        card_row_1.addWidget(self.card_status, 1)
        card_row_1.addWidget(self.card_focus, 1)
        card_row_2.addWidget(self.card_transcript, 1)
        card_row_2.addWidget(self.card_reply, 1)

        self.open_loops_label = QLabel("OPEN LOOPS", self)
        self.open_loops_text = QLabel("None.", self)
        self.open_loops_text.setWordWrap(True)
        self.open_loops_text.setMinimumHeight(72)
        self.open_loops_text.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.open_loops_text.setContentsMargins(10, 8, 10, 8)

        self.timeline_label = QLabel("TIMELINE", self)
        self.timeline = TimelineFeed(self)

        input_row = QHBoxLayout()
        input_row.setSpacing(10)
        self.input_entry = QLineEdit(self)
        self.input_entry.setPlaceholderText("Type an instruction...")
        self.input_entry.returnPressed.connect(self._submit_text)
        self.send_button = QPushButton("Send", self)
        self.send_button.clicked.connect(self._submit_text)
        self.send_button.setFixedWidth(74)
        input_row.addWidget(self.input_entry, 1)
        input_row.addWidget(self.send_button, 0)

        footer_row = QHBoxLayout()
        footer_row.setContentsMargins(0, 0, 0, 0)
        footer_row.setSpacing(0)
        footer_row.addStretch(1)
        self.resize_grip = ResizeGrip(self)
        footer_row.addWidget(self.resize_grip, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)

        layout.addLayout(header_row)
        layout.addLayout(card_row_1)
        layout.addLayout(card_row_2)
        layout.addWidget(self.open_loops_label)
        layout.addWidget(self.open_loops_text)
        layout.addWidget(self.timeline_label)
        layout.addWidget(self.timeline, 1)
        layout.addLayout(input_row)
        layout.addLayout(footer_row)

    def _apply_style(self) -> None:
        self.setAutoFillBackground(False)
        self.title_label.setStyleSheet(f"color:#f4f7fb; font: 700 12pt '{HUD_FONT}'; letter-spacing: 1px;")
        self.mode_chip.setStyleSheet(
            "background:#0d1c2a;"
            "border:1px solid #2b5c79;"
            "border-radius: 11px;"
            "padding: 4px 10px;"
            "color:#86d7ff;"
            f"font: 700 8pt '{MONO_FONT}';"
        )
        self.close_button.setStyleSheet(
            """
            QPushButton {
                background: #101821;
                color: #9ec2dd;
                border: 1px solid #26445b;
                border-radius: 15px;
                font: 700 9pt 'Bahnschrift';
            }
            QPushButton:hover {
                background: #172533;
                color: #f4f7fb;
            }
            """
        )
        self.open_loops_label.setStyleSheet(f"color:#71afd6; font: 700 11px '{MONO_FONT}'; letter-spacing: 1px;")
        self.timeline_label.setStyleSheet(f"color:#71afd6; font: 700 11px '{MONO_FONT}'; letter-spacing: 1px;")
        self.open_loops_text.setStyleSheet(
            "background: #09131c;"
            "border: 1px solid #214359;"
            "border-radius: 16px;"
            "color: #f4f7fb;"
            f"font: 9pt '{BODY_FONT}';"
        )
        self.input_entry.setStyleSheet(
            """
            QLineEdit {
                background: #0b1520;
                color: #f4f7fb;
                border: 1px solid #224258;
                border-radius: 16px;
                padding: 10px 14px;
                font: 9pt 'Segoe UI';
            }
            QLineEdit:focus {
                border: 1px solid #39b6ff;
            }
            """
        )
        self.send_button.setStyleSheet(
            """
            QPushButton {
                background: #12304a;
                color: #f4f7fb;
                border: 1px solid #2c6b95;
                border-radius: 16px;
                padding: 9px 14px;
                font: 700 9pt 'Bahnschrift';
            }
            QPushButton:hover {
                background: #184264;
            }
            QPushButton:disabled {
                background: #1a2027;
                color: #65707c;
                border: 1px solid #27303a;
            }
            """
        )
        self.input_entry.textChanged.connect(self.sync_send_state)
        self.sync_send_state()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), 24, 24)

        gradient = QLinearGradient(QPointF(rect.topLeft()), QPointF(rect.bottomLeft()))
        gradient.setColorAt(0.0, QColor("#0c1620"))
        gradient.setColorAt(0.48, QColor("#09111a"))
        gradient.setColorAt(1.0, QColor("#060c12"))
        painter.fillPath(path, gradient)
        painter.setPen(QPen(PANEL_BORDER, 1.3))
        painter.drawPath(path)

        header_rect = QRect(rect.left() + 10, rect.top() + 10, rect.width() - 20, HEADER_HEIGHT - 18)
        header_path = QPainterPath()
        header_path.addRoundedRect(QRectF(header_rect), 18, 18)
        header_grad = QLinearGradient(QPointF(header_rect.topLeft()), QPointF(header_rect.topRight()))
        header_grad.setColorAt(0.0, QColor(18, 43, 64, 210))
        header_grad.setColorAt(0.65, QColor(9, 18, 28, 180))
        header_grad.setColorAt(1.0, QColor(21, 19, 14, 140))
        painter.fillPath(header_path, header_grad)

        painter.setPen(QPen(QColor(57, 182, 255, 112), 1.4))
        painter.drawLine(rect.left() + 18, rect.top() + 18, rect.left() + 74, rect.top() + 18)
        painter.drawLine(rect.left() + 18, rect.top() + 18, rect.left() + 18, rect.top() + 44)
        painter.drawLine(rect.right() - 74, rect.bottom() - 18, rect.right() - 18, rect.bottom() - 18)
        painter.drawLine(rect.right() - 18, rect.bottom() - 44, rect.right() - 18, rect.bottom() - 18)

        painter.setPen(QPen(QColor(244, 181, 95, 74), 1.0))
        painter.drawLine(rect.right() - 118, rect.top() + 18, rect.right() - 32, rect.top() + 18)

    def sync_send_state(self) -> None:
        has_text = bool(self.input_entry.text().strip())
        self.send_button.setEnabled(has_text)

    def _submit_text(self) -> None:
        self.host.submit_text_from_panel()


class PillCanvas(QWidget):
    def __init__(self, host: "PillWindow"):
        super().__init__(host)
        self.host = host
        self.setAutoFillBackground(False)

    def set_glow_color(self, color: QColor) -> None:
        self.update()

    def mousePressEvent(self, event) -> None:
        self.host.handle_canvas_press(event)

    def mouseMoveEvent(self, event) -> None:
        self.host.handle_canvas_drag(event)

    def mouseReleaseEvent(self, event) -> None:
        self.host.handle_canvas_release(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(6, 6, -6, -6)
        if rect.width() <= 0 or rect.height() <= 0:
            return
        painter.fillRect(rect, QColor("#0a1118"))
        painter.setPen(QPen(QColor("#2a5976"), 1.2))
        painter.drawRect(rect)
        painter.setPen(QPen(QColor(57, 182, 255, 82), 1.2))
        painter.drawLine(rect.left() + 14, rect.top() + 12, rect.left() + 56, rect.top() + 12)
        painter.drawLine(rect.left() + 14, rect.bottom() - 12, rect.left() + 36, rect.bottom() - 12)
        painter.setPen(QPen(QColor(244, 181, 95, 68), 1.0))
        painter.drawLine(rect.right() - 48, rect.top() + 12, rect.right() - 14, rect.top() + 12)

        self._draw_status_mark(painter, rect)
        self._draw_text(painter, rect)

    def _draw_text(self, painter: QPainter, rect: QRect) -> None:
        host = self.host
        label_font = QFont(HUD_FONT, 10, QFont.Weight.Bold)
        msg_font = QFont(BODY_FONT, 9)
        chip_font = QFont(MONO_FONT, 8, QFont.Weight.Bold)
        painter.setFont(label_font)
        painter.setPen(TEXT)

        icon_left = rect.left() + PAD_X
        icon_center_x = icon_left + (ICON_SIZE // 2)
        content_left = icon_left + ICON_SIZE + 12
        content_right = rect.right() - PAD_X

        chip = host.context_chip()
        chip_width = 0
        if chip:
            painter.setFont(chip_font)
            chip_metrics = QFontMetrics(chip_font)
            chip_text_width = min(chip_metrics.horizontalAdvance(chip) + 18, NODE_MAX_WIDTH)
            chip_width = chip_text_width
            chip_rect = QRect(content_right - chip_width, rect.top() + 12, chip_width, 22)
            chip_path = QPainterPath()
            chip_path.addRoundedRect(QRectF(chip_rect), 11, 11)
            chip_grad = QLinearGradient(QPointF(chip_rect.topLeft()), QPointF(chip_rect.topRight()))
            chip_grad.setColorAt(0.0, QColor("#0e2233"))
            chip_grad.setColorAt(1.0, QColor("#122331"))
            painter.fillPath(chip_path, chip_grad)
            painter.setPen(QPen(QColor("#2b5c79"), 1))
            painter.drawPath(chip_path)
            painter.setPen(QColor("#86d7ff"))
            painter.drawText(chip_rect, Qt.AlignmentFlag.AlignCenter, chip)
            painter.setPen(TEXT)

        label_right = content_right - chip_width - (10 if chip_width else 0)
        label_rect = QRect(content_left, rect.top() + 9, max(0, label_right - content_left), 22)
        painter.setFont(label_font)
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, STATES[host._state]["label"])

        message = host._message.strip()
        if message:
            painter.setFont(msg_font)
            painter.setPen(MUTED)
            msg_rect = QRect(content_left, rect.top() + 32, max(0, rect.right() - content_left - PAD_X), rect.height() - 38)
            painter.drawText(msg_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap, message)

    def _draw_status_mark(self, painter: QPainter, rect: QRect) -> None:
        state = self.host._state
        color = _color(STATES[state]["color"])
        pulse = self.host._phase
        cx = rect.left() + PAD_X + (ICON_SIZE // 2)
        cy = rect.top() + (rect.height() // 2)

        base_pen = QPen(QColor("#2a3138"), 1.2)
        painter.setPen(base_pen)
        painter.setBrush(QColor("#12161a"))
        painter.drawEllipse(QPointF(cx, cy), 13, 13)

        if state == "idle":
            arc_pen = QPen(_color(STATES["idle"]["color"], 160), 2.0)
            arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(arc_pen)
            radius = 9 + math.sin(pulse * 0.12) * 1.0
            painter.drawArc(QRectF(cx - radius, cy - radius, radius * 2, radius * 2), 0, 360 * 16)
            highlight_pen = QPen(_color(STATES["idle"]["color"], 255), 2.2)
            highlight_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(highlight_pen)
            start = int((pulse * 8) % 360)
            painter.drawArc(QRectF(cx - radius, cy - radius, radius * 2, radius * 2), start * 16, 90 * 16)
            radial = QRadialGradient(QPointF(cx, cy), 10)
            radial.setColorAt(0.0, QColor(180, 220, 255, 34))
            radial.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(radial)
            painter.drawEllipse(QPointF(cx, cy), 10, 10)
            return

        if state == "listening":
            ripple_radius = 7 + ((pulse % 36) / 36.0) * 8
            ripple_color = QColor(color)
            ripple_color.setAlpha(max(18, 130 - int((pulse % 36) / 36.0 * 120)))
            painter.setPen(QPen(ripple_color, 1.4))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(cx, cy), ripple_radius, ripple_radius)
            bar_pen = QPen(color, 3)
            bar_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(bar_pen)
            for idx, phase_shift in enumerate((0.0, 1.2, 2.4)):
                x = cx - 5 + (idx * 5)
                height = 5 + int((math.sin((pulse * 0.22) + phase_shift) + 1.0) * 3.4)
                painter.drawLine(QPointF(x, cy - height / 2), QPointF(x, cy + height / 2))
            return

        if state == "thinking":
            orbit_radius = 6.0
            for idx in range(4):
                angle = (pulse * 0.095) + (idx * (math.pi / 2.0))
                dot_color = QColor(color)
                dot_color.setAlpha(255 if idx == (pulse // 2) % 4 else 92)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(dot_color)
                painter.drawEllipse(
                    QPointF(cx + math.cos(angle) * orbit_radius, cy + math.sin(angle) * orbit_radius),
                    2.3,
                    2.3,
                )
            return

        if state == "speaking":
            for cycle, span, alpha in ((20, 10, 115), (30, 14, 84)):
                factor = (pulse % cycle) / float(cycle)
                ring_radius = 4 + (factor * span)
                ring_color = QColor(color)
                ring_color.setAlpha(max(12, alpha - int(alpha * factor)))
                painter.setPen(QPen(ring_color, 1.6))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPointF(cx, cy), ring_radius, ring_radius)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QPointF(cx, cy), 4.5, 4.5)
            return

        if state == "error":
            alpha = 180 if self.host._error_flash else 255
            danger = QColor(color)
            danger.setAlpha(alpha)
            painter.setPen(QPen(danger, 1.4))
            painter.setBrush(QColor(58, 32, 36, 210))
            points = [
                QPointF(cx, cy - 7),
                QPointF(cx - 7, cy + 6),
                QPointF(cx + 7, cy + 6),
            ]
            painter.drawPolygon(QPolygonF(points))
            painter.setPen(QPen(danger, 2.0))
            painter.drawLine(QPointF(cx, cy - 2), QPointF(cx, cy + 2))
            painter.drawPoint(QPointF(cx, cy + 5))


class PillWindow(QWidget):
    append_output_signal = pyqtSignal(str, str)

    def __init__(self, config: dict[str, Any], on_config_change=None, on_text_submit=None):
        super().__init__(None)
        trace_startup("PillWindow.__init__ entered")
        self.config = dict(config)
        self.on_config_change = on_config_change
        self.on_text_submit = on_text_submit

        self._state = "idle"
        self._node = ""
        self._message = ""
        self._phase = 0
        self._collapsed = False
        self._panel_visible = False
        self._panel_w = PANEL_WIDTH
        self._panel_h = PANEL_HEIGHT
        self._history: list[tuple[str, str]] = []
        self._hovering = False
        self._dragging = False
        self._drag_offset = QPoint()
        self._anchor_x: float | None = None
        self._anchor_y: float | None = None
        self._anchor_bottom_y: float | None = None
        self._target_width = MIN_WIDTH
        self._target_height = 62
        self._error_flash = False

        self._animation = QVariantAnimation(self)
        self._animation.setDuration(220)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._apply_animation_value)
        self._animation.finished.connect(self._sync_child_layout)

        self._motion_timer = QTimer(self)
        self._motion_timer.timeout.connect(self._tick_motion)
        self._motion_timer.start(33)

        self._collapse_timer = QTimer(self)
        self._collapse_timer.setSingleShot(True)
        self._collapse_timer.timeout.connect(self._collapse_idle)

        self._message_timer = QTimer(self)
        self._message_timer.setSingleShot(True)
        self._message_timer.timeout.connect(self._clear_idle_message)

        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.timeout.connect(self._sync_hover_exit)

        self._keep_top_timer = QTimer(self)
        self._keep_top_timer.timeout.connect(self.raise_)
        self._keep_top_timer.start(2000)
        self._allow_close = False
        trace_startup("PillWindow timers configured")

        self._build_window()
        trace_startup("PillWindow._build_window complete")
        self._load_persisted_history()
        trace_startup("PillWindow history loaded")
        self._redraw(animated=False)
        trace_startup("PillWindow initial redraw complete")
        self.show()
        self.raise_()
        self.activateWindow()
        trace_startup("PillWindow shown")
        if self.text_panel_active():
            self._seed_debug_console_if_needed()
            QTimer.singleShot(120, self.panel.input_entry.setFocus)
            trace_startup("PillWindow text panel active at startup")
        else:
            self._schedule_collapse()
            trace_startup("PillWindow collapse scheduled at startup")

    def _build_window(self) -> None:
        self.setWindowFlags(Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setMouseTracking(True)
        self.setStyleSheet(f"background:{WINDOW_BG};")
        self.setWindowTitle("APRIL")

        self.canvas = PillCanvas(self)
        self.panel = ContextPanel(self)
        self.panel.hide()
        self.append_output_signal.connect(self._append_output)

        for widget in self._hover_widgets():
            widget.installEventFilter(self)

    def _hover_widgets(self) -> list[QObject]:
        widgets: list[QObject] = [self, self.canvas, self.panel, self.panel.input_entry, self.panel.send_button, self.panel.timeline, self.panel.resize_grip]
        widgets.extend(
            [
                self.panel.title_label,
                self.panel.mode_chip,
                self.panel.close_button,
                self.panel.card_status,
                self.panel.card_focus,
                self.panel.card_transcript,
                self.panel.card_reply,
                self.panel.open_loops_label,
                self.panel.open_loops_text,
                self.panel.timeline_label,
            ]
        )
        return widgets

    def sizeHint(self) -> QSize:
        return QSize(self._target_width, self._target_height)

    def eventFilter(self, _obj, event) -> bool:
        if event.type() == QEvent.Type.Enter:
            self._on_hover_enter()
        elif event.type() == QEvent.Type.Leave:
            self._on_hover_leave()
        return False

    def context_chip(self) -> str:
        if self._node:
            return self._node.upper()
        if self._state == "idle":
            return ""
        if not self.config.get("at_home", True):
            return "AWAY"
        if not self.config.get("voice", True):
            return "VOICE OFF"
        return ""

    def text_panel_active(self) -> bool:
        return (not self.config.get("voice", True)) or self._panel_visible

    def set_panel_size(self, width: int, height: int) -> None:
        self._panel_w = max(PANEL_MIN_WIDTH, width)
        self._panel_h = max(PANEL_MIN_HEIGHT, height)
        if self.text_panel_active():
            self._redraw(animated=False)

    def handle_canvas_press(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._collapsed:
            self._collapsed = False
            self._open_text_panel()
            return
        self._dragging = True
        self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def handle_canvas_drag(self, event) -> None:
        if not self._dragging:
            return
        new_pos = event.globalPosition().toPoint() - self._drag_offset
        self.move(new_pos)
        self._persist_anchor_from_geometry()

    def handle_canvas_release(self, _event) -> None:
        self._dragging = False

    def submit_text_from_panel(self) -> None:
        text = self.panel.input_entry.text().strip()
        if not text:
            return
        self.panel.input_entry.clear()
        self._append_output("user", text)
        self._append_output("system", "Queued")
        if not self.on_text_submit:
            self._append_output("assistant", "Text input is ready. The assistant pipeline can plug in here.")
            return

        def run_submit() -> None:
            try:
                response = self.on_text_submit(text)
            except Exception as exc:
                self.append_output_signal.emit("system", f"text submit failed: {exc}")
                return
            if response:
                self.append_output_signal.emit("assistant", response)

        threading.Thread(target=run_submit, daemon=True).start()

    def submit_text_programmatically(self, text: str) -> None:
        self.panel.input_entry.setText(text)
        self.submit_text_from_panel()

    def apply_state(self, state: str, message: str = "", node: str = "") -> None:
        self._collapse_timer.stop()
        self._message_timer.stop()
        self._collapsed = False
        self._state = state if state in STATES else "idle"
        self._message = " ".join(str(message or "").split())
        self._node = " ".join(str(node or "").split())
        self._error_flash = self._state == "error"
        if self._state in {"listening", "thinking", "speaking"}:
            self.canvas.set_glow_color(_color(STATES[self._state]["color"]))
        elif self._state == "error":
            self.canvas.set_glow_color(_color(STATES["error"]["color"]))
        else:
            self.canvas.set_glow_color(_color(STATES["idle"]["color"]))
        self._redraw(animated=True)
        if self.text_panel_active():
            QTimer.singleShot(120, self.panel.input_entry.setFocus)
        elif self._state == "idle":
            if self._message:
                self._schedule_message_clear()
            else:
                self._schedule_collapse()

    def apply_output(self, role: str, text: str) -> None:
        self._append_output(role, text)

    def apply_config(self, config: dict[str, Any]) -> None:
        self.config.clear()
        self.config.update(config)
        self._collapsed = False
        self._collapse_timer.stop()
        self._message_timer.stop()
        self._redraw(animated=False)
        if self.text_panel_active():
            QTimer.singleShot(120, self.panel.input_entry.setFocus)
        elif self._state == "idle":
            if self._message:
                self._schedule_message_clear()
            else:
                self._schedule_collapse()

    def refresh_context_view(self) -> None:
        self._history.clear()
        self._refresh_summary_cards()
        self._seed_debug_console_if_needed()

    def request_destroy(self) -> None:
        self._allow_close = True
        self.close()

    def closeEvent(self, event) -> None:
        if not self._allow_close:
            event.ignore()
            return
        self._keep_top_timer.stop()
        self._motion_timer.stop()
        self._collapse_timer.stop()
        self._message_timer.stop()
        self._hover_timer.stop()
        event.accept()

    def paintEvent(self, _event) -> None:
        if not self.text_panel_active():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(PANEL_MARGIN // 2, PANEL_MARGIN // 2, -(PANEL_MARGIN // 2), -(PANEL_MARGIN // 2))
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), 28, 28)
        outer_grad = QLinearGradient(QPointF(rect.topLeft()), QPointF(rect.bottomLeft()))
        outer_grad.setColorAt(0.0, QColor("#08111a"))
        outer_grad.setColorAt(0.55, QColor("#060b10"))
        outer_grad.setColorAt(1.0, QColor("#04070b"))
        painter.fillPath(path, outer_grad)
        painter.setPen(QPen(QColor("#274c67"), 1.4))
        painter.drawPath(path)

        painter.setPen(QPen(QColor(57, 182, 255, 92), 1.4))
        painter.drawLine(rect.left() + 18, rect.top() + 18, rect.left() + 82, rect.top() + 18)
        painter.drawLine(rect.left() + 18, rect.top() + 18, rect.left() + 18, rect.top() + 48)
        painter.drawLine(rect.right() - 82, rect.bottom() - 18, rect.right() - 18, rect.bottom() - 18)
        painter.drawLine(rect.right() - 18, rect.bottom() - 48, rect.right() - 18, rect.bottom() - 18)
        painter.setPen(QPen(QColor(244, 181, 95, 70), 1.0))
        painter.drawLine(rect.right() - 128, rect.top() + 18, rect.right() - 40, rect.top() + 18)

    def _load_persisted_history(self) -> None:
        try:
            with open(HISTORY_PATH, encoding="utf-8") as handle:
                items = json.load(handle)
        except Exception:
            return
        if not isinstance(items, list):
            return
        for item in items[-MAX_HISTORY_ITEMS:]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", "") or "").strip().lower()
            text = str(item.get("text", "") or "").strip()
            if role not in {"user", "assistant", "system"} or not text:
                continue
            self._history.append((role, " ".join(text.split())))
        if self._history:
            self.panel.timeline.set_entries(self._history)

    def _save_history(self) -> None:
        os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
        data = [{"role": role, "text": text} for role, text in self._history[-MAX_HISTORY_ITEMS:]]
        with open(HISTORY_PATH, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)

    def _append_output(self, role: str, text: str) -> None:
        clean = " ".join(str(text).strip().split())
        if not clean:
            return
        self._history.append((role, clean))
        self._history = self._history[-MAX_HISTORY_ITEMS:]
        self._refresh_summary_cards()
        self.panel.timeline.set_entries(self._history)
        try:
            self._save_history()
        except Exception:
            pass

    def _seed_debug_console_if_needed(self) -> None:
        if self._history:
            self.panel.timeline.set_entries(self._history)
            return
        self._refresh_summary_cards()
        snapshot_lines = get_widget_snapshot_lines(limit=RECENT_SNAPSHOT_LINES)
        for role, text in snapshot_lines:
            self._history.append((role, text))
        debug_events = read_recent_events(limit=RECENT_DEBUG_EVENTS)
        for event in debug_events:
            summary = self._format_debug_event(event)
            if summary:
                self._history.append(("system", summary))
        self._history = self._history[-MAX_HISTORY_ITEMS:]
        self.panel.timeline.set_entries(self._history)
        try:
            self._save_history()
        except Exception:
            pass

    def _format_debug_event(self, event: dict[str, Any]) -> str:
        event_type = str(event.get("event", "") or "").strip()
        if not event_type:
            return ""
        if event_type == "transcript":
            transcript = str(event.get("transcript", "") or "").strip()
            return f"Transcript: {transcript}" if transcript else ""
        if event_type == "assistant_response":
            response = str(event.get("response", "") or "").strip()
            return f"Reply: {response}" if response else ""
        if event_type == "transcription_unavailable":
            return "Transcription was unavailable."
        if event_type == "request_begin":
            source = str(event.get("source", "") or "").strip() or "unknown"
            return f"Request started from {source}."
        if event_type == "action_result":
            reply = str(event.get("reply", "") or "").strip()
            return f"Action: {reply}" if reply else ""
        return ""

    def _refresh_summary_cards(self) -> None:
        snapshot = get_widget_snapshot_data(limit=6)
        if not snapshot:
            self.panel.card_status.set_value("--")
            self.panel.card_focus.set_value("--")
            self.panel.card_transcript.set_value("--")
            self.panel.card_reply.set_value("--")
            self.panel.open_loops_text.setText("None.")
            return
        self.panel.card_status.set_value(str(snapshot.get("status", "--") or "--").upper())
        focus = str(snapshot.get("focus", "") or snapshot.get("active_window", "") or "").strip() or "No active app"
        transcript = str(snapshot.get("last_transcript", "") or "").strip() or "Nothing heard yet"
        reply = str(snapshot.get("last_reply", "") or "").strip() or "No reply yet"
        self.panel.card_focus.set_value(focus)
        self.panel.card_transcript.set_value(transcript)
        self.panel.card_reply.set_value(reply)
        open_loops = snapshot.get("open_loops", [])
        if isinstance(open_loops, list) and open_loops:
            self.panel.open_loops_text.setText("\n".join(f"- {item}" for item in open_loops))
        else:
            self.panel.open_loops_text.setText("None.")

    def _show_context_menu(self, global_pos: QPoint) -> None:
        if self._collapsed:
            self._collapsed = False
            self._redraw(animated=False)
        menu = QMenu(self)
        menu.setStyleSheet(
            """
            QMenu {
                background: #14181d;
                border: 1px solid #27303a;
                border-radius: 10px;
                padding: 6px;
                color: #dbe4ee;
                font: 9pt 'Segoe UI';
            }
            QMenu::item {
                padding: 8px 18px;
                border-radius: 8px;
            }
            QMenu::item:selected {
                background: #203247;
            }
            """
        )
        voice_label = "Voice: ON" if self.config.get("voice", True) else "Voice: OFF"
        home_label = "At Home: YES" if self.config.get("at_home", True) else "At Home: NO"
        term_label = "Terminal: SHOW" if self.config.get("terminal_visible", True) else "Terminal: HIDE"

        voice_action = QAction(voice_label, self)
        voice_action.triggered.connect(self._toggle_voice)
        home_action = QAction(home_label, self)
        home_action.triggered.connect(self._toggle_home)
        term_action = QAction(term_label, self)
        term_action.triggered.connect(self._toggle_terminal)

        menu.addAction(voice_action)
        menu.addAction(home_action)
        menu.addAction(term_action)
        if self.text_panel_active():
            refresh_action = QAction("Refresh Context", self)
            refresh_action.triggered.connect(self.refresh_context_view)
            menu.addAction(refresh_action)
        menu.addSeparator()
        quit_action = QAction("Quit APRIL", self)
        quit_action.triggered.connect(self.request_destroy)
        menu.addAction(quit_action)
        menu.exec(global_pos)

    def _toggle_voice(self) -> None:
        self._set_config("voice", not self.config.get("voice", True))

    def _toggle_home(self) -> None:
        self._set_config("at_home", not self.config.get("at_home", True))

    def _toggle_terminal(self) -> None:
        self._set_config("terminal_visible", not self.config.get("terminal_visible", True))

    def _set_config(self, key: str, value: Any) -> None:
        self.config[key] = value
        self._write_config()
        if key == "voice":
            self.apply_config(self.config)
        if self.on_config_change:
            self.on_config_change(key, value)

    def _write_config(self) -> None:
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as handle:
                json.dump(self.config, handle, indent=2)
        except Exception as exc:
            self.apply_state("error", f"config write failed: {exc}")

    def _open_text_panel(self) -> None:
        self._panel_visible = True
        self._redraw(animated=True)
        QTimer.singleShot(120, self.panel.input_entry.setFocus)

    def _collapse_text_panel(self) -> None:
        self._panel_visible = False
        if not self.config.get("voice", True):
            self._set_config("voice", True)
        else:
            self._redraw(animated=True)

    def _tick_motion(self) -> None:
        self._phase += 1
        if self._error_flash and self._phase % 8 == 0:
            self._error_flash = False
        self.canvas.update()
        if self.text_panel_active():
            self.panel.update()

    def _on_hover_enter(self) -> None:
        self._hovering = True
        self._hover_timer.stop()
        self._collapse_timer.stop()
        self._message_timer.stop()

    def _on_hover_leave(self) -> None:
        self._hover_timer.start(40)

    def _sync_hover_exit(self) -> None:
        if self.frameGeometry().contains(QCursor.pos()):
            return
        self._hovering = False
        if self._state == "idle":
            if self._message:
                self._schedule_message_clear()
            else:
                self._schedule_collapse()

    def _schedule_collapse(self) -> None:
        if self.text_panel_active() or self._hovering:
            return
        self._collapse_timer.start(AUTO_COLLAPSE_MS)

    def _schedule_message_clear(self) -> None:
        if self.text_panel_active() or self._hovering:
            return
        self._message_timer.start(MESSAGE_HOLD_MS)

    def _collapse_idle(self) -> None:
        if self._state == "idle" and not self._message:
            self._collapsed = True
            self._redraw(animated=True)

    def _clear_idle_message(self) -> None:
        if self._hovering or self._state != "idle" or not self._message:
            return
        self._message = ""
        self._redraw(animated=True)
        self._schedule_collapse()

    def _desired_pill_size(self) -> tuple[int, int]:
        if self._collapsed:
            return COLLAPSED_SIZE, COLLAPSED_SIZE

        label_font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        msg_font = QFont("Segoe UI", 9)
        label_metrics = QFontMetrics(label_font)
        msg_metrics = QFontMetrics(msg_font)
        chip = self.context_chip()
        chip_width = 0
        if chip:
            chip_width = min(QFontMetrics(QFont("Segoe UI", 8, QFont.Weight.Bold)).horizontalAdvance(chip) + 18, NODE_MAX_WIDTH)

        message = self._message.strip()
        if not message:
            width = max(MIN_WIDTH, PAD_X + ICON_SIZE + 12 + label_metrics.horizontalAdvance(STATES[self._state]["label"]) + chip_width + PAD_X + 14)
            return min(MAX_WIDTH, width), 60

        wrapped = msg_metrics.boundingRect(QRect(0, 0, MESSAGE_WRAP_WIDTH, 400), int(Qt.TextFlag.TextWordWrap), message)
        content_width = max(label_metrics.horizontalAdvance(STATES[self._state]["label"]) + chip_width + 12, wrapped.width())
        width = min(MAX_WIDTH, max(MIN_WIDTH, PAD_X + ICON_SIZE + 12 + content_width + PAD_X + 10))
        height = max(62, 28 + wrapped.height() + 20)
        return width, height

    def _target_geometry(self) -> QRect:
        if self.text_panel_active():
            width = self._panel_w
            height = self._panel_h
            anchor_mode = "bottom"
        else:
            width, height = self._desired_pill_size()
            anchor_mode = "bottom"
        self._target_width = width
        self._target_height = height
        x, y = self._resolve_anchor_position(width, height, anchor_mode)
        return QRect(x, y, width, height)

    def _resolve_anchor_position(self, width: int, height: int, anchor_mode: str) -> tuple[int, int]:
        screen = QApplication.primaryScreen()
        if screen is not None:
            work_area = screen.availableGeometry()
        else:
            work_area = QRect(0, 0, 1920, 1080)

        if self._anchor_x is None or self._anchor_bottom_y is None:
            self._anchor_x = float(self.config.get("widget_anchor_x")) if self.config.get("widget_anchor_x") is not None else None
            self._anchor_y = float(self.config.get("widget_anchor_y")) if self.config.get("widget_anchor_y") is not None else None
            self._anchor_bottom_y = float(self.config.get("widget_anchor_bottom_y")) if self.config.get("widget_anchor_bottom_y") is not None else None

        if self._anchor_x is None or self._anchor_bottom_y is None:
            self._anchor_x = work_area.center().x()
            self._anchor_bottom_y = work_area.bottom() - ANCHOR_FROM_BOTTOM
            self._anchor_y = self._anchor_bottom_y - (height / 2.0)

        if (
            self._anchor_x < work_area.left() - width
            or self._anchor_x > work_area.right() + width
            or self._anchor_bottom_y < work_area.top()
            or self._anchor_bottom_y > work_area.bottom() + height
        ):
            self._anchor_x = work_area.center().x()
            self._anchor_bottom_y = work_area.bottom() - ANCHOR_FROM_BOTTOM
            self._anchor_y = self._anchor_bottom_y - (height / 2.0)

        x = int(round(self._anchor_x - (width / 2.0)))
        if anchor_mode == "bottom":
            y = int(round(self._anchor_bottom_y - height))
        else:
            center_y = self._anchor_y if self._anchor_y is not None else self._anchor_bottom_y - (height / 2.0)
            y = int(round(center_y - (height / 2.0)))

        x = max(work_area.left(), min(work_area.right() - width, x))
        y = max(work_area.top(), min(work_area.bottom() - height, y))
        return x, y

    def _persist_anchor_from_geometry(self) -> None:
        frame = self.frameGeometry()
        self._anchor_x = frame.x() + (frame.width() / 2.0)
        self._anchor_y = frame.y() + (frame.height() / 2.0)
        self._anchor_bottom_y = frame.y() + frame.height()
        self.config["widget_anchor_x"] = round(self._anchor_x, 1)
        self.config["widget_anchor_y"] = round(self._anchor_y, 1)
        self.config["widget_anchor_bottom_y"] = round(self._anchor_bottom_y, 1)
        try:
            self._write_config()
        except Exception:
            pass

    def _redraw(self, animated: bool) -> None:
        target = self._target_geometry()
        trace_startup(
            f"_redraw animated={animated} panel={self.text_panel_active()} collapsed={self._collapsed} "
            f"target=({target.x()},{target.y()},{target.width()},{target.height()})"
        )
        if self.text_panel_active():
            self.panel.show()
            self._refresh_summary_cards()
            if not self._history:
                self._seed_debug_console_if_needed()
        else:
            self.panel.hide()
        self.canvas.raise_()
        if animated:
            self._animation.stop()
            self._animation.setStartValue(self.geometry())
            self._animation.setEndValue(target)
            self._animation.start()
        else:
            self.setGeometry(target)
            self._sync_child_layout()
        self.update()
        self.canvas.update()

    def _apply_animation_value(self, value: Any) -> None:
        rect = value if isinstance(value, QRect) else QRect(value)
        self.setGeometry(rect)
        self._sync_child_layout()

    def _sync_child_layout(self) -> None:
        width = self.width()
        height = self.height()
        if self.text_panel_active():
            self.canvas.setGeometry(0, 0, width, HEADER_HEIGHT)
            self.panel.setGeometry(PANEL_MARGIN, PANEL_MARGIN, width - (PANEL_MARGIN * 2), height - (PANEL_MARGIN * 2))
        else:
            self.canvas.setGeometry(0, 0, width, height)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_child_layout()


class APRILWidget:
    def __init__(self, config: dict, on_config_change=None, on_text_submit=None):
        trace_startup("APRILWidget.__init__ entered")
        self.config = dict(config)
        self.on_config_change = on_config_change
        self.on_text_submit = on_text_submit
        self.app = QApplication.instance() or QApplication(sys.argv[:1])
        trace_startup("QApplication acquired")
        self.app.setQuitOnLastWindowClosed(False)
        self.app.aboutToQuit.connect(lambda: trace_startup("QApplication aboutToQuit emitted"))
        self._heartbeat_timer = QTimer()
        self._heartbeat_timer.setInterval(5000)
        self._heartbeat_timer.timeout.connect(lambda: trace_startup("QApplication heartbeat"))
        self._heartbeat_timer.start()
        self.bridge = _QtBridge()
        trace_startup("_QtBridge created")
        self.window = PillWindow(self.config, on_config_change=on_config_change, on_text_submit=on_text_submit)
        trace_startup("PillWindow created")

        self.bridge.state_signal.connect(self.window.apply_state)
        self.bridge.output_signal.connect(lambda text, role: self.window.apply_output(role, text))
        self.bridge.config_signal.connect(self.window.apply_config)
        self.bridge.refresh_signal.connect(self.window.refresh_context_view)
        self.bridge.destroy_signal.connect(self.window.request_destroy)
        self.bridge.config_refresh_signal.connect(self.window.apply_config)
        self.bridge.panel_submit_signal.connect(self.window.submit_text_programmatically)
        self.bridge.quit_signal.connect(self.app.quit)
        trace_startup("APRILWidget signals connected")

    def set_state(self, state: str, message: str = "", node: str = ""):
        self.bridge.state_signal.emit(state, message, node)

    def add_text_output(self, text: str, role: str = "assistant"):
        self.bridge.output_signal.emit(text, role)

    def update_from_config(self):
        self.bridge.config_signal.emit(dict(self.window.config))

    def refresh_context_view(self):
        self.bridge.refresh_signal.emit()

    def schedule_config_refresh(self, config: dict):
        self.bridge.config_refresh_signal.emit(dict(config))

    def run(self):
        self.window.show()
        self.app.exec()

    def destroy(self):
        self.bridge.destroy_signal.emit()
        self.bridge.quit_signal.emit()


if __name__ == "__main__":
    import time

    dummy_config = {
        "voice": True,
        "at_home": True,
        "terminal_visible": True,
    }

    def on_change(key, value):
        print(f"[config] {key} = {value}")

    def on_submit(text):
        print(f"[text] {text}")
        return f"Received: {text}"

    widget = APRILWidget(dummy_config, on_config_change=on_change, on_text_submit=on_submit)

    def demo() -> None:
        time.sleep(1)
        widget.set_state("listening", node="mac")
        time.sleep(2)
        widget.set_state("thinking", node="mac")
        time.sleep(2)
        widget.set_state("speaking", "opening the orbital diagnostics feed", node="mac")
        time.sleep(2)
        widget.set_state("error", "ollama unreachable")
        time.sleep(2)
        widget.set_state("idle")
        time.sleep(2)
        dummy_config["voice"] = False
        widget.schedule_config_refresh(dummy_config)
        time.sleep(0.8)
        widget.add_text_output("Voice is off. Text replies will appear here.", role="assistant")
        time.sleep(0.8)
        widget.bridge.panel_submit_signal.emit("summarize today's plan")
        time.sleep(3)
        dummy_config["voice"] = True
        widget.schedule_config_refresh(dummy_config)
        widget.set_state("idle")
        QTimer.singleShot(1200, widget.destroy)

    threading.Thread(target=demo, daemon=True).start()
    widget.run()
