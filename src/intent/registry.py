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
from copy import deepcopy
import pkgutil
import re
from pathlib import Path
from typing import Any, Callable, Iterable

from .tool_interface import (
    IntentExample,
    IntentPlan,
    IntentResult,
    IntentTool,
    validate_tool,
)

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
    examples: tuple[dict[str, Any], ...]
    match: MatchFn
    execute: ExecuteFn
    source: str


def _normalize_trigger(trigger: str) -> str:
    return " ".join(str(trigger or "").strip().lower().split())


def _trigger_head(trigger: str) -> str:
    parts = trigger.split(" ", 1)
    return parts[0] if parts else ""


def _registered_from_module(tool: IntentTool, source: str) -> RegisteredTool:
    triggers = tuple(
        _normalize_trigger(trigger)
        for trigger in tool.TRIGGERS
        if _normalize_trigger(trigger)
    )
    examples = tuple(_normalize_example(example) for example in tool.EXAMPLES)
    return RegisteredTool(
        intent_name=tool.INTENT_NAME.strip().lower(),
        triggers=triggers,
        ollama_description=tool.OLLAMA_DESCRIPTION.strip(),
        examples=examples,
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


def _build_registry() -> tuple[
    tuple[RegisteredTool, ...],
    dict[str, RegisteredTool],
    dict[str, tuple[RegisteredTool, ...]],
]:
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
                if (
                    trigger in existing.triggers
                    and existing.intent_name != tool.intent_name
                ):
                    raise ValueError(
                        f"duplicate trigger '{trigger}' across intents: {existing.intent_name}, {tool.intent_name}"
                    )
            bucket.append(tool)

    frozen_tools = tuple(tools_by_intent.values())
    frozen_index = {key: tuple(value) for key, value in trigger_index.items()}
    return frozen_tools, {tool.intent_name: tool for tool in frozen_tools}, frozen_index


def tools() -> tuple[RegisteredTool, ...]:
    return _TOOLS


def get(intent_name: str) -> RegisteredTool | None:
    return _TOOLS_BY_INTENT.get(str(intent_name or "").strip().lower())


def descriptions() -> dict[str, str]:
    return {tool.intent_name: tool.ollama_description for tool in _TOOLS}


def examples() -> dict[str, tuple[dict[str, Any], ...]]:
    return {
        tool.intent_name: tuple(dict(example) for example in tool.examples)
        for tool in _TOOLS
    }


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


def semantic_plan(
    text: str, *, confidence_threshold: float = 0.76
) -> IntentPlan | None:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return None
    normalized = _normalize_text(lowered)
    query_tokens = _tokenize(normalized)
    if not query_tokens:
        return None

    best_tool: RegisteredTool | None = None
    best_example: dict[str, Any] | None = None
    best_score = 0.0
    second_score = 0.0

    for tool in _TOOLS:
        if tool.intent_name == "conversation":
            continue
        tool_score = 0.0
        tool_example: dict[str, Any] | None = None
        for example in tool.examples:
            score = _score_example(normalized, query_tokens, example, tool)
            if score > tool_score:
                tool_score = score
                tool_example = dict(example)
        if tool_score > best_score:
            second_score = best_score
            best_score = tool_score
            best_tool = tool
            best_example = tool_example
        elif tool_score > second_score:
            second_score = tool_score

    if best_tool is None or best_example is None:
        return None
    if best_score < confidence_threshold:
        return None
    if best_score - second_score < 0.05:
        return None

    plan = best_tool.match(text, lowered)
    if plan is None:
        action = (
            best_example.get("action")
            if isinstance(best_example.get("action"), dict)
            else {}
        )
        if not action:
            return None
        plan = {
            "intent": best_tool.intent_name,
            "response_preview": str(
                best_example.get("response_preview", "") or ""
            ).strip(),
            "action": deepcopy(action),
        }

    if not isinstance(plan, dict):
        return None
    if not isinstance(plan.get("action"), dict):
        plan["action"] = {}
    plan["action"].setdefault("text", text)
    plan.setdefault("intent", best_tool.intent_name)
    if not str(plan.get("response_preview", "") or "").strip():
        preview = str(best_example.get("response_preview", "") or "").strip()
        if preview:
            plan["response_preview"] = preview
    plan["_semantic"] = {
        "score": round(best_score, 3),
        "example": str(best_example.get("text", "") or "").strip(),
        "intent": best_tool.intent_name,
    }
    return plan


def _normalize_example(example: IntentExample) -> dict[str, Any]:
    text = _normalize_text(str(example.get("text", "") or ""))
    response_preview = " ".join(
        str(example.get("response_preview", "") or "").strip().split()
    )
    action = example.get("action") if isinstance(example.get("action"), dict) else {}
    return {
        "text": text,
        "response_preview": response_preview,
        "action": dict(action),
    }


def _normalize_text(text: str) -> str:
    return " ".join(str(text).strip().lower().split())


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_:/.-]+", text.lower())


def _score_example(
    query: str, query_tokens: list[str], example: dict[str, Any], tool: RegisteredTool
) -> float:
    example_text = str(example.get("text", "") or "").strip().lower()
    if not example_text:
        return 0.0
    if example_text == query:
        return 1.0

    example_tokens = _tokenize(example_text)
    if not example_tokens:
        return 0.0

    query_set = set(query_tokens)
    example_set = set(example_tokens)
    shared = len(query_set & example_set)
    union = len(query_set | example_set)
    jaccard = shared / union if union else 0.0
    overlap = shared / max(len(query_tokens), len(example_tokens), 1)
    subseq_bonus = 0.12 if example_text in query or query in example_text else 0.0
    prefix_bonus = (
        0.08
        if query.startswith(example_text[: min(len(query), len(example_text))])
        else 0.0
    )
    description_bonus = _description_bonus(query_tokens, tool.ollama_description)
    return min(
        1.0,
        (jaccard * 0.52)
        + (overlap * 0.32)
        + subseq_bonus
        + prefix_bonus
        + description_bonus,
    )


def _description_bonus(query_tokens: list[str], description: str) -> float:
    desc_tokens = set(_tokenize(description))
    if not desc_tokens:
        return 0.0
    overlap = len(set(query_tokens) & desc_tokens) / max(len(query_tokens), 1)
    return min(0.08, overlap * 0.08)


_TOOLS, _TOOLS_BY_INTENT, _TRIGGER_INDEX = _build_registry()
