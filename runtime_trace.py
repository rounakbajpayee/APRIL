"""
runtime_trace.py — Canonical runtime trace infrastructure for APRIL.

Phase 1 — Commit A: additive infrastructure only.
Phase 2A — RuntimeEvent canonical schema introduced.

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

RuntimeEvent (Phase 2A):
    Canonical internal schema for all structured trace events.
    Internal to this module; callers continue using trace_event() unchanged.

Design invariants:
    - Never raises into caller under any circumstances.
    - Never blocks caller thread on disk I/O.
    - Single writer thread owns all file access; no external locking needed.
    - Writer thread is daemon=True so it never prevents process exit on crash.
    - Graceful shutdown drains the queue within a bounded timeout.
    - Trace failure is isolated: runtime behavior is unaffected.


TRANSITIONAL PHASE 1/2A NOTES

- startup_trace.log intentionally contains both:
  - human-readable TRACE lines (trace_marker)
  - structured JSON trace_event lines (trace_event → RuntimeEvent)

- This mixed-format output is transitional and intentional.

- Future observability phases should separate:
  - human-readable causal traces
  - machine-readable structured event streams

- Phase 1/2A prioritizes:
  - deterministic migration
  - preservation of existing TRACE workflows
  - minimal runtime semantic change

PHASE 2A CHANGES

- RuntimeEvent dataclass introduced as canonical internal schema.
- trace_event() now normalizes to RuntimeEvent before serialization.
- Serialization output is semantically identical to Phase 1.
- No caller changes required.
- thread_name field captured automatically; job_id reserved (None).
- request_id and job_id fields present on schema; propagation deferred to Phase 2B/2C.
"""

from __future__ import annotations

import json
import queue
import sys
import threading
from dataclasses import dataclass
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
# Phase 2A — Canonical RuntimeEvent schema
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class RuntimeEvent:
    """
    Canonical runtime event schema for APRIL observability.

    Phase 2A: schema definition only.
    Phase 2B: request_id propagation.
    Phase 2C: job_id propagation.

    Fields
    ------
    timestamp   : ISO-UTC timestamp — causal ordering.
    subsystem   : source subsystem label — ownership boundary.
    severity    : one of DEBUG | INFO | WARNING | ERROR | CRITICAL.
    event       : concise event identity string.
    request_id  : optional — request lifecycle correlation (Phase 2B).
    job_id      : optional — async/subtask correlation (Phase 2C).
    payload     : optional — compact structured event details.
    thread_name : optional — thread boundary visibility.

    Canonical subsystem values:
        input | bridge | state | ui | brain | tts | stt | runtime | observability

    Canonical severity values:
        DEBUG | INFO | WARNING | ERROR | CRITICAL

    Design constraints:
        - Immutable after construction (slots=True, no post-init mutation).
        - Compact JSON serialization via _serialize().
        - No inheritance. No event bus. No magic.
    """
    timestamp:   str
    subsystem:   str
    severity:    str
    event:       str
    request_id:  str | None = None
    job_id:      str | None = None
    payload:     dict[str, Any] | None = None
    thread_name: str | None = None

    def _serialize(self) -> str:
        """
        Serialize to a compact JSON line suitable for append-only log output.

        Output fields:
            ts, type, subsystem, severity, event
            + conditionally: request_id, job_id, thread_name, payload

        Omits None fields to keep lines compact and human-inspectable.
        Field order is stable and deterministic.
        """
        record: dict[str, Any] = {
            "ts":        self.timestamp,
            "type":      "trace_event",
            "subsystem": self.subsystem,
            "severity":  self.severity,
            "event":     self.event,
        }
        if self.request_id is not None:
            record["request_id"] = self.request_id
        if self.job_id is not None:
            record["job_id"] = self.job_id
        if self.thread_name is not None:
            record["thread_name"] = self.thread_name
        if self.payload:
            record["payload"] = self.payload
        return json.dumps(record, ensure_ascii=False)


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

    Internally normalized to RuntimeEvent before serialization.
    Serialized as a single JSON line.

    Arguments:
        event      — event name string (e.g. "state_transition")
        subsystem  — source subsystem label (e.g. "bridge", "input")
        request_id — optional correlation ID
        payload    — optional dict of additional fields

    Caller API is unchanged from Phase 1.  RuntimeEvent is internal.

    This function:
        - is thread-safe
        - never raises
        - never blocks on disk I/O
    """
    try:
        ev = RuntimeEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            subsystem=str(subsystem),
            severity="INFO",
            event=str(event),
            request_id=str(request_id) if request_id is not None else None,
            job_id=None,  # Phase 2C
            payload=payload if payload else None,
            thread_name=threading.current_thread().name,
        )
        _writer.put(ev._serialize())
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
