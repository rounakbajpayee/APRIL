# APRIL - Codebase Orientation
> Version: 2.1
> Date: 2026-05-21
> Audience: new sessions and future handoffs

This file is the fast way to recover context before making changes. [Certain]

## One-Paragraph Summary

APRIL is a Windows-hosted assistant that listens from the Copilot key, transcribes audio, routes requests across local intents and remote services, speaks back through TTS, and records enough structured state to explain what happened later. [Certain]

The weak part is still real-world input quality, not code organization: poor STT can still make a good router look broken. [Certain]

## File Map

```text
april/
|-- aprilctl.cmd          easy launcher
|-- aprilctl.ps1          launcher implementation
|-- main.py               request pipeline and lifecycle recording
|-- brain.py              local replies, routing, Ollama planning
|-- widget.py             floating widget and context panel
|-- input_handler.py      Copilot key handling and recording flow
|-- stt.py                local plus remote transcription
|-- tts.py                SAPI and remote say routing
|-- session_manager.py    local or SSH command execution
|-- learning.py           phrase rewrites
|-- memory.py             short-term conversation memory
|-- semantic_store.py     append-only semantic example store
|-- event_ledger.py       canonical event log
|-- state_engine.py       snapshot projection and widget-facing summaries
|-- debug_log.py          lightweight runtime log
|-- stress_test.py        deterministic regression suite
`-- intent/               self-registering tool modules
```

## How Requests Flow

1. `input_handler.py` or the widget text box produces user input. [Certain]
2. `main.py` creates a request id and records lifecycle events. [Certain]
3. `stt.py` returns transcript plus STT metadata for voice input. [Certain]
4. `brain.py` applies learned rewrites and chooses a plan. [Certain]
5. `intent/__init__.py` dispatches to the selected tool. [Certain]
6. `main.py` records result events, stores a semantic example, updates memory, and triggers TTS if needed. [Certain]

## The Routing Order

This matters when debugging misroutes. [Certain]

1. Local utility replies such as time, model, open loops, recent activity, and transcript introspection. [Certain]
2. Trigger-index routing from the registry. [Certain]
3. Full `match()` passes over registered tools. [Certain]
4. Example-based semantic routing from tool `EXAMPLES`. [Certain]
5. Ollama planning. [Certain]
6. Conversation fallback. [Certain]

If a question like `what is the population of India` goes to browser or shell, that is a routing bug. [Certain]
If `open youtube` fails because STT heard something else, that is upstream noise first. [Certain]

## The Semantic Pieces

There are two layers and they are easy to confuse. [Certain]

- `learning.py` rewrites explicit taught phrases like `movie time` into concrete commands. [Certain]
- `intent/registry.py` uses example similarity to map paraphrases like `pull up youtube` before Ollama. [Certain]
- `semantic_store.py` records confirmed turns into `state/semantic_records.jsonl` for future reuse and training export. [Certain]

Weak point: the semantic store is not yet the thing driving most live routing decisions; the example matcher in the registry is doing more immediate work today. [Certain]

## State System

APRIL is not stateless anymore. [Certain]

- `event_ledger.py` writes the source of truth. [Certain]
- `state_engine.py` rebuilds `april_state.json`, `desktop_state.json`, and `context_snapshot.json`. [Certain]
- widget summary cards and open loops are driven from those projections. [Certain]

Useful inspection commands: [Certain]

```powershell
Get-Content .\state\events.jsonl -Tail 20
Get-Content .\state\context_snapshot.json
Get-Content .\logs\debug.jsonl -Tail 20
```

## Remote Paths

- Remote shell uses `session_manager.execute()` with optional `mac_ssh_key` and `dell_ssh_key`. [Certain]
- Remote TTS uses `tts_engine: "say"` and shells out to `say` over SSH. [Certain]
- `at_home` does not actively manage a transport layer; it is mostly a config flag that other code may consult. [Certain]

## Current Test Reality

The suite currently has 22 passing tests. [Certain]

It covers routing, state projection, interruption cleanup, remote key-path wiring, remote `say` routing, semantic example persistence, and example-based semantic routing. [Certain]

It does not prove GUI rendering, live browser surfacing, real device APIs, actual SSH hosts, or actual audio quality. [Certain]

## Practical Advice Before Editing

1. Read `working_memory/CURRENT_TASK.md` first if it exists. [Certain]
2. Run the stress suite before believing any stale doc or memory. [Certain]
3. Treat STT complaints skeptically until you inspect the actual transcript. [Certain]
4. Do not add new docs that restate pre-fix gaps as if they still exist. [Certain]
