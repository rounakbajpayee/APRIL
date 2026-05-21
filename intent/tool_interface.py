"""
Typed interface for self-registering APRIL intent tools.

Each tool module in intent/ is expected to expose:
- INTENT_NAME: unique registry key
- TRIGGERS: phrase fragments used for fast local lookup
- OLLAMA_DESCRIPTION: planner prompt description
- match(text, lowered): local routing probe that returns a normalized plan or None
- execute(action, config, context): execution entrypoint
"""

from __future__ import annotations

from typing import Any, NotRequired, Protocol, TypedDict, cast


class IntentAction(TypedDict, total=False):
    text: str


class IntentExample(TypedDict, total=False):
    text: str
    response_preview: str
    action: IntentAction


class IntentPlan(TypedDict):
    intent: str
    response_preview: str
    action: IntentAction


class IntentResult(TypedDict):
    reply: str
    ok: bool
    error_kind: NotRequired[str | None]
    config_changed: NotRequired[bool]


class IntentTool(Protocol):
    INTENT_NAME: str
    TRIGGERS: list[str] | tuple[str, ...]
    OLLAMA_DESCRIPTION: str
    EXAMPLES: list[IntentExample] | tuple[IntentExample, ...]

    def match(self, text: str, lowered: str) -> IntentPlan | None:
        ...

    def execute(self, action: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> IntentResult:
        ...


def validate_tool(candidate: Any) -> IntentTool:
    intent_name = getattr(candidate, "INTENT_NAME", None)
    triggers = getattr(candidate, "TRIGGERS", None)
    description = getattr(candidate, "OLLAMA_DESCRIPTION", None)
    match = getattr(candidate, "match", None)
    execute = getattr(candidate, "execute", None)

    if not isinstance(intent_name, str) or not intent_name.strip():
        raise ValueError("tool is missing a valid INTENT_NAME")
    if not isinstance(triggers, (list, tuple)):
        raise ValueError(f"{intent_name} is missing TRIGGERS")
    if any(not isinstance(trigger, str) or not trigger.strip() for trigger in triggers):
        raise ValueError(f"{intent_name} has invalid TRIGGERS")
    if not isinstance(description, str) or not description.strip():
        raise ValueError(f"{intent_name} is missing OLLAMA_DESCRIPTION")
    examples = getattr(candidate, "EXAMPLES", None)
    if not isinstance(examples, (list, tuple)):
        raise ValueError(f"{intent_name} is missing EXAMPLES")
    for example in examples:
        if not isinstance(example, dict):
            raise ValueError(f"{intent_name} has an invalid EXAMPLES entry")
        example_text = str(example.get("text", "") or "").strip()
        if not example_text:
            raise ValueError(f"{intent_name} has an EXAMPLES entry without text")
    if not callable(match):
        raise ValueError(f"{intent_name} is missing match()")
    if not callable(execute):
        raise ValueError(f"{intent_name} is missing execute()")
    return cast(IntentTool, candidate)
