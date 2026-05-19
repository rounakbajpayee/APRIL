"""
Intent tool registry for APRIL.

The registry discovers self-registering intent modules and exposes:
- intent lookup for execution dispatch
- a trigger index for fast local routing
- Ollama planner descriptions assembled from registered tools

Legacy adapters keep the pre-registry tools routable during migration.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import pkgutil
import re
from pathlib import Path
from typing import Any, Callable, Iterable

from .tool_interface import IntentPlan, IntentResult, IntentTool, validate_tool


MatchFn = Callable[[str, str], IntentPlan | None]
ExecuteFn = Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], IntentResult]

_PACKAGE_DIR = Path(__file__).resolve().parent
_PACKAGE_NAME = __name__.rsplit(".", 1)[0]
_SKIP_MODULES = {"__init__", "registry", "tool_interface"}


@dataclass(frozen=True)
class RegisteredTool:
    intent_name: str
    triggers: tuple[str, ...]
    ollama_description: str
    match: MatchFn
    execute: ExecuteFn
    source: str


def _normalize_trigger(trigger: str) -> str:
    return " ".join(str(trigger or "").strip().lower().split())


def _trigger_head(trigger: str) -> str:
    parts = trigger.split(" ", 1)
    return parts[0] if parts else ""


def _registered_from_module(tool: IntentTool, source: str) -> RegisteredTool:
    triggers = tuple(_normalize_trigger(trigger) for trigger in tool.TRIGGERS if _normalize_trigger(trigger))
    return RegisteredTool(
        intent_name=tool.INTENT_NAME.strip().lower(),
        triggers=triggers,
        ollama_description=tool.OLLAMA_DESCRIPTION.strip(),
        match=tool.match,
        execute=tool.execute,
        source=source,
    )


def _discover_module_tools() -> list[RegisteredTool]:
    tools: list[RegisteredTool] = []
    for module_info in pkgutil.iter_modules([str(_PACKAGE_DIR)]):
        if module_info.name in _SKIP_MODULES:
            continue
        module = importlib.import_module(f"{_PACKAGE_NAME}.{module_info.name}")
        if not hasattr(module, "INTENT_NAME"):
            continue
        tool = validate_tool(module)
        tools.append(_registered_from_module(tool, source=f"module:{module_info.name}"))
    return tools


def _build_registry() -> tuple[tuple[RegisteredTool, ...], dict[str, RegisteredTool], dict[str, tuple[RegisteredTool, ...]]]:
    discovered = _discover_module_tools()
    tools_by_intent: dict[str, RegisteredTool] = {}

    for tool in discovered:
        if tool.intent_name in tools_by_intent:
            raise ValueError(f"duplicate registered intent: {tool.intent_name}")
        tools_by_intent[tool.intent_name] = tool

    if "conversation" not in tools_by_intent:
        raise ValueError("conversation tool must be registered")

    trigger_index: dict[str, list[RegisteredTool]] = {}
    for tool in tools_by_intent.values():
        seen_triggers: set[str] = set()
        for trigger in tool.triggers:
            if trigger in seen_triggers:
                continue
            seen_triggers.add(trigger)
            head = _trigger_head(trigger)
            if not head:
                continue
            bucket = trigger_index.setdefault(head, [])
            for existing in bucket:
                if trigger in existing.triggers and existing.intent_name != tool.intent_name:
                    raise ValueError(f"duplicate trigger '{trigger}' across intents: {existing.intent_name}, {tool.intent_name}")
            bucket.append(tool)

    frozen_tools = tuple(tools_by_intent.values())
    frozen_index = {key: tuple(value) for key, value in trigger_index.items()}
    return frozen_tools, {tool.intent_name: tool for tool in frozen_tools}, frozen_index


_TOOLS, _TOOLS_BY_INTENT, _TRIGGER_INDEX = _build_registry()


def tools() -> tuple[RegisteredTool, ...]:
    return _TOOLS


def get(intent_name: str) -> RegisteredTool | None:
    return _TOOLS_BY_INTENT.get(str(intent_name or "").strip().lower())


def descriptions() -> dict[str, str]:
    return {tool.intent_name: tool.ollama_description for tool in _TOOLS}


def _candidate_heads(lowered: str) -> Iterable[str]:
    for token in re.findall(r"[a-z0-9_]+://|[a-z0-9_']+", lowered):
        yield token


def iter_triggered_tools(lowered: str) -> tuple[RegisteredTool, ...]:
    seen: set[str] = set()
    matched: list[RegisteredTool] = []
    for head in _candidate_heads(lowered):
        for tool in _TRIGGER_INDEX.get(head, ()):
            if tool.intent_name in seen:
                continue
            if any(trigger in lowered for trigger in tool.triggers):
                seen.add(tool.intent_name)
                matched.append(tool)
    return tuple(matched)
