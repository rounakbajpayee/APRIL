# APRIL - Design Document
> Version: 0.5
> Date: 2026-05-21
> Status: Active runtime plus doc sync complete

This document is the current design reference for the desktop APRIL MVP. [Certain]

## What APRIL Is

APRIL is a locally running Windows assistant that listens on the Lenovo host, routes intent across local tools and remote services, and keeps a durable runtime state trail. [Certain]

Current implemented scope includes voice and text input, local and remote STT, local and LLM-backed routing, a floating widget with a context panel, structured event/state projection, persistent short-term memory, teachable phrase rewrites, and a semantic example store for later reuse and training export. [Certain]

## Current Runtime State

- The registry-based intent system is the primary routing layer. [Certain]
- Example-based semantic routing now runs before Ollama for local intents. [Certain]
- Completed requests are captured into `state/semantic_records.jsonl` as training-ready examples. [Certain]
- `tts_engine: "say"` now routes over SSH to the configured node instead of silently falling back. [Certain]
- `mac_ssh_key` and `dell_ssh_key` config keys are supported by `session_manager.py`. [Certain]
- The widget stays in speaking state until TTS actually finishes. [Certain]
- The stress suite currently contains 22 passing tests. [Certain]

## Repository Structure

```text
april/
|-- aprilctl.cmd
|-- aprilctl.ps1
|-- main.py
|-- widget.py
|-- input_handler.py
|-- stt.py
|-- brain.py
|-- tts.py
|-- session_manager.py
|-- device_control.py
|-- media.py
|-- screen_capture.py
|-- observer.py
|-- event_ledger.py
|-- state_engine.py
|-- debug_log.py
|-- learning.py
|-- memory.py
|-- semantic_store.py
|-- stress_test.py
|-- intent/
|   |-- __init__.py
|   |-- registry.py
|   |-- tool_interface.py
|   |-- browser.py
|   |-- config_intent.py
|   |-- conversation.py
|   |-- device.py
|   |-- media_intent.py
|   |-- shell.py
|   `-- vision.py
|-- prompts/
|-- state/
`-- logs/
```

## Config Notes

`config_defaults.json` holds the full schema and `config.json` stores only overrides. [Certain]

Important runtime keys: [Certain]

- `voice`: enables or disables spoken replies. [Certain]
- `tts_engine`: `auto`, `sapi`, `say`, or `espeak`. [Certain]
- `tts_say_node`: target node for SSH `say`; defaults to `mac`. [Certain]
- `tts_timeout_seconds`: timeout for remote `say` execution. [Certain]
- `stt_mode`: `remote_first` or `local_only`. [Certain]
- `ollama_host` and `ollama_model`: planner and conversation backend. [Certain]
- `mac_ssh_host`, `mac_ssh_user`, `mac_ssh_key`: remote shell and remote TTS config for the Mac. [Certain]
- `dell_ssh_host`, `dell_ssh_user`, `dell_ssh_key`: remote shell config for the Dell. [Certain]
- `state_context_timeline_limit`: prompt-time state summary size. [Certain]
- `widget_anchor_x`, `widget_anchor_y`, `widget_anchor_bottom_y`: persisted widget placement. [Certain]

## Request Pipeline

Normal voice flow: [Certain]

1. `input_handler.py` captures audio from the Copilot key workflow. [Certain]
2. `main.py` assigns a request id and records request lifecycle events. [Certain]
3. `stt.py` transcribes with metadata. [Certain]
4. `brain.py` applies learned rewrites, local replies, trigger routing, full tool matching, then example-based semantic routing, then Ollama planning if needed. [Certain]
5. `intent/__init__.py` dispatches the plan to the registered tool. [Certain]
6. `main.py` records structured result events, updates snapshots, stores a semantic example, appends memory, and triggers TTS if a reply exists. [Certain]

## Routing Stack

`brain.py` currently evaluates in this order: [Certain]

1. Local utility replies such as time, model, recent activity, current context, open loops, and latest transcript. [Certain]
2. Trigger-index matches from `intent/registry.py`. [Certain]
3. Full tool `match()` passes across registered non-conversation tools. [Certain]
4. Example-based semantic routing from intent `EXAMPLES`. [Certain]
5. Ollama JSON intent planning. [Certain]
6. Conversation fallback. [Certain]

Weak point: the example-based semantic router is lexical and lightweight, so it improves paraphrase recovery but is not a substitute for a real embedding store. [Likely]

## Semantic Layer

APRIL now has two related semantic mechanisms. [Certain]

`intent/registry.py` uses per-tool `EXAMPLES` to recover paraphrases before Ollama. [Certain]

