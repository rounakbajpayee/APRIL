"""
stt.py - Speech-to-text helpers for APRIL.

APRIL prefers a remote Whisper-compatible HTTP endpoint and can fall back to a
local `whisper` CLI if the endpoint is unavailable.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from typing import Any


DEFAULT_TIMEOUT_SECONDS = 20


class TranscriptionError(RuntimeError):
    pass


def transcribe(audio_bytes: bytes, config: dict[str, Any]) -> str:
    """
    Convert WAV audio bytes into text.

    Returns an empty string when no transcript can be produced.
    """
    if not audio_bytes:
        return ""

    remote_error = None
    whisper_host = str(config.get("whisper_host", "") or "").strip()
    if whisper_host:
        try:
            return _transcribe_remote(audio_bytes, whisper_host)
        except Exception as exc:
            remote_error = exc

    try:
        return _transcribe_local(audio_bytes)
    except Exception:
        if remote_error:
            return ""
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
    whisper_path = shutil.which("whisper")
    if not whisper_path:
        raise TranscriptionError("local whisper CLI not found")

    with tempfile.TemporaryDirectory(prefix="april-stt-") as temp_dir:
        audio_path = os.path.join(temp_dir, "april_input.wav")
        with open(audio_path, "wb") as handle:
            handle.write(audio_bytes)

        command = [
            whisper_path,
            audio_path,
            "--model",
            "base",
            "--output_format",
            "txt",
            "--output_dir",
            temp_dir,
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=DEFAULT_TIMEOUT_SECONDS * 3,
        )
        if result.returncode != 0:
            raise TranscriptionError(result.stderr.strip() or "local whisper failed")

        transcript_path = os.path.join(temp_dir, "april_input.txt")
        if not os.path.exists(transcript_path):
            raise TranscriptionError("local whisper did not write a transcript")
        with open(transcript_path, encoding="utf-8") as handle:
            return handle.read().strip()
