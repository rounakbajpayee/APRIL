"""
brain.py - APRIL routing and conversational reply helpers.

APRIL uses a hybrid approach:
- direct local handling for utility questions and obvious device/config/browser requests
- optional Ollama-backed JSON intent planning for more free-form requests
- Ollama-backed conversational replies and command summarization as fallback layers
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any

from debug_log import latest_event_value, summarize_recent_activity
from learning import apply_rewrites
from memory import summarize_recent
import semantic_store
from state_engine import get_prompt_context_summary, load_snapshot
import runtime_trace


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
SITE_ALIASES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "reddit": "https://www.reddit.com",
    "spotify": "https://open.spotify.com",
    "jellyfin": "http://media.home.lan",
}
APP_ALIASES = {
    "spotify",
    "terminal",
    "powershell",
    "cmd",
    "notepad",
    "calculator",
    "settings",
    "explorer",
    "vscode",
    "visual studio code",
    "chrome",
}


class BrainError(RuntimeError):
    pass


def process(text: str, config: dict[str, Any]) -> dict[str, Any]:
    clean = apply_rewrites(text)
    if not clean:
        return _conversation_plan("", "")

    # Capture enriched context for training data recording
    _state_context = get_prompt_context_summary(limit=int(config.get("state_context_timeline_limit", 6)))
    _memory_context = summarize_recent(limit=int(config.get("memory_context_turns", 6)))

    local_reply = _local_reply(clean, config)
    if local_reply:
        plan = {
            "intent": "conversation",
            "response_preview": local_reply,
            "action": {
                "mode": "direct_reply",
                "reply": local_reply,
                "text": clean,
            },
        }
        plan["_enriched_context"] = {"memory": _memory_context or "", "state": _state_context or ""}
        return plan

    local_plan = _local_plan(clean, config)
    if local_plan:
        local_plan["_enriched_context"] = {"memory": _memory_context or "", "state": _state_context or ""}
        return local_plan

    if _looks_like_conversation_question(clean):
        plan = _conversation_plan(clean, "")
        plan["_enriched_context"] = {"memory": _memory_context or "", "state": _state_context or ""}
        return plan

    llm_plan = _ollama_intent_plan(clean, config)
    if llm_plan:
        llm_plan["_enriched_context"] = {"memory": _memory_context or "", "state": _state_context or ""}
        return llm_plan

    plan = _conversation_plan(clean, "")
    plan["_enriched_context"] = {"memory": _memory_context or "", "state": _state_context or ""}
    return plan


def respond(text: str, config: dict[str, Any]) -> str:
    clean = apply_rewrites(text)
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
        runtime_trace.trace_event(
            "ollama_request_failed",
            subsystem="brain",
            severity=runtime_trace.ERROR,
            payload={"error": str(exc), "error_type": type(exc).__name__},
        )
        return "I heard you, but my brain service is unavailable right now."


def summarize_output(raw_output: str, original_request: str, config: dict[str, Any]) -> str:
    clean_output = str(raw_output or "").strip()
    if not clean_output:
        return "It finished without any output."
    if len(clean_output) <= 220 and clean_output.count("\n") <= 2:
        return clean_output

    ollama_host = str(config.get("ollama_host", "") or "").strip()
    ollama_model = str(config.get("ollama_model", "") or "").strip()
    if not ollama_host or not ollama_model:
        return _trim_output(clean_output)

    prompt = (
        f'User request: "{original_request}"\n'
        f"Raw output:\n{clean_output}\n\n"
        "Summarize this in 1 to 2 short natural sentences. "
        "Do not quote large blocks of terminal text."
    )
    try:
        return _ollama_chat(prompt, config)
    except Exception as exc:
        runtime_trace.trace_event(
            "summarize_output_failed",
            subsystem="brain",
            severity=runtime_trace.WARNING,
            payload={"error": str(exc)},
        )
        return _trim_output(clean_output)


def _ollama_chat(text: str, config: dict[str, Any]) -> str:
    state_context = get_prompt_context_summary(limit=int(config.get("state_context_timeline_limit", 6)))
    if state_context:
        text = f"{state_context}\n\nCurrent user message: {text}"
    recent_memory = summarize_recent(limit=int(config.get("memory_context_turns", 6)))
    if recent_memory:
        text = f"Recent conversation:\n{recent_memory}\n\n{text}"
    data = _ollama_chat_payload(
        user_content=text,
        config=config,
        system_content=_system_prompt(config),
    )
    message = data.get("message") if isinstance(data, dict) else None
    if isinstance(message, dict):
        content = str(message.get("content", "") or "").strip()
        if content:
            return content
    raise BrainError("unexpected Ollama response payload")


def _ollama_chat_payload(user_content: str, config: dict[str, Any], system_content: str) -> dict[str, Any]:
    try:
        import requests
    except ImportError as exc:
        raise BrainError("requests is not installed") from exc

    url = str(config.get("ollama_host", "")).rstrip("/") + "/api/chat"
    payload = {
        "model": str(config.get("ollama_model", "")).strip(),
        "stream": False,
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ],
    }
    timeout = float(config.get("brain_timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise BrainError("unexpected Ollama response payload")
    return data


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

    if any(marker in lowered for marker in ("what did we just discuss", "what were we talking about", "summarize our conversation")):
        recent = summarize_recent(limit=int(config.get("memory_context_turns", 6)))
        if recent:
            return recent
        return "We have not built up any recent conversation memory yet."

    if any(
        marker in lowered
        for marker in (
            "what just happened",
            "what happened just now",
            "recent activity",
            "show recent activity",
            "what have you been doing",
        )
    ):
        return summarize_recent_activity(limit=8)

    if any(marker in lowered for marker in ("what did you hear", "what did you transcribe", "what did i say")):
        transcript = latest_event_value("transcript", "transcript")
        if transcript:
            return f"The latest transcript I captured was: {transcript}"
        return "I don't have a recent transcript logged yet."

    if any(marker in lowered for marker in ("what did you do", "why did you do that", "what action did you take")):
        return summarize_recent_activity(limit=5)

    if any(
        marker in lowered
        for marker in (
            "what do you know right now",
            "what's my current context",
            "what is my current context",
            "what are you aware of",
            "what do you see about the current session",
        )
    ):
        summary = get_prompt_context_summary(limit=6)
        return summary or "I don't have enough state built up yet."

    if any(marker in lowered for marker in ("what are your open loops", "what is still unresolved")):
        snapshot = load_snapshot()
        open_loops = snapshot.get("open_loops", []) if isinstance(snapshot, dict) else []
        if open_loops:
            return "\n".join(f"- {item}" for item in open_loops[-5:])
        return "I don't have any unresolved loops in the current snapshot."

    if _looks_like_time_question(lowered):
        now = datetime.now().astimezone()
        return f"It's {now.strftime('%I:%M %p').lstrip('0')} on {now.strftime('%A, %B %d')}."

    if _looks_like_model_question(lowered):
        model = str(config.get("ollama_model", "") or "").strip()
        if model:
            return f"I'm using the Ollama model {model}."
        return "I don't have a configured Ollama model right now."

    if "joke" in lowered:
        return "Why did the scarecrow win an award? Because he was outstanding in his field."

    return ""


def _local_plan(text: str, config: dict[str, Any]) -> dict[str, Any] | None:
    from intent import registry as intent_registry

    lowered = text.lower()
    triggered_tools = intent_registry.iter_triggered_tools(lowered)

    for tool in triggered_tools:
        plan = tool.match(text, lowered)
        if plan:
            return plan

    for tool in intent_registry.tools():
        if tool.intent_name == "conversation":
            continue
        if tool in triggered_tools:
            continue
        plan = tool.match(text, lowered)
        if plan:
            return plan

    learned_plan = intent_registry.semantic_plan(text)
    if learned_plan:
        return learned_plan

    # Dynamic semantic routing layer (checks past confirmed examples/history)
    threshold = float(config.get("semantic_routing_threshold", 0.74))
    dynamic_plan = semantic_store.semantic_plan(text, confidence_threshold=threshold)
    if dynamic_plan:
        return dynamic_plan

    return None


def _ollama_intent_plan(text: str, config: dict[str, Any]) -> dict[str, Any] | None:
    from intent import registry as intent_registry

    ollama_host = str(config.get("ollama_host", "") or "").strip()
    ollama_model = str(config.get("ollama_model", "") or "").strip()
    if not ollama_host or not ollama_model:
        return None

    intent_lines = "\n".join(
        f"- {tool.intent_name}: {tool.ollama_description}"
        for tool in intent_registry.tools()
    )
    action_rules = "\n".join(_planner_action_rules(intent_registry))
    planner_prompt = (
        "Classify the request into one of these intents:\n"
        f"{intent_lines}\n\n"
        "Return JSON only with this shape:\n"
        "{\n"
        '  "intent": "...",\n'
        '  "response_preview": "short confirmation",\n'
        '  "action": { ... }\n'
        "}\n\n"
        "Action rules:\n"
        f"{action_rules}\n\n"
        f'User request: "{text}"'
    )

    try:
        data = _ollama_chat_payload(
            user_content=planner_prompt,
            config=config,
            system_content=(
                "You convert APRIL user requests into compact JSON plans. "
                "Return valid JSON only and no markdown."
            ),
        )
    except Exception as exc:
        runtime_trace.trace_event(
            "intent_plan_failed",
            subsystem="brain",
            severity=runtime_trace.WARNING,
            payload={"error": str(exc), "text": text[:120]},
        )
        return None

    message = data.get("message") if isinstance(data, dict) else None
    content = str(message.get("content", "") or "").strip() if isinstance(message, dict) else ""
    payload = _extract_json_object(content)
    if not isinstance(payload, dict):
        return None
    return _normalize_plan(payload, text)


def _normalize_plan(payload: dict[str, Any], original_text: str) -> dict[str, Any]:
    from intent import registry as intent_registry

    intent = str(payload.get("intent", "") or "").strip().lower()
    response_preview = str(payload.get("response_preview", "") or "").strip()
    action = payload.get("action")
    if not isinstance(action, dict):
        action = {}
    action.setdefault("text", original_text)
    if intent_registry.get(intent) is None:
        return _conversation_plan(original_text, "")
    if intent == "conversation":
        action.setdefault("text", original_text)
    return {
        "intent": intent,
        "response_preview": response_preview,
        "action": action,
    }


def _conversation_plan(text: str, preview: str) -> dict[str, Any]:
    return {
        "intent": "conversation",
        "response_preview": preview,
        "action": {
            "text": text,
        },
    }


def _planner_action_rules(intent_registry: Any) -> list[str]:
    action_rules = {
        "config": '- config: use keys like {"updates":{"voice":false}}',
        "device": "- device: use modes like set_volume, adjust_volume, set_brightness, open_app, media_key",
        "browser": "- browser: use modes like open_url, search_web, search_youtube",
        "shell": '- shell: include {"node":"local|mac|dell","command":"..."} when possible',
        "media": "- media: include title or mode like continue",
        "vision": '- vision: include {"question":"..."}',
        "conversation": '- conversation: include {"text":"original request"}',
    }
    lines: list[str] = []
    for tool in intent_registry.tools():
        rule = action_rules.get(tool.intent_name)
        if rule:
            lines.append(rule)
    return lines


def _extract_json_object(content: str) -> dict[str, Any] | None:
    clean = content.strip()
    if clean.startswith("```"):
        clean = clean.strip("`")
        if clean.lower().startswith("json"):
            clean = clean[4:].strip()
    try:
        payload = json.loads(clean)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    start = clean.find("{")
    end = clean.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            payload = json.loads(clean[start : end + 1])
        except json.JSONDecodeError:
            return None
        if isinstance(payload, dict):
            return payload
    return None


def _trim_output(clean_output: str) -> str:
    first_lines = clean_output.splitlines()
    if not first_lines:
        return "It finished without any output."
    trimmed = "\n".join(first_lines[:5]).strip()
    if len(trimmed) > 260:
        trimmed = trimmed[:257].rstrip() + "..."
    return trimmed


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


def _looks_like_model_question(lowered: str) -> bool:
    if "using" not in lowered:
        return False
    markers = [
        "what model",
        "which model",
        "what module",
        "which module",
        "model are you using",
        "module are you using",
    ]
    return any(marker in lowered for marker in markers)


def _looks_like_conversation_question(text: str) -> bool:
    lowered = text.lower().strip()
    if not lowered:
        return False
    if _looks_like_time_question(lowered) or _looks_like_model_question(lowered):
        return False

    if lowered.startswith(("what is ", "what are ", "who is ", "who are ", "how many ", "how much ", "tell me ", "explain ")):
        if any(marker in lowered for marker in ("on my screen", "current directory", "working directory", "documents folder", "downloads folder", "desktop folder", "open ", "run ", "go to ", "search ", "launch ", "start ", "volume", "brightness", "pause ", "mute ", "voice ", "terminal")):
            return False
        return True

    if lowered.endswith("?"):
        if any(marker in lowered for marker in ("open ", "search ", "run ", "connect to ", "volume", "brightness", "pause ", "mute ", "play ")):
            return False
        return True

    return False


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
