"""
session_manager.py - Minimal local/SSH command execution for APRIL phase 1.
"""

from __future__ import annotations

import os
import subprocess
import threading
from typing import Any

_active_node = "local"
_active_node_lock = threading.Lock()


def get_active_node() -> str:
    with _active_node_lock:
        return _active_node


def describe_node(node: str) -> str:
    return node if node in {"local", "mac", "dell"} else "target"


def execute(
    node: str, command: str, config: dict[str, Any], timeout: int = 20
) -> dict[str, Any]:
    global _active_node
    resolved_node = (node or "local").strip().lower() or "local"
    with _active_node_lock:
        _active_node = resolved_node

    if resolved_node == "local":
        return _execute_local(command, timeout)
    if resolved_node in {"mac", "dell"}:
        return _execute_remote(resolved_node, command, config, timeout)
    return {
        "ok": False,
        "node": resolved_node,
        "command": command,
        "output": f"Unknown node: {resolved_node}",
        "returncode": 1,
    }


def show_all_panes() -> bool:
    return _run_terminal_command(["wt", "-w", "0", "focus-tab", "-t", "0"])


def hide_all_panes() -> bool:
    return _run_terminal_command(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "$p = Get-Process WindowsTerminal -ErrorAction SilentlyContinue; "
            "if ($p) { $p | ForEach-Object { $_.CloseMainWindow() | Out-Null } }",
        ]
    )


def handle_home_change(_at_home: bool) -> None:
    return


def _execute_local(command: str, timeout: int) -> dict[str, Any]:
    shell_command = (
        [
            "powershell",
            "-NoProfile",
            "-Command",
            command,
        ]
        if os.name == "nt"
        else ["bash", "-lc", command]
    )

    try:
        result = subprocess.run(
            shell_command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            startupinfo=_startupinfo(),
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "node": "local",
            "command": command,
            "output": f"Command timed out after {timeout} seconds.",
            "returncode": 124,
        }

    output = (result.stdout or "").strip() or (result.stderr or "").strip()
    return {
        "ok": result.returncode == 0,
        "node": "local",
        "command": command,
        "output": output,
        "returncode": result.returncode,
    }


def _execute_remote(
    node: str, command: str, config: dict[str, Any], timeout: int
) -> dict[str, Any]:
    try:
        import paramiko
    except ImportError:
        return {
            "ok": False,
            "node": node,
            "command": command,
            "output": "paramiko is not installed, so remote shell commands are unavailable right now.",
            "returncode": 1,
        }

    host = str(config.get(f"{node}_ssh_host", "") or "").strip()
    user = str(config.get(f"{node}_ssh_user", "") or "").strip()
    key_path = str(config.get(f"{node}_ssh_key", "") or "").strip()
    if not host or not user:
        return {
            "ok": False,
            "node": node,
            "command": command,
            "output": f"{node} SSH host or user is not configured.",
            "returncode": 1,
        }

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        connect_kwargs: dict[str, Any] = {
            "username": user,
            "timeout": timeout,
            "allow_agent": True,
            "look_for_keys": True,
        }
        if key_path:
            connect_kwargs["key_filename"] = os.path.expanduser(key_path)
        client.connect(host, **connect_kwargs)
        _, stdout, stderr = client.exec_command(command, timeout=timeout)
        stdout_text = stdout.read().decode("utf-8", errors="replace").strip()
        stderr_text = stderr.read().decode("utf-8", errors="replace").strip()
        exit_status = stdout.channel.recv_exit_status()
        output = stdout_text or stderr_text
        ok = exit_status == 0
        return {
            "ok": ok,
            "node": node,
            "command": command,
            "output": output,
            "returncode": exit_status,
        }
    except Exception as exc:
        return {
            "ok": False,
            "node": node,
            "command": command,
            "output": f"SSH to {node} failed: {exc}",
            "returncode": 1,
        }
    finally:
        client.close()


def _run_terminal_command(command: list[str]) -> bool:
    try:
        subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            startupinfo=_startupinfo(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except Exception:
        return False


def _startupinfo():
    startupinfo = None
    if os.name == "nt" and hasattr(subprocess, "STARTUPINFO"):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
    return startupinfo
