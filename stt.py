"""
stt.py - Speech-to-text helpers for APRIL.

APRIL can transcribe with either a local `whisper` CLI or a remote
Whisper-compatible HTTP endpoint.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


DEFAULT_TIMEOUT_SECONDS = 20
BASE_DIR = Path(__file__).resolve().parent


class TranscriptionError(RuntimeError):
    pass


def transcribe(audio_bytes: bytes, config: dict[str, Any]) -> str:
    """
    Convert WAV audio bytes into text.

    Returns an empty string when no transcript can be produced.
    """
    if not audio_bytes:
        return ""

    prefer_local = str(config.get("stt_mode", "local_first") or "local_first").strip().lower() != "remote_first"
    whisper_host = str(config.get("whisper_host", "") or "").strip()

    attempts = []
    if prefer_local:
        attempts.append(("local", lambda: _transcribe_local(audio_bytes)))
        if whisper_host:
            attempts.append(("remote", lambda: _transcribe_remote(audio_bytes, whisper_host)))
    else:
        if whisper_host:
            attempts.append(("remote", lambda: _transcribe_remote(audio_bytes, whisper_host)))
        attempts.append(("local", lambda: _transcribe_local(audio_bytes)))

    for _, attempt in attempts:
        try:
            text = attempt()
        except Exception:
            continue
        if text.strip():
            return text
    return ""


def _transcribe_remote(audio_bytes: bytes, whisper_host: str) -> str:
    try:
        import requests
    except ImportError as exc:
        raise TranscriptionError("requests is not installed") from exc

    url = whisper_host.rstrip("/") + "/v1/audio/transcriptions"
    files = {
        "file": ("april_input.wav", audio_bytes, "audio/wav"),
    }
    data = {
        "model": "whisper-1",
    }
    response = requests.post(url, files=files, data=data, timeout=DEFAULT_TIMEOUT_SECONDS)
    response.raise_for_status()
    return _extract_text(response)


def _extract_text(response) -> str:
    content_type = response.headers.get("content-type", "").lower()
    if "application/json" in content_type:
        payload = response.json()
        if isinstance(payload, dict):
            return str(payload.get("text", "") or "").strip()
        raise TranscriptionError("unexpected JSON payload from STT service")

    body = response.text.strip()
    if not body:
        return ""
    if body.startswith("{"):
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return body
        if isinstance(payload, dict):
            return str(payload.get("text", "") or "").strip()
    return body


def _transcribe_local(audio_bytes: bytes) -> str:
    whisper_path = _find_whisper_executable()
    if not whisper_path:
        raise TranscriptionError("local whisper CLI not found")
    model_name = str(_config_value("stt_local_model", "small.en")).strip() or "small.en"
    language = str(_config_value("stt_language", "en")).strip() or "en"
    initial_prompt = str(_config_value("stt_initial_prompt", "APRIL")).strip()

    with tempfile.TemporaryDirectory(prefix="april-stt-") as temp_dir:
        audio_path = os.path.join(temp_dir, "april_input.wav")
        with open(audio_path, "wb") as handle:
            handle.write(audio_bytes)

        command = [
            whisper_path,
            audio_path,
            "--model",
            model_name,
            "--language",
            language,
            "--output_format",
            "txt",
            "--output_dir",
            temp_dir,
        ]
        if initial_prompt:
            command.extend(["--initial_prompt", initial_prompt])
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=DEFAULT_TIMEOUT_SECONDS * 6,
            env=_build_local_whisper_env(),
            creationflags=_subprocess_creationflags(),
            startupinfo=_subprocess_startupinfo(),
        )
        if result.returncode != 0:
            raise TranscriptionError(result.stderr.strip() or "local whisper failed")

        transcript_path = os.path.join(temp_dir, "april_input.txt")
        if not os.path.exists(transcript_path):
            raise TranscriptionError("local whisper did not write a transcript")
        with open(transcript_path, encoding="utf-8") as handle:
            return handle.read().strip()


def _find_whisper_executable() -> str | None:
    candidates = [
        shutil.which("whisper"),
        str(BASE_DIR / ".venv" / "Scripts" / "whisper.exe"),
        str(BASE_DIR / ".venv" / "Scripts" / "whisper"),
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def _config_value(key: str, default):
    try:
        with open(BASE_DIR / "config.json", encoding="utf-8") as handle:
            current = json.load(handle)
        if key in current:
            return current[key]
    except Exception:
        pass
    try:
        with open(BASE_DIR / "config_defaults.json", encoding="utf-8") as handle:
            defaults = json.load(handle)
        return defaults.get(key, default)
    except Exception:
        return default


def _build_local_whisper_env() -> dict[str, str]:
    env = os.environ.copy()
    ffmpeg_dir = _ensure_ffmpeg_command_dir()
    if ffmpeg_dir:
        env["PATH"] = ffmpeg_dir + os.pathsep + env.get("PATH", "")
    return env


def _ensure_ffmpeg_command_dir() -> str | None:
    try:
        import imageio_ffmpeg
    except ImportError:
        return None

    try:
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None

    ffmpeg_dir = os.path.dirname(ffmpeg_path)
    if not ffmpeg_dir:
        return None

    ffmpeg_command = os.path.join(ffmpeg_dir, "ffmpeg.exe")
    if os.path.exists(ffmpeg_command):
        return ffmpeg_dir

    try:
        shutil.copyfile(ffmpeg_path, ffmpeg_command)
    except OSError:
        return None
    return ffmpeg_dir


def _subprocess_creationflags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _subprocess_startupinfo():
    startupinfo = None
    if os.name == "nt" and hasattr(subprocess, "STARTUPINFO"):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
    return startupinfo