`semantic_store.py` keeps append-only confirmed records in `state/semantic_records.jsonl`. Each record includes normalized text, resolved intent, action payload, outcome, subject metadata, and optional confidence. [Certain]

Current confirmed use cases: [Certain]

- reuse prior phrasing with `semantic_store.semantic_plan()` [Certain]
- export training-ready examples with `export_training_records()` [Certain]
- preserve a common record shape for future non-conversation artifacts such as documents and directories [Certain]

Weak point: the store currently rewrites the file from its in-memory cache window and caps retained cache-backed records at 500 entries, so it is still a pragmatic MVP store, not a long-term archival database. [Certain]

## State System

`event_ledger.py` is the canonical append-only event log and `state_engine.py` deterministically replays it into snapshots. [Certain]

Important event types in active use include: [Certain]

- `april_started` [Certain]
- `request_started` and `request_interrupted` [Certain]
- `audio_captured` [Certain]
- `transcript_received` and `transcript_unavailable` [Certain]
- `intent_planned` [Certain]
- `action_completed` and `action_failed` [Certain]
- `assistant_replied` [Certain]
- `response_discarded` [Certain]
- `config_changed` [Certain]
- `desktop_observed` [Certain]
- `semantic_example_recorded` [Certain]

Generated state files: [Certain]

- `state/events.jsonl` [Certain]
- `state/april_state.json` [Certain]
- `state/desktop_state.json` [Certain]
- `state/context_snapshot.json` [Certain]

## Widget

The widget is a compact always-on-top pill that can expand into a larger context panel. [Certain]

Implemented behavior: [Certain]

- idle, listening, thinking, speaking, and error states [Certain]
- speaking state remains active until TTS completion callback returns [Certain]
- hover pauses collapse timers [Certain]
- collapsed orb click reopens the panel path [Likely]
- larger default context panel with summary cards, open loops, scrollable timeline, text input, and resize grip [Certain]
- persisted widget position and UI history [Certain]

Weak point: visual correctness still depends on display scale and actual runtime testing; automated tests do not verify rendering. [Certain]

## TTS

`tts.py` exposes `speak()`, `stop()`, and engine resolution. [Certain]

Current behavior: [Certain]

- `auto` resolves to `sapi` on Windows. [Certain]
- `sapi` uses a hidden PowerShell speech synthesizer subprocess. [Certain]
- `say` uses `session_manager.execute()` and runs `say <text>` on the configured remote node on Windows. [Certain]
- `stop()` terminates the active subprocess for interruption. [Certain]

Weak point: the remote `say` path currently trusts shell quoting around a single string command, so unusual punctuation or remote shell differences are the most likely edge cases. [Likely]

## Session Manager

`session_manager.py` executes commands locally or over SSH. [Certain]

Remote execution supports configured key paths through `key_filename` when `mac_ssh_key` or `dell_ssh_key` is provided. [Certain]

Weak point: `handle_home_change()` is still a no-op, so the `at_home` flag is descriptive and indirect rather than enforcing a real connection lifecycle. [Certain]

## Stress Coverage

Run with: [Certain]

```powershell
.venv\Scripts\python.exe stress_test.py -v
```

Current automated coverage includes 22 tests for: [Certain]

- core routing [Certain]
- conversation-question protection [Certain]
- media pause routing [Certain]
- learning rewrites [Certain]
- override-only config writes [Certain]
- recent activity introspection [Certain]
- event ledger and snapshot projection [Certain]
- transcript failure open loops [Certain]
- mixed execution dispatch [Certain]
- interruption cleanup [Certain]
- shell timeout classification [Certain]
- session-manager delegation [Certain]
- device volume endpoint usage [Certain]
- visible Windows app launch [Certain]
- configured remote SSH key usage [Certain]
- remote `say` routing [Certain]
- launcher quoting [Certain]
- failure and discard event recording [Certain]
- STT metadata logging [Certain]
- semantic store recall [Certain]
- example-based semantic routing [Certain]

Not covered by automation: real microphone capture, real remote hosts, real browser surfacing, real widget rendering, real Ollama accuracy, and real TTS audio output. [Certain]

## Known Gaps

- Vision still needs a valid `gemini_api_key`. [Certain]
- Jellyfin title search still needs a valid `jellyfin_api_key`. [Certain]
- STT quality and latency remain environment-dependent even though the code paths are covered. [Certain]
- The semantic store is append-oriented MVP storage, not durable retrieval infrastructure. [Certain]

## Immediate Next Work

1. Keep docs and runtime behavior aligned after each fix. [Certain]
2. Validate the repaired UI and remote paths manually on the real machine, not just through mocks. [Certain]
3. If semantic reuse matters beyond command paraphrases, replace token overlap scoring with embeddings and proper retrieval. [Likely]
