"""
shell.py - Local and remote shell execution handling.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from brain import summarize_output
from session_manager import describe_node, execute as execute_session_command
from .tool_interface import IntentPlan, IntentResult


INTENT_NAME = "shell"
TRIGGERS = [
    "connect to",
    "run",
    "execute",
    "what's in",
    "what is in",
    "list files",
    "show files",
    "current directory",
    "working directory",
    "who am i",
    "check network load",
    "disk usage",
    "memory usage",
]
OLLAMA_DESCRIPTION = "Run shell commands locally or on configured remote nodes"
EXAMPLES = [
    {
        "text": "who am i on local",
        "response_preview": "Checking that on local.",
        "action": {"mode": "natural", "node": "local"},
    },
    {
        "text": "list files",
        "response_preview": "Checking that on local.",
        "action": {"mode": "natural", "node": "local"},
    },
    {
        "text": "what's in the documents folder",
        "response_preview": "Checking that on local.",
        "action": {"mode": "natural", "node": "local"},
    },
    {
        "text": "open my documents folder",
        "response_preview": "Checking that on local.",
        "action": {"mode": "natural", "node": "local"},
    },
    {
        "text": "run git status on local",
        "response_preview": "Running that on local.",
        "action": {"mode": "command", "node": "local", "command": "git status"},
    },
    {
        "text": "connect to mac",
        "response_preview": "Checking mac.",
        "action": {"mode": "check_connection", "node": "mac"},
    },
]


def match(text: str, lowered: str) -> IntentPlan | None:
    node = _detect_node(lowered)

    if lowered.startswith("connect to "):
        target = lowered.split("connect to ", 1)[1].strip(" .")
        if target in {"mac", "dell", "local"}:
            return {
                "intent": INTENT_NAME,
                "response_preview": f"Checking {target}.",
                "action": {"mode": "check_connection", "node": target, "text": text},
            }

    if lowered.startswith("run ") or lowered.startswith("execute "):
        command = text.split(" ", 1)[1].strip()
        command = _strip_trailing_node_selector(command)
        return {
            "intent": INTENT_NAME,
            "response_preview": f"Running that on {node}.",
            "action": {"mode": "command", "node": node, "command": command, "text": text},
        }

    simple_phrases = (
        "what's in",
        "what is in",
        "list files",
        "show files",
        "current directory",
        "working directory",
        "who am i",
        "check network load",
        "disk usage",
        "memory usage",
    )
    if any(phrase in lowered for phrase in simple_phrases):
        return {
            "intent": INTENT_NAME,
            "response_preview": f"Checking that on {node}.",
            "action": {"mode": "natural", "node": node, "text": text},
        }

    return None


def execute(action: dict[str, Any], config: dict[str, Any], context: dict[str, Any] | None = None) -> IntentResult:
    context = context or {}
    node = str(action.get("node", "local") or "local").strip().lower()
    mode = str(action.get("mode", "command") or "command").strip().lower()
    original_text = str(action.get("text") or context.get("text") or "").strip()

    command = str(action.get("command", "") or "").strip()
    if mode == "check_connection" and not command:
        command = "hostname"
    elif mode == "natural" and not command:
        command = infer_command(original_text, node)

    if not command:
        return {
            "reply": "I understood that as a shell request, but I still need a clearer command.",
            "config_changed": False,
            "ok": False,
            "error_kind": "shell_command_missing",
        }

    try:
        result = execute_session_command(node, command, config, timeout=int(config.get("shell_timeout_seconds", 20)))
    except Exception as exc:
        import runtime_trace
        runtime_trace.trace_event(
            "shell_execute_error",
            subsystem="intent.shell",
            severity=runtime_trace.ERROR,
            payload={"error": str(exc), "node": node, "command": command[:120]},
        )
        return {
            "reply": f"Shell command failed: {exc}",
            "config_changed": False,
            "ok": False,
            "error_kind": "shell_error",
        }
    output = str(result.get("output", "") or "").strip()
    target = describe_node(node)

    if not result.get("ok"):
        error_kind = "shell_timeout" if int(result.get("returncode", 0) or 0) == 124 else "shell_failed"
        if output:
            return {
                "reply": f"The command on {target} failed: {output}",
                "config_changed": False,
                "ok": False,
                "error_kind": error_kind,
            }
        return {
            "reply": f"The command on {target} failed.",
            "config_changed": False,
            "ok": False,
            "error_kind": error_kind,
        }

    summary = summarize_output(output, original_text or command, config)
    if node == "local":
        return {"reply": summary, "config_changed": False, "ok": True}
    return {"reply": f"On {target}, {summary}", "config_changed": False, "ok": True}


def handle(action: dict[str, Any], config: dict[str, Any], context: dict[str, Any] | None = None) -> IntentResult:
    return execute(action, config, context)


def _detect_node(lowered: str) -> str:
    if " on mac" in lowered or lowered.endswith(" mac"):
        return "mac"
    if " on dell" in lowered or lowered.endswith(" dell"):
        return "dell"
    if " locally" in lowered or " on local" in lowered or lowered.endswith(" local"):
        return "local"
    return "local"


def _strip_trailing_node_selector(command: str) -> str:
    for suffix in (" on mac", " on dell", " on local"):
        if command.lower().endswith(suffix):
            return command[: -len(suffix)].strip()
    return command


def infer_command(text: str, node: str) -> str:
    lowered = text.lower()
    is_windows = node == "local" and os.name == "nt"
    user_home = Path.home()
    documents_dir = user_home / "Documents"
    downloads_dir = user_home / "Downloads"
    desktop_dir = user_home / "Desktop"

    if any(phrase in lowered for phrase in ("current directory", "working directory", "where am i")):
        return "Get-Location" if is_windows else "pwd"

    if "who am i" in lowered or "whoami" in lowered:
        return "whoami"

    if "check network load" in lowered:
        return "Get-NetAdapterStatistics | Format-Table -AutoSize" if is_windows else "uptime"

    if "disk usage" in lowered:
        return "Get-PSDrive -PSProvider FileSystem | Format-Table -AutoSize" if is_windows else "df -h"

    if "memory usage" in lowered:
        return (
            "Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize,FreePhysicalMemory"
            if is_windows
            else "free -h"
        )

    if any(phrase in lowered for phrase in ("list files", "show files")):
        return "Get-ChildItem -Force" if is_windows else "ls -la"

    if any(phrase in lowered for phrase in ("documents folder", "documents directory", "my documents", "open documents")):
        if is_windows:
            safe_path = str(documents_dir).replace("'", "''")
            return f"Get-ChildItem -Force -LiteralPath '{safe_path}'"
        return f"ls -la {str(documents_dir)!r}"

    if any(phrase in lowered for phrase in ("downloads folder", "downloads directory", "my downloads", "open downloads")):
        if is_windows:
            safe_path = str(downloads_dir).replace("'", "''")
            return f"Get-ChildItem -Force -LiteralPath '{safe_path}'"
        return f"ls -la {str(downloads_dir)!r}"

    if any(phrase in lowered for phrase in ("desktop folder", "desktop directory", "my desktop", "open desktop")):
        if is_windows:
            safe_path = str(desktop_dir).replace("'", "''")
            return f"Get-ChildItem -Force -LiteralPath '{safe_path}'"
        return f"ls -la {str(desktop_dir)!r}"

    path_match = re.search(r"(?:what's in|what is in)\s+(.+)", lowered)
    if path_match:
        raw_path = path_match.group(1).strip(" .")
        if is_windows:
            safe_path = raw_path.replace("'", "''")
            return f"Get-ChildItem -Force -LiteralPath '{safe_path}'"
        return f"ls -la {raw_path!r}"

    return ""
