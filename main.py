"""
main.py — APRIL Entry Point (stub)
Loads config, starts widget. All other subsystems stubbed for now.
Build order: widget ✓ → input_handler → stt → brain → tts → sessions → intents
"""

import json
import os
import sys

from stt import transcribe

# ── Config ────────────────────────────────────────────────────────────────────

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH  = os.path.join(BASE_DIR, "config.json")
DEFAULT_PATH = os.path.join(BASE_DIR, "config_defaults.json")


def load_config() -> dict:
    config = {}
    if os.path.exists(DEFAULT_PATH):
        with open(DEFAULT_PATH) as f:
            config.update(json.load(f))
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            config.update(json.load(f))
        return config
    if config:
        return config
    # Minimal fallback so widget can start
    return {
        "voice": True,
        "at_home": True,
        "tts_engine": "auto",
        "terminal_visible": True,
        "active_sessions": [],
        "ollama_host": "http://192.168.0.234:11434",
        "ollama_model": "gemma4:e2b",
        "whisper_host": "http://192.168.0.234:8001",
        "mac_ssh_host": "192.168.0.234",
        "mac_ssh_user": "homelab",
        "dell_ssh_host": "192.168.0.162",
        "dell_ssh_user": "homelab",
        "jellyfin_host": "http://media.home.lan",
        "jellyfin_api_key": "",
        "gemini_api_key": "",
        "vision_model": "gemini-2.5-flash",
        "audio_sample_rate": 16000,
        "audio_channels": 1,
        "audio_chunk_size": 1024,
        "copilot_hold_threshold": 0.3,
        "copilot_double_tap_window": 0.4,
        "copilot_min_audio_seconds": 0.5,
        "suppress_copilot": False,
    }


# ── Config change handler (called by widget context menu) ─────────────────────

def on_config_change(key, value):
    """
    Called whenever the widget writes a config change.
    Stub for now — subsystems will hook in here as they're built.
    """
    print(f"[main] config changed: {key} = {value}")
    # Future hooks:
    # if key == "at_home": session_manager.handle_home_change(value)
    # if key == "terminal_visible": session_manager.show/hide panes
    # if key == "voice": tts.handle_voice_change(value)


# ── Main ──────────────────────────────────────────────────────────────────────

def handle_user_text(text: str, source: str = "text"):
    """
    Shared text entry point for typed input and future STT transcripts.
    """
    print(f"[main] user text ({source}): {text}")
    return "APRIL heard you. The brain pipeline will attach here next."


def on_text_submit(text: str):
    """
    Called when the widget text panel submits a message.
    Stub for now - the real assistant pipeline will route this like transcribed speech.
    """
    return handle_user_text(text, source="text")


def on_audio_captured(audio_bytes: bytes, duration: float):
    """
    Called when the Copilot-key audio handler captures a WAV payload.
    """
    size_kb = len(audio_bytes) / 1024
    print(f"[main] audio captured: {duration:.2f}s, {size_kb:.1f} KiB WAV")
    config = load_config()
    transcript = transcribe(audio_bytes, config)
    if not transcript.strip():
        print("[main] transcription unavailable")
        return "I captured that, but I couldn't transcribe it."

    print(f"[main] transcript: {transcript}")
    return handle_user_text(transcript, source="voice")


def main():
    config = load_config()
    print(f"[main] config loaded — at_home={config.get('at_home')}, voice={config.get('voice')}")

    # Import widget here so tkinter only touches the main thread
    from widget import APRILWidget
    widget = APRILWidget(config, on_config_change=on_config_change, on_text_submit=on_text_submit)

    print("[main] widget started — APRIL is idle")
    # Subsystem init will go here between load_config and widget.run():
    from input_handler import start as start_input_handler
    input_handler = start_input_handler(widget, config, on_audio=on_audio_captured)
    # if config["voice"] and config["at_home"]: tts.open_mac_channel(config)
    # etc.

    try:
        widget.run()  # blocks until window closed
    finally:
        input_handler.stop()
    print("[main] widget closed — shutting down")


if __name__ == "__main__":
    main()
