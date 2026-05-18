"""
shell.py - Local and remote shell execution handling.
"""

from __future__ import annotations

import os
import re
from typing import Any

from brain import summarize_output
from session_manager import describe_node, execute


def handle(action: dict[str, Any], config: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
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

    result = execute(node, command, config, timeout=int(config.get("shell_timeout_seconds", 20)))
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


def infer_command(text: str, node: str) -> str:
    lowered = text.lower()
    is_windows = node == "local" and os.name == "nt"

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

    path_match = re.search(r"(?:what's in|what is in)\s+(.+)", lowered)
    if path_match:
        raw_path = path_match.group(1).strip(" .")
        if is_windows:
            safe_path = raw_path.replace("'", "''")
            return f"Get-ChildItem -Force -LiteralPath '{safe_path}'"
        return f"ls -la {raw_path!r}"

    return ""
