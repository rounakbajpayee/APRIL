"""
screen_capture.py - Screenshot and Gemini vision helper for APRIL phase 1.
"""

from __future__ import annotations

import base64
from typing import Any


def capture_and_query(question: str, config: dict[str, Any]) -> str:
    api_key = str(config.get("gemini_api_key", "") or "").strip()
    if not api_key:
        return "Vision is not configured yet because the Gemini API key is missing."

    try:
        import google.generativeai as genai
        import mss
        import mss.tools
    except ImportError:
        return "Vision dependencies are not installed yet."

    try:
        with mss.mss() as sct:
            screenshot = sct.grab(sct.monitors[0])
            img_bytes = mss.tools.to_png(screenshot.rgb, screenshot.size)
    except Exception as exc:
        return f"I couldn't capture the screen: {exc}"

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(str(config.get("vision_model", "gemini-2.5-flash")))
        response = model.generate_content(
            [
                f"The user is asking about their current screen: {question}",
                "Answer based only on what is visible in this screenshot.",
                {
                    "mime_type": "image/png",
                    "data": base64.b64encode(img_bytes).decode("ascii"),
                },
            ]
        )
    except Exception as exc:
        return f"Vision request failed: {exc}"

    text = getattr(response, "text", "") or ""
    clean = " ".join(str(text).strip().split())
    return clean or "I captured the screen, but I couldn't get a useful vision reply."
