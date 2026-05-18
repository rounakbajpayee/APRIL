"""
widget.py - APRIL floating status widget.

Always-on-top, no title bar, bottom-center.
Canvas-drawn Flow-style dictation pill with a Windows shaped region.
"""

import ctypes
import ctypes.wintypes
import json
import math
import os
import threading
import tkinter as tk
import tkinter.font as tkfont


gdi32 = ctypes.windll.gdi32
user32 = ctypes.windll.user32
user32.SetWindowPos.argtypes = [
    ctypes.wintypes.HWND,
    ctypes.wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_uint,
]
user32.SetWindowPos.restype = ctypes.wintypes.BOOL
try:
    user32.SetProcessDPIAware()
except Exception:
    pass

SPI_GETWORKAREA = 0x0030
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040


def _set_window_region(hwnd, w, h, radius, scale):
    """Clip window to a rounded rectangle using SetWindowRgn."""
    # Tk geometry is already expressed in the window coordinate space that
    # SetWindowRgn expects. Scaling these values makes the region too large on
    # high-DPI displays, which exposes the rectangular toplevel background.
    pw = int(w)
    ph = int(h)
    pr = int(radius * 2)
    rgn = gdi32.CreateRoundRectRgn(0, 0, pw + 1, ph + 1, pr, pr)
    user32.SetWindowRgn(hwnd, rgn, True)


def _get_dpi_scale(root):
    """Return DPI scale factor: 1.0 at 100%, 1.5 at 150%, etc."""
    return root.winfo_fpixels("1i") / 96.0


def _get_work_area():
    """Return the usable primary-monitor work area in screen coordinates."""
    rect = ctypes.wintypes.RECT()
    if user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
        return rect.left, rect.top, rect.right, rect.bottom
    return 0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


STATES = {
    "idle": {"color": "#9aa0a6", "label": "APRIL", "pulse": False},
    "listening": {"color": "#47e38d", "label": "Listening", "pulse": True},
    "thinking": {"color": "#f7b84b", "label": "Thinking", "pulse": False},
    "speaking": {"color": "#61a8ff", "label": "Speaking", "pulse": False},
    "error": {"color": "#ff5a67", "label": "Error", "pulse": False},
}

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

BG = "#111214"
TRANSPARENT = "#010203"
BORDER = "#2c2f34"
HIGHLIGHT = "#3a3d44"
TEXT = "#f4f6f8"
MUTED = "#8d96a0"
PANEL_BG = "#111214"
FIELD_BG = "#17191d"
FIELD_BORDER = "#30343a"
USER_BUBBLE = "#1c2530"
ASSISTANT_BUBBLE = "#181b1f"

PAD_X = 18
PAD_Y = 11
RADIUS = 30
IDLE_MIN_WIDTH = 0
MIN_WIDTH = 188
MAX_WIDTH = 420
MESSAGE_WRAP_WIDTH = 360
ICON_SIZE = 24
ICON_GAP = 10
NODE_GAP = 12
NODE_PAD_X = 8
NODE_MAX_WIDTH = 76
MSG_GAP = 5
ANCHOR_FROM_BOTTOM = 50
ANIM_MS = 160
ANIM_STEP_MS = 16
AUTO_COLLAPSE_MS = 7000
MESSAGE_HOLD_MS = 9000
COLLAPSED_SIZE = 46
PANEL_WIDTH = 392
PANEL_HEIGHT = 292
PANEL_PAD = 16
PANEL_RADIUS = 26
PANEL_HEADER_H = 38
PANEL_INPUT_H = 36
PANEL_GAP = 10


