"""
observer.py - Lightweight self and desktop awareness helpers for APRIL.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
from typing import Any


def collect_runtime_observation() -> dict[str, Any]:
    observation: dict[str, Any] = {
        "host_os": os.name,
        "pid": os.getpid(),
    }
    foreground = get_foreground_window_context()
    if foreground:
        observation["foreground"] = foreground
    return observation


def get_foreground_window_context() -> dict[str, Any]:
    if os.name != "nt":
        return {}

    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return {}

    title_buffer = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, title_buffer, len(title_buffer))
    title = str(title_buffer.value or "").strip()

    pid = ctypes.wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

    context: dict[str, Any] = {
        "window_title": title,
        "pid": int(pid.value),
    }
    if title:
        context["app_hint"] = _derive_app_hint(title)
    return context


def _derive_app_hint(title: str) -> str:
    if " - " in title:
        return title.rsplit(" - ", 1)[-1].strip()
    return title[:80].strip()
