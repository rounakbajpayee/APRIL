"""
screen_capture.py - Screenshot and vision query helper for APRIL.

Routes all vision requests through the local Lens vision service.
Configured via `vision_host` in config (e.g. http://192.168.0.234:8004).
"""

from __future__ import annotations

import io
from typing import Any

_VLM_MAX_WIDTH = 1280  # downsample before sending — VLM doesn't need full resolution


def _downscale_png(img_bytes: bytes, max_width: int = _VLM_MAX_WIDTH) -> bytes:
    """Resize screenshot to max_width if wider, preserving aspect ratio."""
    try:
        import cv2
        import numpy as np

        arr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return img_bytes
        h, w = img.shape[:2]
        if w <= max_width:
            return img_bytes
        scale = max_width / w
        resized = cv2.resize(
            img, (max_width, int(h * scale)), interpolation=cv2.INTER_AREA
        )
        ok, buf = cv2.imencode(".png", resized)
        return buf.tobytes() if ok else img_bytes
    except Exception:
        return img_bytes


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

    img_bytes = _downscale_png(img_bytes)

    try:
        response = requests.post(
            f"{vision_host}/v1/vision/analyze",
            files={"file": ("screenshot.png", io.BytesIO(img_bytes), "image/png")},
            params={
                "prompt": f"The user is asking about their current screen: {question} Answer based only on what is visible in this screenshot."
            },
            timeout=float(config.get("vision_timeout_seconds", 90)),
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        return f"Vision request failed: {exc}"

    text = str(data.get("text", "") or "").strip()
    clean = " ".join(text.split())
    return clean or "I captured the screen, but I couldn't get a useful vision reply."
