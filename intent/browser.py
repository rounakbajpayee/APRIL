"""
browser.py - Browser and search intent handling.
"""

from __future__ import annotations

import os
import re
import subprocess
import urllib.parse
import webbrowser
from typing import Any

from .tool_interface import IntentPlan, IntentResult


INTENT_NAME = "browser"
TRIGGERS = [
    "search for",
    "google",
    "search youtube for",
    "youtube search for",
    "find on youtube",
    "open youtube",
    "open google",
    "open gmail",
    "open github",
    "open reddit",
    "open spotify",
    "open jellyfin",
    "go to",
    "http://",
    "https://",
]
OLLAMA_DESCRIPTION = "Open websites or search the web or YouTube in the browser"

SITE_ALIASES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "reddit": "https://www.reddit.com",
    "spotify": "https://open.spotify.com",
    "jellyfin": "http://media.home.lan",
}


def match(text: str, lowered: str) -> IntentPlan | None:
    if url := _extract_url(text):
        return {
            "intent": INTENT_NAME,
            "response_preview": f"Opening {url}.",
            "action": {"mode": "open_url", "url": url, "text": text},
        }

    if any(marker in lowered for marker in ("search youtube for ", "youtube search for ", "find on youtube ")):
        query = lowered
        for marker in ("search youtube for ", "youtube search for ", "find on youtube "):
            if marker in query:
                query = query.split(marker, 1)[1].strip(" .")
                break
        if query:
            return {
                "intent": INTENT_NAME,
                "response_preview": f"Searching YouTube for {query}.",
                "action": {"mode": "search_youtube", "query": query, "text": text},
            }

    if lowered.startswith("search for ") or lowered.startswith("google "):
        query = text.split(" ", 2)[-1].strip()
        return {
            "intent": INTENT_NAME,
            "response_preview": f"Searching the web for {query}.",
            "action": {"mode": "search_web", "query": query, "text": text},
        }

    open_match = re.match(r"(?:open|go to) (.+)", lowered)
    if open_match:
        target = open_match.group(1).strip(" .")
        if target in SITE_ALIASES:
            return {
                "intent": INTENT_NAME,
                "response_preview": f"Opening {target}.",
                "action": {"mode": "open_url", "url": SITE_ALIASES[target], "text": text},
            }
        if "." in target and " " not in target:
            url = target if target.startswith(("http://", "https://")) else f"https://{target}"
            return {
                "intent": INTENT_NAME,
                "response_preview": f"Opening {target}.",
                "action": {"mode": "open_url", "url": url, "text": text},
            }

    return None


def execute(action: dict[str, Any], _config: dict[str, Any], context: dict[str, Any] | None = None) -> IntentResult:
    mode = str(action.get("mode", "") or "").strip().lower()
    if mode == "open_url":
        url = str(action.get("url", "") or "").strip()
        if not url:
            return {"reply": "I need a URL to open.", "config_changed": False, "ok": False, "error_kind": "browser_url_missing"}
        _open_visible(url)
        return {"reply": f"Opening {url}.", "config_changed": False, "ok": True}

    if mode == "search_youtube":
        query = str(action.get("query", "") or "").strip()
        if not query:
            return {"reply": "I need a YouTube search query.", "config_changed": False, "ok": False, "error_kind": "browser_query_missing"}
        url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
        _open_visible(url)
        return {"reply": f"Searching YouTube for {query}.", "config_changed": False, "ok": True}

    if mode == "search_web":
        query = str(action.get("query", "") or "").strip()
        if not query:
            query = str((context or {}).get("text", "") or "").strip()
        if not query:
            return {"reply": "I need a web search query.", "config_changed": False, "ok": False, "error_kind": "browser_query_missing"}
        url = "https://www.google.com/search?q=" + urllib.parse.quote(query)
        _open_visible(url)
        return {"reply": f"Searching the web for {query}.", "config_changed": False, "ok": True}

    return {
        "reply": "I understood that as a browser request, but I couldn't map the action yet.",
        "config_changed": False,
        "ok": False,
        "error_kind": "browser_unmapped_action",
    }


def handle(action: dict[str, Any], _config: dict[str, Any], context: dict[str, Any] | None = None) -> IntentResult:
    return execute(action, _config, context)


def _open_visible(url: str) -> None:
    if os.name == "nt":
        try:
            os.startfile(url)
            return
        except Exception:
            try:
                subprocess.Popen(
                    ["cmd", "/c", "start", "", url],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    startupinfo=_startupinfo(),
                )
                return
            except Exception:
                pass
    webbrowser.open(url)


def _startupinfo():
    startupinfo = None
    if os.name == "nt" and hasattr(subprocess, "STARTUPINFO"):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
    return startupinfo


def _extract_url(text: str) -> str:
    match = re.search(r"(https?://[^\s]+)", text)
    if match:
        return match.group(1)
    return ""
