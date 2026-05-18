"""
browser.py - Browser and search intent handling.
"""

from __future__ import annotations

import os
import subprocess
import urllib.parse
import webbrowser
from typing import Any


def handle(action: dict[str, Any], _config: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    mode = str(action.get("mode", "") or "").strip().lower()
    if mode == "open_url":
        url = str(action.get("url", "") or "").strip()
        if not url:
            return {"reply": "I need a URL to open.", "config_changed": False}
        _open_visible(url)
        return {"reply": f"Opening {url}.", "config_changed": False}

    if mode == "search_youtube":
        query = str(action.get("query", "") or "").strip()
        if not query:
            return {"reply": "I need a YouTube search query.", "config_changed": False}
        url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
        _open_visible(url)
        return {"reply": f"Searching YouTube for {query}.", "config_changed": False}

    if mode == "search_web":
        query = str(action.get("query", "") or "").strip()
        if not query:
            query = str((context or {}).get("text", "") or "").strip()
        if not query:
            return {"reply": "I need a web search query.", "config_changed": False}
        url = "https://www.google.com/search?q=" + urllib.parse.quote(query)
        _open_visible(url)
        return {"reply": f"Searching the web for {query}.", "config_changed": False}

    return {"reply": "I understood that as a browser request, but I couldn't map the action yet.", "config_changed": False}


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
