"""
runtime_trace.py — Canonical runtime trace infrastructure for APRIL.

Phase 1 — Commit A: additive infrastructure only.
No call-site migration in this commit.

Architecture:
    caller thread
    → queue.Queue
    → single writer thread (_TraceWriter)
    → append-only file writes → logs/startup_trace.log

Public API:
    trace_marker(message)
    trace_event(event, *, subsystem, request_id=None, payload=None)
    shutdown(timeout=3.0)
    flush(timeout=3.0)

Design invariants:
    - Never raises into caller under any circumstances.
    - Never blocks caller thread on disk I/O.
    - Single writer thread owns all file access; no external locking needed.
    - Writer thread is daemon=True so it never prevents process exit on crash.
    - Graceful shutdown drains the queue within a bounded timeout.
    - Trace failure is isolated: runtime behavior is unaffected.


TRANSITIONAL PHASE 1 NOTES

- startup_trace.log intentionally contains both:
  - human-readable TRACE lines
  - structured JSON trace_event lines

- This mixed-format output is transitional and intentional.

- Future observability phases should separate:
  - human-readable causal traces
  - machine-readable structured event streams

- Phase 1 prioritizes:
  - deterministic migration
  - preservation of existing TRACE workflows
  - minimal runtime semantic change
"""

from __future__ import annotations

import json
import queue
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_BASE_DIR = Path(__file__).resolve().parent
_LOG_DIR  = _BASE_DIR / "logs"
_TRACE_PATH = _LOG_DIR / "startup_trace.log"

# Sentinel object — placed on the queue to signal the writer to shut down.
_SENTINEL = object()

# Drain timeout used by flush() and shutdown() if the caller doesn't specify.
_DEFAULT_DRAIN_TIMEOUT = 3.0  # seconds


# ---------------------------------------------------------------------------
# Internal writer
# ---------------------------------------------------------------------------

class _TraceWriter:
    """
    Single writer thread that owns all appends to startup_trace.log.

    Receives pre-formatted line strings via a Queue.  Each line is
    written with a newline and flushed immediately so partial-line
    corruption cannot occur.  File handle is opened once at first write
    and kept open; the directory is created on first use.

    Shutdown procedure:
        1. Put _SENTINEL onto the queue.
        2. Join the thread with a bounded timeout.
        3. If the thread did not exit in time, abandon it (it is daemon).
    """

    def __init__(self) -> None:
        self._q: queue.Queue[Any] = queue.Queue()
        self._handle = None          # open file handle, or None
        self._thread = threading.Thread(
            target=self._run,
            name="april-trace-writer",
            daemon=True,
        )
        self._thread.start()

    # ------------------------------------------------------------------ public

    def put(self, line: str) -> None:
        """Enqueue a pre-formatted line.  Never raises."""
        try:
            self._q.put_nowait(line)
        except Exception:
            pass

    def flush(self, timeout: float = _DEFAULT_DRAIN_TIMEOUT) -> None:
        """
        Block until the queue is drained or timeout expires.

        Places a sentinel, then waits for the queue to become empty.
        Does not stop the writer thread.
        """
        try:
            done = threading.Event()
            self._q.put(_DrainMarker(done))
            done.wait(timeout=timeout)
        except Exception:
            pass

    def shutdown(self, timeout: float = _DEFAULT_DRAIN_TIMEOUT) -> None:
        """
        Signal the writer to stop and wait up to timeout seconds.

        After this returns the writer thread may still be alive if it
        did not drain in time; that is acceptable because it is daemon=True.
        """
        try:
            self._q.put(_SENTINEL)
            self._thread.join(timeout=timeout)
        except Exception:
            pass
        finally:
            self._close_handle()

    # ------------------------------------------------------------------ writer loop

    def _run(self) -> None:
        while True:
            try:
                item = self._q.get()
            except Exception:
                break

            if item is _SENTINEL:
                self._q.task_done()
                break

            if isinstance(item, _DrainMarker):
                try:
                    item.done.set()
                except Exception:
                    pass
                self._q.task_done()
                continue

            if isinstance(item, str):
                self._write(item)
                self._q.task_done()

        self._close_handle()

    def _write(self, line: str) -> None:
        try:
            handle = self._get_handle()
            if handle is None:
                return
            handle.write(line + "\n")
            handle.flush()
        except Exception as exc:
            # Isolate; optionally print to stderr so it's visible during dev.
            try:
                print(f"[runtime_trace] write error: {exc}", file=sys.stderr)
            except Exception:
                pass
            # Try to close and reopen on next write.
            self._close_handle()

    def _get_handle(self):
        if self._handle is not None:
            return self._handle
        try:
            _LOG_DIR.mkdir(parents=True, exist_ok=True)
            self._handle = _TRACE_PATH.open("a", encoding="utf-8", buffering=1)
            return self._handle
        except Exception as exc:
            try:
                print(f"[runtime_trace] cannot open trace file: {exc}", file=sys.stderr)
            except Exception:
                pass
            return None

    def _close_handle(self) -> None:
        try:
            if self._handle is not None:
                self._handle.close()
        except Exception:
            pass
        finally:
            self._handle = None


