# ADR-0001: Thread-Safe Observability Tracing via Unbounded Queue Writer

**Status:** Accepted

## Context
In previous phases, APRIL logged traces and debug markers directly on the caller thread. This approach caused latency on hot execution paths (especially on STT triggers and UI repaints) and risked deadlock scenarios when files were accessed simultaneously by different threads.

## Decision
Introduce a thread-safe, non-blocking observability logging mechanism in `runtime_trace.py`:
- Use a single, process-wide unbounded thread-safe `Queue` to enqueue structured trace markers.
- Spawn a dedicated background logging thread at module load time to consume the queue and write asynchronously to `startup_trace.log` and event files.
- Expose explicit `trace_marker`, `trace_event`, `flush`, and `shutdown` methods.

## Reasoning
- **Non-blocking Callers:** Enqueuing a log is extremely fast (< 0.1ms), ensuring that hotkeys or speech pipelines are not stalled by I/O.
- **Thread Safety:** The Queue coordinates log serialization naturally, preventing concurrent file write conflicts.
- **Simplicity:** Avoiding complicated framework loggers (like standard logging handlers) keeps codebase dependencies light.

## Consequences
- Logging is eventually consistent (buffered in memory before flush).
- A process crash could theoretically lose the last few buffered logs (mitigated by explicit `shutdown(timeout)` calls at exit points).
