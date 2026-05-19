"""
intent package - APRIL phase 1 execution dispatcher.
"""

from __future__ import annotations

from typing import Any

from screen_capture import capture_and_query

from . import registry


def execute_plan(plan: dict[str, Any], config: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    context = context or {}
    intent = str(plan.get("intent", "") or "").strip().lower()
    action = plan.get("action")
    if not isinstance(action, dict):
        action = {}
    tool = registry.get(intent) or registry.get("conversation")
    if tool is None:
        raise RuntimeError("conversation tool is not registered")
    return tool.execute(action, config, context)
