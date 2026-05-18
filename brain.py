"""
brain.py - Minimal APRIL response generation via Ollama.

This MVP version keeps the pipeline intentionally small: send the user's text
to the configured Ollama chat endpoint and return a concise reply. Intent
classification and tool execution can layer on later.
"""

from __future__ import annotations

from typing import Any


DEFAULT_TIMEOUT_SECONDS = 30
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
    return DEFAULT_SYSTEM_PROMPT
