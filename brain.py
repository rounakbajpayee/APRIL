"""
brain.py - Minimal APRIL response generation via Ollama.

This MVP version keeps the pipeline intentionally small: send the user's text
to the configured Ollama chat endpoint and return a concise reply. Intent
classification and tool execution can layer on later.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_TIMEOUT_SECONDS = 30
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_PROMPT_FILES = [
    "soul.md",
    "style.md",
    "capabilities.md",
    "rules.md",
]
DEFAULT_SYSTEM_PROMPT = (
    "You are APRIL, a concise home assistant running on a Windows laptop. "
    "Reply naturally in 1 to 3 short sentences. "
    "If the user asks for something you cannot verify or execute yet, say so plainly."
)


class BrainError(RuntimeError):
    pass


def respond(text: str, config: dict[str, Any]) -> str:
    clean = " ".join(str(text).strip().split())
    if not clean:
        return ""

    local_reply = _local_reply(clean, config)
    if local_reply:
        return local_reply

    ollama_host = str(config.get("ollama_host", "") or "").strip()
    ollama_model = str(config.get("ollama_model", "") or "").strip()
    if not ollama_host or not ollama_model:
        return "Brain is not configured yet."

    try:
        return _ollama_chat(clean, config)
    except Exception as exc:
        print(f"[brain] ollama request failed: {exc}")
        return "I heard you, but my brain service is unavailable right now."


def _ollama_chat(text: str, config: dict[str, Any]) -> str:
    try:
        import requests
    except ImportError as exc:
        raise BrainError("requests is not installed") from exc

    url = str(config.get("ollama_host", "")).rstrip("/") + "/api/chat"
    payload = {
        "model": str(config.get("ollama_model", "")).strip(),
        "stream": False,
        "messages": [
            {"role": "system", "content": _system_prompt(config)},
            {"role": "user", "content": text},
        ],
    }
    timeout = float(config.get("brain_timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    message = data.get("message") if isinstance(data, dict) else None
    if isinstance(message, dict):
        content = str(message.get("content", "") or "").strip()
        if content:
            return content
    raise BrainError("unexpected Ollama response payload")


def _system_prompt(config: dict[str, Any]) -> str:
    custom_prompt = str(config.get("brain_system_prompt", "") or "").strip()
    if custom_prompt:
        return custom_prompt
    prompt_from_files = _load_prompt_files(config)
    if prompt_from_files:
        return prompt_from_files
    return DEFAULT_SYSTEM_PROMPT


def _local_reply(text: str, config: dict[str, Any]) -> str:
    lowered = text.lower()

    if _looks_like_time_question(lowered):
        now = datetime.now().astimezone()
        return f"It's {now.strftime('%I:%M %p').lstrip('0')} on {now.strftime('%A, %B %d')}."

    if "what model" in lowered and "using" in lowered:
        model = str(config.get("ollama_model", "") or "").strip()
        if model:
            return f"I'm using the Ollama model {model}."
        return "I don't have a configured Ollama model right now."

    if "joke" in lowered:
        return "Why did the scarecrow win an award? Because he was outstanding in his field."

    return ""


def _looks_like_time_question(lowered: str) -> bool:
    if "time" not in lowered:
        return False
    time_markers = [
        "what time is it",
        "tell me the time",
        "current time",
        "time right now",
        "what's the time",
        "what is the time",
    ]
    if any(marker in lowered for marker in time_markers):
        return True
    return ("what" in lowered or "tell" in lowered) and "time" in lowered


def _load_prompt_files(config: dict[str, Any]) -> str:
    prompt_dir_name = str(config.get("brain_prompt_dir", "prompts") or "prompts").strip() or "prompts"
    prompt_dir = BASE_DIR / prompt_dir_name
    if not prompt_dir.exists() or not prompt_dir.is_dir():
        return ""

    configured_files = config.get("brain_prompt_files", DEFAULT_PROMPT_FILES)
    if isinstance(configured_files, str):
        filenames = [item.strip() for item in configured_files.split(",") if item.strip()]
    elif isinstance(configured_files, list):
        filenames = [str(item).strip() for item in configured_files if str(item).strip()]
    else:
        filenames = list(DEFAULT_PROMPT_FILES)

    sections = []
    for filename in filenames:
        path = prompt_dir / filename
        if not path.exists() or not path.is_file():
            continue
        try:
            body = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not body:
            continue
        sections.append(f"[{filename}]\n{body}")

    return "\n\n".join(sections).strip()
