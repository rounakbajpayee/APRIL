# Operations Runbook — APRIL

This runbook guides you on how to start, monitor, troubleshoot, and operate the APRIL daemon.

---

## 1. Process Operations

Manage the background daemon using the root-level shortcuts or directly via `scripts/aprilctl.ps1`:

* **Start the background process:**
  ```cmd
  .\start.cmd
  ```
  *Under the hood:* Runs `powershell -WindowStyle Hidden -File scripts/aprilctl.ps1 start`.
* **Check service status:**
  ```cmd
  .\status.cmd
  ```
* **Stop the process:**
  ```cmd
  .\stop.cmd
  ```

---

## 2. Directory and Logs Index

All configuration and log folders are resolved relative to the repository root:

* **Traces & Debug Logs:**
  - `src/logs/startup_trace.log`: Direct trace logs of initialization stages and threads.
  - `src/logs/debug.jsonl`: Structured developer activities and transcripts.
* **State Projections:**
  - `src/state/events.jsonl`: Causal event ledgers.
  - `src/state/context_snapshot.json`: Active desktop apps snapshot and open loop indicators.
* **Persistent Cache:**
  - `src/memory.json`: Session turns.
  - `src/learned_phrases.json`: Teach phrase overrides.

---

## 3. Common Troubleshooting

### Process Already Running
If `start.cmd` prints that APRIL is already running but it doesn't respond, run:
```cmd
.\stop.cmd
.\start.cmd
```
This forces a process termination and restarts the listeners.

### Hotkeys Not Capturing
If APRIL does not register trigger keypresses (e.g. F23/Copilot key):
1. Check if another application is locking key hooks.
2. Confirm the virtual environment has `pynput` installed correctly.
3. Check `src/logs/startup_trace.log` for any hook registration errors.
