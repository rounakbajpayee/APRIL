"""
device_control.py - Lightweight Windows device controls for APRIL phase 1.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import webbrowser
from typing import Any

APP_TARGETS = {
    "spotify": "spotify",
    "terminal": "wt",
    "powershell": "powershell",
    "cmd": "cmd",
    "notepad": "notepad",
    "calculator": "calc",
    "settings": "ms-settings:",
    "explorer": "explorer",
    "chrome": "chrome",
    "vscode": "code",
    "visual studio code": "code",
}
VK_MAP = {
    "play_pause": 0xB3,
    "next": 0xB0,
    "prev": 0xB1,
    "mute": 0xAD,
}


def perform(action: dict[str, Any]) -> str:
    mode = str(action.get("mode", "") or "").strip().lower()
    if mode == "set_volume":
        return set_volume(int(action.get("level", 0)))
    if mode == "adjust_volume":
        return adjust_volume(int(action.get("delta", 0)))
    if mode == "set_brightness":
        return set_brightness(int(action.get("level", 0)))
    if mode == "adjust_brightness":
        return adjust_brightness(int(action.get("delta", 0)))
    if mode == "open_app":
        return open_app(str(action.get("app", "") or ""))
    if mode == "media_key":
        return media_key(str(action.get("key", "") or ""))
    return "I understood that as a device request, but I couldn't map the action yet."


def set_volume(level: int) -> str:
    target = max(0, min(100, int(level)))
    try:
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    except ImportError:
        return "Volume control dependencies are not installed yet."

    devices = AudioUtilities.GetSpeakers()
    volume = _get_endpoint_volume(devices, IAudioEndpointVolume)
    if volume is None:
        return "Volume control dependencies are not installed yet."
    volume.SetMasterVolumeLevelScalar(target / 100.0, None)
    return f"Volume set to {target} percent."


def adjust_volume(delta: int) -> str:
    try:
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    except ImportError:
        return "Volume control dependencies are not installed yet."

    devices = AudioUtilities.GetSpeakers()
    volume = _get_endpoint_volume(devices, IAudioEndpointVolume)
    if volume is None:
        return "Volume control dependencies are not installed yet."
    current = round(volume.GetMasterVolumeLevelScalar() * 100)
    target = max(0, min(100, current + int(delta)))
    volume.SetMasterVolumeLevelScalar(target / 100.0, None)
    return f"Volume set to {target} percent."


def set_brightness(level: int) -> str:
    target = max(0, min(100, int(level)))
    try:
        import screen_brightness_control as sbc
    except ImportError:
        return "Brightness control dependency is not installed yet."
    try:
        sbc.set_brightness(target)
    except Exception as exc:
        return f"I couldn't set brightness: {exc}"
    return f"Brightness set to {target} percent."


def adjust_brightness(delta: int) -> str:
    try:
        import screen_brightness_control as sbc
    except ImportError:
        return "Brightness control dependency is not installed yet."
    try:
        current = int(sbc.get_brightness(display=0)[0])
        target = max(0, min(100, current + int(delta)))
        sbc.set_brightness(target)
    except Exception as exc:
        return f"I couldn't adjust brightness: {exc}"
    return f"Brightness set to {target} percent."


def open_app(app_name: str) -> str:
    clean = app_name.strip().lower()
    target = APP_TARGETS.get(clean)
    if not target:
        return f"I don't have an app mapping for {app_name} yet."
    if target.endswith(":") or target.startswith("http"):
        webbrowser.open(target)
    else:
        try:
            if os.name == "nt":
                subprocess.Popen(
                    ["cmd", "/c", "start", "", target],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    startupinfo=_startupinfo(),
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            else:
                subprocess.Popen(
                    [target],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    startupinfo=_startupinfo(),
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
        except Exception as exc:
            return f"I couldn't open {clean}: {exc}"
    return f"Opening {clean}."


def media_key(action: str) -> str:
    vk = VK_MAP.get(action)
    if not vk:
        return "That media key action is not available yet."
    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
    ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
    return {
        "play_pause": "Toggled playback.",
        "next": "Skipped to the next track.",
        "prev": "Went back a track.",
        "mute": "Toggled mute.",
    }.get(action, "Done.")


def _startupinfo():
    startupinfo = None
    if hasattr(subprocess, "STARTUPINFO"):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
    return startupinfo


def _get_endpoint_volume(devices, endpoint_volume_type):
    endpoint_volume = getattr(devices, "EndpointVolume", None)
    if endpoint_volume is not None:
        return endpoint_volume

    try:
        from ctypes import POINTER, cast
        from comtypes import CLSCTX_ALL
    except ImportError:
        return None

    activate = getattr(devices, "Activate", None)
    if not callable(activate):
        return None
    try:
        interface = activate(endpoint_volume_type._iid_, CLSCTX_ALL, None)
    except Exception:
        return None
    try:
        return cast(interface, POINTER(endpoint_volume_type))
    except Exception:
        return None
