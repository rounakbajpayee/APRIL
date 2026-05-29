# ADR-0002: request_id & job_id Correlation across Asynchronous Boundaries

**Status:** Accepted

## Context
When a user interacts with APRIL via hotkeys, multiple asynchronous steps occur sequentially (Audio Capture -> STT Transcription -> Brain Planning -> Action Execution -> TTS Speaking -> Repainting). Under high concurrency or rapid triggers, it was impossible to correlate which background logs belonged to which user interaction.

## Decision
Enforce explicit propagation of `request_id` and `job_id` parameters across all boundaries, rather than relying on thread-local storage or context variables.

1. **`request_id` Correlation:**
   - Generated at the interaction boundary (e.g. key down) in `InputHandler` (as `REQ-NNNN`).
   - Propagated positional argument down all callback pipelines (`on_audio(..., request_id)`).
   - Injected into UI Bridge calls (`bridge.set_state(..., request_id)`).

2. **`job_id` Correlation:**
   - Generated inside `main.py` at async tasks boundaries (`STT-NNNN`, `BRAIN-NNNN`, `TTS-NNNN`).
   - Logged alongside the parent `request_id` to establish a causal observability chain.

## Reasoning
- **Determinism:** Explicit parameter passing is foolproof, type-checked, and unaffected by Python thread pool task multiplexing.
- **Traceability:** Facilitates near-instant grep-based log reconstruction of the exact execution path of any transaction.
