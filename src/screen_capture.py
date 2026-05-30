"""
screen_capture.py - Screenshot and vision query helper for APRIL.

Routes all vision requests through the local Lens vision service.
Configured via `vision_host` in config (e.g. http://192.168.0.234:8004).
"""

from __future__ import annotations

import io
from typing import Any


def capture_and_query(question: str, config: dict[str, Any]) -> str:
    vision_host = str(config.get("vision_host", "") or "").strip().rstrip("/")
    if not vision_host:
        return "Vision is not configured yet — set vision_host in config."

    try:
        import mss
        import mss.tools
        import requests
    except ImportError:
        return "Vision dependencies are not installed (mss, requests)."

    try:
        with mss.mss() as sct:
            screenshot = sct.grab(sct.monitors[0])
            img_bytes = mss.tools.to_png(screenshot.rgb, screenshot.size)
    except Exception as exc:
        return f"I couldn't capture the screen: {exc}"

    try:
        response = requests.post(
            f"{vision_host}/v1/vision/analyze",
            files={"file": ("screenshot.png", io.BytesIO(img_bytes), "image/png")},
            params={"prompt": f"The user is asking about their current screen: {question} Answer based only on what is visible in this screenshot."},
            timeout=float(config.get("vision_timeout_seconds", 30)),
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        return f"Vision request failed: {exc}"

    text = str(data.get("text", "") or "").strip()
    clean = " ".join(text.split())
    return clean or "I captured the screen, but I couldn't get a useful vision reply."
