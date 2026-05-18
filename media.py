"""
media.py - Minimal Jellyfin/browser helpers for APRIL phase 1.
"""

from __future__ import annotations

import urllib.parse
import webbrowser
from typing import Any


def handle_media(action: dict[str, Any], config: dict[str, Any]) -> str:
    mode = str(action.get("mode", "") or "").strip().lower()
    jellyfin_host = str(config.get("jellyfin_host", "") or "").strip()
    if not jellyfin_host:
        return "Jellyfin host is not configured yet."

    if mode == "continue":
        webbrowser.open(jellyfin_host.rstrip("/") + "/web/")
        return "Opening Jellyfin so you can continue watching."

    if mode == "play":
        title = str(action.get("title", "") or "").strip()
        if not title:
            webbrowser.open(jellyfin_host.rstrip("/") + "/web/")
            return "Opening Jellyfin."
        search_url = jellyfin_host.rstrip("/") + "/web/#/search.html?query=" + urllib.parse.quote(title)
        webbrowser.open(search_url)
        return f"Opening Jellyfin search for {title}."

    webbrowser.open(jellyfin_host.rstrip("/") + "/web/")
    return "Opening Jellyfin."
