"""
tts.py - Minimal APRIL text-to-speech routing.

This MVP version favors a local Windows SAPI path so APRIL can speak replies
without depending on remote infrastructure.
"""

from __future__ import annotations

import os
import subprocess
import threading
import shlex
from typing import Any, Callable

from session_manager import execute as execute_session_command


_speak_lock = threading.Lock()
_process_lock = threading.Lock()
_current_process = None
_kokoro_stop = threading.Event()


def speak(text: str, config: dict[str, Any], on_done: Callable[[bool], None] | None = None) -> bool:
    clean = " ".join(str(text).strip().split())
    if not clean or not bool(config.get("voice", True)):
        if on_done is not None:
            on_done(False)
        return False

    threading.Thread(target=_speak_blocking, args=(clean, dict(config), on_done), daemon=True).start()
    return True


def stop() -> None:
    global _current_process
    _kokoro_stop.set()
    with _process_lock:
        proc = _current_process
        _current_process = None
    if not proc:
        return
    try:
        proc.terminate()
    except Exception:
        return


def _speak_blocking(text: str, config: dict[str, Any], on_done: Callable[[bool], None] | None = None) -> None:
    with _speak_lock:
        engine = resolve_engine(config)
        ok = False
        try:
            if engine == "sapi":
                _speak_sapi(text, config)
                ok = True
            elif engine == "say":
                _speak_say(text, config)
                ok = True
            elif engine == "kokoro":
                _speak_kokoro(text, config)
                ok = True
            else:
                print(f"[tts] engine unavailable: {engine}")
        except Exception as exc:
            print(f"[tts] speak failed: {exc}")
        finally:
            if on_done is not None:
                try:
                    on_done(ok)
                except Exception:
                    pass


def resolve_engine(config: dict[str, Any]) -> str:
    engine = str(config.get("tts_engine", "auto") or "auto").strip().lower()
    if engine and engine != "auto":
        return engine
    return "sapi"


def _speak_kokoro(text: str, config: dict[str, Any]) -> None:
    import requests
    import pyaudio

    host = str(config.get("kokoro_host", "http://192.168.0.234:8002") or "http://192.168.0.234:8002").rstrip("/")
    url = f"{host}/v1/audio/speech"
    voice = str(config.get("tts_kokoro_voice", "bm_daniel") or "bm_daniel")
    speed = float(config.get("tts_kokoro_speed", 1.0) or 1.0)
    timeout = int(config.get("tts_timeout_seconds", 20) or 20)

    response = requests.post(
        url,
        json={"input": text, "voice": voice, "speed": speed},
        stream=True,
        timeout=timeout,
    )
    response.raise_for_status()

    audio_data = b"".join(response.iter_content(chunk_size=4096))

    # Kokoro uses 0xFFFFFFFF placeholder RIFF sizes — skip the 44-byte WAV header
    # and feed raw PCM directly. Format is always int16, mono, 24000 Hz.
    pcm = audio_data[44:]

    _kokoro_stop.clear()
    pa = pyaudio.PyAudio()
    try:
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=24000,
            output=True,
        )
        try:
            chunk = 4096
            for i in range(0, len(pcm), chunk):
                if _kokoro_stop.is_set():
                    break
                stream.write(pcm[i:i + chunk])
        finally:
            stream.stop_stream()
            stream.close()
    finally:
        pa.terminate()


def _speak_sapi(text: str, config: dict[str, Any]) -> None:
    global _current_process
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
    proc = subprocess.Popen(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            command,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        startupinfo=startupinfo,
        creationflags=creationflags,
    )
    with _process_lock:
        _current_process = proc
    try:
        proc.communicate()
    finally:
        with _process_lock:
            if _current_process is proc:
                _current_process = None


def _speak_say(text: str, config: dict[str, Any]) -> None:
    if os.name == "nt":
        node = str(config.get("tts_say_node", "mac") or "mac").strip().lower()
        command = "say " + shlex.quote(text)
        execute_session_command(node, command, config, timeout=int(config.get("tts_timeout_seconds", 20)))
        return

    startupinfo = None
    if hasattr(subprocess, "STARTUPINFO"):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
    subprocess.Popen(["say", text], startupinfo=startupinfo, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).wait()