class APRILWidget:
    def __init__(self, config: dict, on_config_change=None, on_text_submit=None):
        self.config = config
        self.on_config_change = on_config_change
        self.on_text_submit = on_text_submit

        self._state = "idle"
        self._node = ""
        self._message = ""
        self._pulse_job = None
        self._anim_job = None
        self._collapse_job = None
        self._message_clear_job = None
        self._hover_sync_job = None
        self._dot_id = None
        self._wave_ids = []
        self._wave_phase = 0
        self._motion_phase = 0
        self._collapsed = False
        self._display_w = 0
        self._display_h = 0
        self._anchor_x = None
        self._anchor_y = None
        self._anchor_bottom_y = None
        self._hwnd = None
        self._scale = 1.0
        self._panel_visible = False
        self._history = []
        self._hovering = False

        self._build_window()
        self._build_fonts()
        self._build_canvas()
        self._build_text_panel()
        self._redraw()
        self.root.deiconify()
        self._schedule_collapse()
        if self._text_panel_active():
            self.root.after(120, self._focus_text_input)

    def _build_window(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("APRIL")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", TRANSPARENT)
        self.root.resizable(False, False)
        self.root.config(bg=TRANSPARENT, padx=0, pady=0)
        self.root.after(2000, self._keep_on_top)
        self.root.bind("<Enter>", self._on_hover_enter)
        self.root.bind("<Leave>", self._on_hover_leave)

    def _build_fonts(self):
        self.font_label = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self.font_node = tkfont.Font(family="Segoe UI", size=8, weight="bold")
        self.font_msg = tkfont.Font(family="Segoe UI", size=9)
        self.font_panel = tkfont.Font(family="Segoe UI", size=9)
        self.font_panel_bold = tkfont.Font(family="Segoe UI", size=9, weight="bold")

    def _build_canvas(self):
        self.root.update_idletasks()
        hwnd = self.root.winfo_id()
        self._hwnd = user32.GetParent(hwnd) or hwnd
        self._scale = _get_dpi_scale(self.root)

        self.canvas = tk.Canvas(
            self.root,
            bg=TRANSPARENT,
            highlightthickness=0,
            width=1,
            height=1,
            borderwidth=0,
        )
        self.canvas.place(x=0, y=0)
        self.canvas.bind("<Button-3>", self._show_context_menu)
        self.canvas.bind("<Button-1>", self._drag_start)
        self.canvas.bind("<B1-Motion>", self._drag_motion)
        self.canvas.bind("<Enter>", self._on_hover_enter)
        self.canvas.bind("<Leave>", self._on_hover_leave)

    def _build_text_panel(self):
        self.panel_frame = tk.Frame(self.root, bg=PANEL_BG, bd=0, highlightthickness=0)

        self.panel_title = tk.Label(
            self.panel_frame,
            text="APRIL",
            bg=PANEL_BG,
            fg=TEXT,
            font=self.font_label,
            anchor="w",
        )
        self.panel_mode = tk.Label(
            self.panel_frame,
            text="TEXT",
            bg="#1d242b",
            fg="#8fb4d8",
            font=self.font_node,
            padx=8,
            pady=2,
        )
        self.panel_close = tk.Button(
            self.panel_frame,
            text="x",
            command=self._collapse_text_panel,
            bg=PANEL_BG,
            fg=MUTED,
            activebackground="#1a1d21",
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=self.font_panel_bold,
            cursor="hand2",
        )

        self.output_text = tk.Text(
            self.panel_frame,
            bg=FIELD_BG,
            fg=TEXT,
            insertbackground=TEXT,
            selectbackground="#2d4158",
            selectforeground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=FIELD_BORDER,
            highlightcolor=FIELD_BORDER,
            font=self.font_panel,
            wrap="word",
            padx=10,
            pady=8,
            height=7,
            state="disabled",
            cursor="arrow",
        )
        self.output_text.tag_configure("user", foreground="#dce8f7", spacing1=6, spacing3=2)
        self.output_text.tag_configure("assistant", foreground="#f4f6f8", spacing1=6, spacing3=2)
        self.output_text.tag_configure("system", foreground=MUTED, spacing1=6, spacing3=2)

        self.input_var = tk.StringVar()
        self.input_entry = tk.Entry(
            self.panel_frame,
            textvariable=self.input_var,
            bg=FIELD_BG,
            fg=TEXT,
            insertbackground=TEXT,
            selectbackground="#2d4158",
            selectforeground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=FIELD_BORDER,
            highlightcolor="#4d6f92",
            font=self.font_panel,
        )
        self.send_button = tk.Button(
            self.panel_frame,
            text="Send",
            command=self._submit_text,
            bg="#223348",
            fg=TEXT,
            activebackground="#2c4564",
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=self.font_panel_bold,
            cursor="hand2",
        )

        self.input_entry.bind("<Return>", self._submit_text)
        self.input_entry.bind("<Escape>", lambda _event: self._collapse_text_panel())
        self.input_var.trace_add("write", lambda *_args: self._sync_send_state())
        self._sync_send_state()
        for widget in (self.panel_frame, self.panel_title, self.panel_mode, self.panel_close, self.output_text, self.input_entry, self.send_button):
            widget.bind("<Enter>", self._on_hover_enter)
            widget.bind("<Leave>", self._on_hover_leave)

    def _ellipsize(self, text, font, max_width):
        if not text or font.measure(text) <= max_width:
            return text
        ellipsis = "..."
        available = max_width - font.measure(ellipsis)
        trimmed = text
        while trimmed and font.measure(trimmed) > available:
            trimmed = trimmed[:-1]
        return trimmed.rstrip() + ellipsis

    def _wrap_text(self, text, font, max_width):
        clean = " ".join(str(text).strip().split())
        if not clean:
            return "", 0, 0

        lines = []
        current = ""
        for word in clean.split(" "):
            candidate = word if not current else f"{current} {word}"
            if font.measure(candidate) <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
                current = ""
            if font.measure(word) <= max_width:
                current = word
                continue

            chunk = ""
            for char in word:
                candidate = chunk + char
                if chunk and font.measure(candidate) > max_width:
                    lines.append(chunk)
                    chunk = char
                else:
                    chunk = candidate
            current = chunk

        if current:
            lines.append(current)

        wrapped = "\n".join(lines)
        width = max((font.measure(line) for line in lines), default=0)
        return wrapped, width, len(lines)

    def _context_chip(self):
        if self._node:
            return self._node.upper()
        if self._state == "idle":
            return ""
        if not self.config.get("at_home", True):
            return "AWAY"
        if not self.config.get("voice", True):
            return "VOICE OFF"
        return ""

    def _text_panel_active(self):
        return not self.config.get("voice", True)

    def _measure_layout(self):
        if self._text_panel_active():
            return {
                "state": STATES.get(self._state, STATES["idle"]),
                "label": "APRIL",
                "node": "TEXT",
                "message": "",
                "w": PANEL_WIDTH,
                "h": PANEL_HEIGHT,
                "radius": PANEL_RADIUS,
                "collapsed": False,
                "panel": True,
                "anchor": "bottom",
            }

        state = STATES.get(self._state, STATES["idle"])
        label = state["label"]
        node = self._ellipsize(self._context_chip(), self.font_node, NODE_MAX_WIDTH)
        message, msg_row_w, msg_lines = self._wrap_text(self._message, self.font_msg, MESSAGE_WRAP_WIDTH)

        if self._collapsed and self._state == "idle" and not message:
            return {
                "state": state,
                "label": "",
                "node": "",
                "message": "",
                "w": COLLAPSED_SIZE,
                "h": COLLAPSED_SIZE,
                "radius": COLLAPSED_SIZE // 2,
                "collapsed": True,
                "panel": False,
                "anchor": "center",
            }

        lh = self.font_label.metrics("linespace")
        mh = self.font_msg.metrics("linespace")
        lw = self.font_label.measure(label)
        nw = self.font_node.measure(node) if node else 0
        node_w = nw + NODE_PAD_X * 2 if node else 0

        label_row_w = ICON_SIZE + ICON_GAP + lw + (NODE_GAP + node_w if node else 0)
        content_w = max(label_row_w, msg_row_w)
        content_h = lh + (MSG_GAP + (mh * msg_lines) if message else 0)

        h = content_h + PAD_Y * 2
        radius = min(RADIUS, h // 2)
        min_width = IDLE_MIN_WIDTH if self._state == "idle" else MIN_WIDTH
        w = min(MAX_WIDTH, max(min_width, content_w + PAD_X * 2, radius * 2 + 1))
        if w % 2:
            w = w + 1 if w < MAX_WIDTH else w - 1

        return {
            "state": state,
            "label": label,
            "node": node,
            "message": message,
            "w": w,
            "h": h,
            "radius": radius,
            "lh": lh,
            "mh": mh,
            "lw": lw,
            "nw": nw,
            "node_w": node_w,
            "label_row_w": label_row_w,
            "msg_lines": msg_lines,
            "collapsed": False,
            "panel": False,
            "anchor": "center",
        }

    def _redraw(self, animate=True):
        layout = self._measure_layout()
        if animate and self._display_w and self._display_h:
            self._animate_to(layout)
            return
        self._render_layout(layout, layout["w"], layout["h"])

    def _render_layout(self, layout, w, h):
        radius = min(layout["radius"], h // 2)
        self.canvas.delete("all")
        self._wave_ids = []
        self._dot_id = None
        self.canvas.config(width=w, height=h)
        self._set_position(w, h, radius, layout.get("anchor", "center"))
        self._draw_pill(w, h, radius)

        if layout.get("panel"):
            self._place_text_panel(w, h)
            self._display_w = w
            self._display_h = h
            return

        self._hide_text_panel()

        if layout["collapsed"]:
            self._draw_status_mark(w / 2, h / 2, layout["state"]["color"])
            self._display_w = w
            self._display_h = h
            return

        label_cy = PAD_Y + layout["lh"] // 2
        msg_top = PAD_Y + layout["lh"] + MSG_GAP
        row_x = (w - layout["label_row_w"]) / 2
        icon_cx = row_x + ICON_SIZE / 2
        text_x = row_x + ICON_SIZE + ICON_GAP

        self._draw_status_mark(icon_cx, label_cy, layout["state"]["color"])
        self.canvas.create_text(
            text_x,
            label_cy,
            text=layout["label"],
            font=self.font_label,
            fill=TEXT,
            anchor="w",
        )

        if layout["node"]:
            node_h = 18
            node_x1 = text_x + layout["lw"] + NODE_GAP
            node_x2 = node_x1 + layout["node_w"]
            self._draw_round_rect(
                node_x1,
                label_cy - node_h // 2,
                node_x2,
                label_cy + node_h // 2,
                9,
                fill="#1d242b",
                outline="#2b3641",
            )
            self.canvas.create_text(
                node_x1 + NODE_PAD_X,
                label_cy,
                text=layout["node"],
                font=self.font_node,
                fill="#8fb4d8",
                anchor="w",
            )

        if layout["message"]:
            self.canvas.create_text(
                w / 2,
                msg_top,
                text=layout["message"],
                font=self.font_msg,
                fill=MUTED,
                anchor="n",
                justify="center",
                width=MESSAGE_WRAP_WIDTH,
            )
        self._display_w = w
        self._display_h = h

    def _animate_to(self, layout):
        if self._anim_job:
            self.root.after_cancel(self._anim_job)
            self._anim_job = None

        start_w = self._display_w
        start_h = self._display_h
        target_w = layout["w"]
        target_h = layout["h"]
        steps = max(1, ANIM_MS // ANIM_STEP_MS)

        def ease(t):
            return 1 - pow(1 - t, 3)

        def frame(step=1):
            t = ease(step / steps)
            w = round(start_w + (target_w - start_w) * t)
            h = round(start_h + (target_h - start_h) * t)
            self._render_layout(layout, w, h)
            if step < steps:
                self._anim_job = self.root.after(ANIM_STEP_MS, lambda: frame(step + 1))
            else:
                self._anim_job = None
                self._render_layout(layout, target_w, target_h)

        frame()

    def _place_text_panel(self, w, h):
        frame_w = max(1, w - 2)
        frame_h = max(1, h - 2)
        inner_x = PANEL_PAD
        inner_w = max(120, frame_w - PANEL_PAD * 2)
        header_y = PANEL_PAD
        output_y = header_y + PANEL_HEADER_H
        input_y = frame_h - PANEL_PAD - PANEL_INPUT_H
        output_h = max(80, input_y - output_y - PANEL_GAP)
        button_w = 66
        entry_w = inner_w - button_w - PANEL_GAP

        self.panel_frame.place(x=1, y=1, width=frame_w, height=frame_h)
        self.panel_title.place(x=inner_x, y=header_y + 5, width=120, height=24)
        self.panel_mode.place(x=frame_w - PANEL_PAD - 58, y=header_y + 7, width=58, height=22)
        self.panel_close.place(x=frame_w - PANEL_PAD - 94, y=header_y + 4, width=28, height=28)
        self.output_text.place(x=inner_x, y=output_y, width=inner_w, height=output_h)
        self.input_entry.place(x=inner_x, y=input_y, width=entry_w, height=PANEL_INPUT_H)
        self.send_button.place(x=inner_x + entry_w + PANEL_GAP, y=input_y, width=button_w, height=PANEL_INPUT_H)

    def _hide_text_panel(self):
        if self.panel_frame.winfo_ismapped():
            self.panel_frame.place_forget()

    def _focus_text_input(self):
        if self._text_panel_active():
            self.input_entry.focus_set()

    def _sync_send_state(self):
        has_text = bool(self.input_var.get().strip())
        self.send_button.config(
            state="normal" if has_text else "disabled",
            bg="#223348" if has_text else "#1b2027",
            fg=TEXT if has_text else "#59616b",
        )

    def _append_output(self, role, text):
        clean = " ".join(str(text).strip().split())
        if not clean:
            return
        self._history.append((role, clean))
        self._history = self._history[-40:]

        self.output_text.config(state="normal")
        self.output_text.delete("1.0", "end")
        for item_role, item_text in self._history:
            label = "You" if item_role == "user" else "APRIL" if item_role == "assistant" else "System"
            tag = item_role if item_role in {"user", "assistant"} else "system"
            self.output_text.insert("end", f"{label}: {item_text}\n", tag)
        self.output_text.config(state="disabled")
        self.output_text.see("end")

    def add_text_output(self, text, role="assistant"):
        self.root.after(0, lambda: self._append_output(role, text))

    def _submit_text(self, event=None):
        text = self.input_var.get().strip()
        if not text:
            return "break"
        self.input_var.set("")
        self._append_output("user", text)
        self._append_output("system", "Queued")

        if self.on_text_submit:
            try:
                response = self.on_text_submit(text)
            except Exception as exc:
                self._append_output("system", f"text submit failed: {exc}")
            else:
                if response:
                    self._append_output("assistant", response)
        else:
            self._append_output("assistant", "Text input is ready. The assistant pipeline can plug in here.")
        return "break"

    def _collapse_text_panel(self):
        self._set_config("voice", True)

    def _draw_round_rect(self, x1, y1, x2, y2, radius, fill, outline):
        r = radius
        c = self.canvas
        c.create_arc(x1, y1, x1 + r * 2, y1 + r * 2, start=90, extent=90, fill=fill, outline=outline)
        c.create_arc(x2 - r * 2, y1, x2, y1 + r * 2, start=0, extent=90, fill=fill, outline=outline)
        c.create_arc(x1, y2 - r * 2, x1 + r * 2, y2, start=180, extent=90, fill=fill, outline=outline)
        c.create_arc(x2 - r * 2, y2 - r * 2, x2, y2, start=270, extent=90, fill=fill, outline=outline)
        c.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline=fill)
        c.create_rectangle(x1, y1 + r, x2, y2 - r, fill=fill, outline=fill)

    def _draw_pill(self, w, h, radius):
        self._draw_round_rect(0, 0, w, h, radius, fill=BG, outline=BG)
        self.canvas.create_arc(1, 1, radius * 2, radius * 2, start=90, extent=90, outline=BORDER, style="arc", width=1)
        self.canvas.create_arc(w - radius * 2, 1, w - 1, radius * 2, start=0, extent=90, outline=BORDER, style="arc", width=1)
        self.canvas.create_arc(1, h - radius * 2, radius * 2, h - 1, start=180, extent=90, outline=BORDER, style="arc", width=1)
        self.canvas.create_arc(w - radius * 2, h - radius * 2, w - 1, h - 1, start=270, extent=90, outline=BORDER, style="arc", width=1)
        self.canvas.create_line(radius, 1, w - radius, 1, fill=HIGHLIGHT, width=1)
        self.canvas.create_line(radius, h - 1, w - radius, h - 1, fill=BORDER, width=1)

    def _draw_status_mark(self, cx, cy, color):
        r = ICON_SIZE // 2
        self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill="#1c2024", outline="#30353b")
        if self._state == "listening":
            heights = [
                8 + int(4 * math.sin((self._motion_phase + i) * 0.9))
                for i in range(3)
            ]
            for i, height in enumerate(heights):
                x = cx - 5 + i * 5
                self.canvas.create_line(
                    x,
                    cy - height // 2,
                    x,
                    cy + height // 2,
                    fill=color,
                    width=3,
                    capstyle=tk.ROUND,
                )
        elif self._state == "thinking":
            for i in range(4):
                angle = (self._motion_phase * 0.55) + (i * math.pi / 2)
                alpha_color = color if i == self._motion_phase % 4 else "#6c5329"
                x = cx + math.cos(angle) * 5
                y = cy + math.sin(angle) * 5
                self.canvas.create_oval(x - 2, y - 2, x + 2, y + 2, fill=alpha_color, outline=alpha_color)
        elif self._state == "speaking":
            pulse = 1 + (self._motion_phase % 5)
            self.canvas.create_oval(
                cx - 4 - pulse,
                cy - 4 - pulse,
                cx + 4 + pulse,
                cy + 4 + pulse,
                outline="#234c7c",
                width=1,
            )
            self._dot_id = self.canvas.create_oval(cx - 5, cy - 5, cx + 5, cy + 5, fill=color, outline=color)
        elif self._state == "error":
            self.canvas.create_polygon(
                cx,
                cy - 7,
                cx - 7,
                cy + 6,
                cx + 7,
                cy + 6,
                fill="#3a2024",
                outline=color,
            )
            self.canvas.create_line(cx, cy - 2, cx, cy + 2, fill=color, width=2, capstyle=tk.ROUND)
            self.canvas.create_oval(cx - 1, cy + 4, cx + 1, cy + 6, fill=color, outline=color)
        else:
            self._dot_id = self.canvas.create_oval(
                cx - 5,
                cy - 5,
                cx + 5,
                cy + 5,
                fill=color,
                outline=color,
            )

    def _set_position(self, w, h, radius, anchor="center"):
        if self._anchor_x is None or self._anchor_y is None:
            left, top, right, bottom = _get_work_area()
            self._anchor_x = (left + right) / 2
            self._anchor_y = bottom - ANCHOR_FROM_BOTTOM
            self._anchor_bottom_y = self._anchor_y + 25
        x = round(self._anchor_x - w / 2)
        if anchor == "bottom":
            bottom_y = self._anchor_bottom_y if self._anchor_bottom_y is not None else self._anchor_y + 25
            y = round(bottom_y - h)
        else:
            y = round(self._anchor_y - h / 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        user32.SetWindowPos(
            self._hwnd,
            None,
            x,
            y,
            w,
            h,
            SWP_NOZORDER | SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )
        self.canvas.place(x=0, y=0, width=w, height=h)
        _set_window_region(self._hwnd, w, h, radius, self._scale)

    def set_state(self, state: str, message: str = "", node: str = ""):
        if self._collapse_job:
            self.root.after_cancel(self._collapse_job)
            self._collapse_job = None
        if self._message_clear_job:
            self.root.after_cancel(self._message_clear_job)
            self._message_clear_job = None
        self._collapsed = False
        self._state = state
        self._message = message
        self._node = node
        self.root.after(0, self._on_state_change)

    def _on_state_change(self):
        if self._pulse_job:
            self.root.after_cancel(self._pulse_job)
            self._pulse_job = None
        self._motion_phase = 0
        self._redraw()
        if self._state in {"listening", "thinking", "speaking"}:
            self._pulse()
        elif self._state == "idle" and not self._text_panel_active():
            if self._message:
                self._schedule_message_clear()
            else:
                self._schedule_collapse()

    def update_from_config(self):
        self.root.after(0, self._on_config_refresh)

    def _on_config_refresh(self):
        if self._collapse_job:
            self.root.after_cancel(self._collapse_job)
            self._collapse_job = None
        if self._message_clear_job:
            self.root.after_cancel(self._message_clear_job)
            self._message_clear_job = None
        self._collapsed = False
        self._redraw()
        if self._text_panel_active():
            self.root.after(120, self._focus_text_input)
        elif self._state == "idle":
            if self._message:
                self._schedule_message_clear()
            else:
                self._schedule_collapse()

    def run(self):
        self.root.mainloop()

    def destroy(self):
        self.root.after(0, self.root.destroy)

    def _schedule_collapse(self):
        if self._text_panel_active() or self._hovering:
            return
        if self._collapse_job:
            self.root.after_cancel(self._collapse_job)
        self._collapse_job = self.root.after(AUTO_COLLAPSE_MS, self._collapse_idle)

    def _schedule_message_clear(self):
        if self._text_panel_active() or self._hovering:
            return
        if self._message_clear_job:
            self.root.after_cancel(self._message_clear_job)
        self._message_clear_job = self.root.after(MESSAGE_HOLD_MS, self._clear_idle_message)

    def _collapse_idle(self):
        self._collapse_job = None
        if self._state == "idle" and not self._message:
            self._collapsed = True
            self._redraw()

    def _clear_idle_message(self):
        self._message_clear_job = None
        if self._hovering or self._state != "idle" or not self._message:
            return
        self._message = ""
        self._redraw()
        self._schedule_collapse()

    def _pulse(self):
        if self._state not in {"listening", "thinking", "speaking"}:
            return
        self._motion_phase += 1
        self._redraw(animate=False)
        self._pulse_job = self.root.after(180, self._pulse)

    def _keep_on_top(self):
        self.root.attributes("-topmost", True)
        self.root.after(2000, self._keep_on_top)

    def _drag_start(self, event):
        if self._collapsed:
            self._collapsed = False
            self._redraw()
        self._drag_x = event.x_root - self.root.winfo_x()
        self._drag_y = event.y_root - self.root.winfo_y()

    def _drag_motion(self, event):
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self.root.geometry(f"+{x}+{y}")
        self._anchor_x = x + self.root.winfo_width() / 2
        self._anchor_y = y + self.root.winfo_height() / 2
        self._anchor_bottom_y = y + self.root.winfo_height()

    def _on_hover_enter(self, _event=None):
        self._hovering = True
        if self._hover_sync_job:
            self.root.after_cancel(self._hover_sync_job)
            self._hover_sync_job = None
        if self._collapse_job:
            self.root.after_cancel(self._collapse_job)
            self._collapse_job = None
        if self._message_clear_job:
            self.root.after_cancel(self._message_clear_job)
            self._message_clear_job = None

    def _on_hover_leave(self, _event=None):
        if self._hover_sync_job:
            self.root.after_cancel(self._hover_sync_job)
        self._hover_sync_job = self.root.after(40, self._sync_hover_exit)

    def _sync_hover_exit(self):
        self._hover_sync_job = None
        pointer_x = self.root.winfo_pointerx()
        pointer_y = self.root.winfo_pointery()
        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        root_w = self.root.winfo_width()
        root_h = self.root.winfo_height()
        inside = root_x <= pointer_x <= root_x + root_w and root_y <= pointer_y <= root_y + root_h
        if inside:
            return
        self._hovering = False
        if self._state == "idle":
            if self._message:
                self._schedule_message_clear()
            else:
                self._schedule_collapse()

    def _show_context_menu(self, event):
        if self._collapsed:
            self._collapsed = False
            self._redraw()
        menu = tk.Menu(
            self.root,
            tearoff=0,
            bg="#222222",
            fg="#cccccc",
            activebackground="#333333",
            activeforeground="#ffffff",
            font=("Segoe UI", 9),
            bd=0,
        )

        voice_label = "Voice: ON" if self.config.get("voice", True) else "Voice: OFF"
        menu.add_command(label=voice_label, command=self._toggle_voice)

        home_label = "At Home: YES" if self.config.get("at_home", True) else "At Home: NO"
        menu.add_command(label=home_label, command=self._toggle_home)

        term_label = "Terminal: SHOW" if self.config.get("terminal_visible", True) else "Terminal: HIDE"
        menu.add_command(label=term_label, command=self._toggle_terminal)

        menu.add_separator()
        menu.add_command(label="Quit APRIL", command=self._quit)

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _toggle_voice(self):
        self._set_config("voice", not self.config.get("voice", True))

    def _toggle_home(self):
        self._set_config("at_home", not self.config.get("at_home", True))

    def _toggle_terminal(self):
        self._set_config("terminal_visible", not self.config.get("terminal_visible", True))

    def _set_config(self, key, value):
        self.config[key] = value
        self._write_config()
        if key == "voice":
            self.update_from_config()
        if self.on_config_change:
            self.on_config_change(key, value)

    def _write_config(self):
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            self.set_state("error", f"config write failed: {e}")

    def _quit(self):
        self.root.destroy()


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

    w = APRILWidget(dummy_config, on_config_change=on_change, on_text_submit=on_submit)

    def demo():
        time.sleep(1)
        w.set_state("listening", node="mac")
        time.sleep(3)
        w.set_state("thinking", node="mac")
        time.sleep(2)
        w.set_state("speaking", node="mac", message="opening spotify")
        time.sleep(2)
        w.set_state("error", message="ollama unreachable")
        time.sleep(2)
        w.set_state("idle")
        time.sleep(2)

        dummy_config["voice"] = False
        w.update_from_config()
        time.sleep(0.5)
        w.add_text_output("Voice is off. Text replies will appear here.", role="assistant")
        time.sleep(1)
        w.root.after(0, lambda: w.input_var.set("summarize today's plan"))
        time.sleep(0.5)
        w.root.after(0, w._submit_text)
        time.sleep(3)
        dummy_config["voice"] = True
        w.update_from_config()
        w.set_state("idle")

    threading.Thread(target=demo, daemon=True).start()
    w.run()
