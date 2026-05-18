"""
tts.py - Minimal APRIL text-to-speech routing.

This MVP version favors a local Windows SAPI path so APRIL can speak replies
without depending on remote infrastructure.
"""

from __future__ import annotations

import os
import subprocess
import threading
from typing import Any


_speak_lock = threading.Lock()


def speak(text: str, config: dict[str, Any]) -> bool:
    clean = " ".join(str(text).strip().split())
    if not clean or not bool(config.get("voice", True)):
        return False

    threading.Thread(target=_speak_blocking, args=(clean, dict(config)), daemon=True).start()
    return True


def _speak_blocking(text: str, config: dict[str, Any]) -> None:
    with _speak_lock:
        engine = resolve_engine(config)
        try:
            if engine == "sapi":
                _speak_sapi(text, config)
            else:
                print(f"[tts] engine unavailable: {engine}")
        except Exception as exc:
            print(f"[tts] speak failed: {exc}")


def resolve_engine(config: dict[str, Any]) -> str:
    engine = str(config.get("tts_engine", "auto") or "auto").strip().lower()
    if engine and engine != "auto":
        return engine
    return "sapi"


def _speak_sapi(text: str, config: dict[str, Any]) -> None:
    startupinfo = None
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if os.name == "nt" and hasattr(subprocess, "STARTUPINFO"):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0

    escaped = text.replace("'", "''")
    rate = int(config.get("tts_rate", 0))
    volume = int(config.get("tts_volume", 100))
    command = (
        "Add-Type -AssemblyName System.Speech; "
        "$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$voice.Rate = {rate}; "
        f"$voice.Volume = {volume}; "
        f"$voice.Speak('{escaped}'); "
        "$voice.Dispose()"
    )
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            command,
        ],
        check=False,
        capture_output=True,
        text=True,
        startupinfo=startupinfo,
        creationflags=creationflags,
    )