class _DrainMarker:
    """Placed on the queue by flush(); signals completion via an Event."""
    __slots__ = ("done",)

    def __init__(self, done: threading.Event) -> None:
        self.done = done


# ---------------------------------------------------------------------------
# Module-level writer instance
# ---------------------------------------------------------------------------

# Created once at import time.  This is intentionally module-level state;
# there is exactly one writer per process.  No dynamic registration.
_writer = _TraceWriter()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def trace_marker(message: str) -> None:
    """
    Emit a human-readable deterministic runtime trace marker.

    Format (matches existing startup_trace.log format):
        <ISO-UTC-timestamp> [<caller tag if inferable>] <message>

    The caller tag is NOT inferred here — callers include their own
    subsystem prefix in message (e.g. "[main] TRACE1 INPUT state=idle"),
    exactly as the existing trace_startup() functions do.

    This function:
        - is thread-safe
        - never raises
        - never blocks on disk I/O
        - enqueues the line and returns immediately
    """
    try:
        ts = datetime.now(timezone.utc).isoformat()
        line = f"{ts} {message}"
        _writer.put(line)
    except Exception:
        pass


def trace_event(
    event: str,
    *,
    subsystem: str,
    request_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """
    Emit a structured trace event to the trace log.

    Serialized as a single JSON line.  Future-compatible; lightly used
    in Phase 1.

    Arguments:
        event      — event name string (e.g. "state_transition")
        subsystem  — source subsystem label (e.g. "bridge", "input")
        request_id — optional correlation ID
        payload    — optional dict of additional fields

    This function:
        - is thread-safe
        - never raises
        - never blocks on disk I/O
    """
    try:
        record: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "trace_event",
            "event": str(event),
            "subsystem": str(subsystem),
        }
        if request_id is not None:
            record["request_id"] = str(request_id)
        if payload:
            record["payload"] = payload
        line = json.dumps(record, ensure_ascii=False)
        _writer.put(line)
    except Exception:
        pass


def flush(timeout: float = _DEFAULT_DRAIN_TIMEOUT) -> None:
    """
    Block until pending trace writes are flushed, or timeout expires.

    Safe to call from any thread.  Does not stop the writer.
    """
    try:
        _writer.flush(timeout=timeout)
    except Exception:
        pass


def shutdown(timeout: float = _DEFAULT_DRAIN_TIMEOUT) -> None:
    """
    Flush pending writes and stop the writer thread.

    Bounded by timeout.  Safe to call from any thread.
    Runtime callers (main.py app shutdown) should call this once.
    """
    try:
        _writer.shutdown(timeout=timeout)
    except Exception:
        pass
