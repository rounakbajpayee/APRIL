# APRIL — Codebase Orientation
> **Date:** 2026-05-18 · **For:** Rounak · **Purpose:** Understand what Codex built before you trust it
> Read this before doing anything else. No assumptions about prior knowledge.

---

## The Big Picture in One Paragraph

APRIL is a Python program that runs on your Lenovo (Windows). When you press the Copilot key, it records your voice, sends the audio to your Mac for transcription, sends the text to Ollama on your Mac for understanding, figures out what you want (open a browser, run a shell command, change a setting, etc.), does it, and speaks back using Windows' built-in voice. It also has a small floating window in the corner of your screen that shows what state it's in. Everything it does gets written to log files so you can review what happened.

---

## File Map — What Every File Actually Does

```
april/
├── main.py               ← The conductor. Starts everything, coordinates the pipeline.
├── widget.py             ← The floating pill window you see on screen.
├── input_handler.py      ← Detects the Copilot key press and records your voice.
├── brain.py              ← Figures out what you want and routes it to the right handler.
├── stt.py                ← Sends audio to your Mac's whisper service for transcription.
├── tts.py                ← Makes APRIL speak using Windows SAPI (PowerShell).
├── session_manager.py    ← Runs shell commands locally or via SSH to mac/dell.
├── device_control.py     ← Controls volume, brightness, media keys, app launches.
├── media.py              ← Opens Jellyfin in the browser.
├── screen_capture.py     ← Takes a screenshot and asks Gemini what's on screen.
├── memory.py             ← Remembers recent conversation turns across requests.
├── learning.py           ← Lets you teach APRIL custom phrase shortcuts.
├── observer.py           ← Checks what window is currently in focus on your desktop.
├── event_ledger.py       ← Writes everything that happens to a log file (append-only).
├── state_engine.py       ← Reads the log file and builds a summary of current state.
├── debug_log.py          ← A simpler, lighter log for quick debugging queries.
├── stress_test.py        ← Automated tests. Run this to check if things still work.
├── config.json           ← Your live settings. APRIL reads and writes this.
├── config_defaults.json  ← The factory defaults. Never gets overwritten.
├── memory.json           ← Recent conversation history. Auto-managed.
├── intent/
│   ├── __init__.py       ← Reads the brain's decision and calls the right handler.
│   ├── shell.py          ← Handles "run X" and "check X on mac" type commands.
│   ├── browser.py        ← Handles "open X" and "search for X" commands.
│   ├── device.py         ← Handles volume, brightness, app launch commands.
│   ├── media_intent.py   ← Handles "play X on Jellyfin" commands.
│   ├── config_intent.py  ← Handles "turn off voice", "I'm leaving home", etc.
│   └── conversation.py   ← Handles everything else — falls back to Ollama.
├── state/                ← Auto-generated. Don't edit manually.
│   ├── events.jsonl      ← Every event ever, one JSON per line.
│   ├── context_snapshot.json  ← Current state summary (rebuilt after every event).
│   ├── april_state.json  ← Just the APRIL-specific part of the snapshot.
│   └── desktop_state.json    ← Just the desktop-observation part.
└── logs/
    ├── debug.jsonl       ← Lightweight debug events (simpler than events.jsonl).
    └── ui_history.json   ← Text panel chat history (persisted across restarts).
```

---

## The Request Pipeline — Step by Step

This is exactly what happens when you press the Copilot key and say "open YouTube":

```
1. input_handler.py     detects F23 keydown → starts recording mic audio
2. input_handler.py     detects F23 keyup → stops recording, has WAV bytes
3. main.py              assigns a request ID (e.g. request_7)
4. main.py              calls stt.py with the WAV bytes
5. stt.py               POSTs audio to http://192.168.0.234:8001/v1/audio/transcriptions
6. stt.py               returns "open YouTube"
7. main.py              calls brain.py with "open YouTube"
8. brain.py             recognises this locally as a browser intent (no Ollama needed)
9. brain.py             returns: {intent: "browser", action: {mode: "open_url", url: "https://youtube.com"}}
10. main.py             calls intent/__init__.py with that plan
11. intent/__init__.py  calls intent/browser.py
12. intent/browser.py   calls os.startfile("https://youtube.com") → browser opens
13. intent/browser.py   returns {reply: "Opening https://youtube.com.", ok: True}
14. main.py             calls tts.py with "Opening https://youtube.com."
15. tts.py              runs PowerShell → Add-Type System.Speech → speaks the reply
16. widget.py           shows "Speaking" state, then returns to idle
17. event_ledger.py     all of steps 3–16 are written to state/events.jsonl
18. state_engine.py     rebuilds context_snapshot.json after each event
```

If at step 8, brain.py doesn't recognise the pattern locally, it instead calls Ollama on your Mac and asks it to figure out the intent. That adds ~2–5 seconds of latency.

---

## The Brain's Decision Tree

`brain.py` tries these in order. The first match wins:

```
1. Local reply?    → Hardcoded answers: time, model name, joke, "what just happened", etc.
                     No network call. Instant.

2. Local plan?     → Pattern matching against the text:
                     - config keywords (turn off voice, I'm leaving home...)
                     - device keywords (set volume to X, open app...)
                     - browser keywords (open youtube, search for...)
                     - vision keywords (what's on my screen...)
                     - media keywords (play X, continue watching...)
                     - shell keywords (run X, check disk usage...)
                     No network call. Instant.

3. Ollama plan?    → If neither of the above matched, send the text to Ollama
                     and ask it to return a JSON intent plan.
                     Network call to mac:11434. 2–10 seconds.

4. Fallback?       → If Ollama also fails or returns garbage, treat it as conversation.
                     Calls Ollama again for a plain conversational reply.
```

**Implication:** Most common commands (open X, volume, browser, config) never touch Ollama. Ollama is only needed for free-form requests or anything ambiguous.

---

## Config — What the Settings Actually Do

Open `april/config.json`. These are the important ones:

| Key | What it does | Current value |
|-----|-------------|---------------|
| `voice` | Whether APRIL speaks replies out loud | `true` |
| `at_home` | Whether you're on LAN (affects routing decisions) | `true` |
| `tts_engine` | `"auto"` = SAPI on Windows, `"sapi"` = force SAPI | `"auto"` |
| `ollama_host` | Where APRIL's brain lives | `http://192.168.0.234:11434` |
| `ollama_model` | Which model to use | `"gemma4:e2b"` ← **verify this exists** |
| `whisper_host` | Where STT lives | `http://192.168.0.234:8001` |
| `suppress_copilot` | Whether to block Windows Copilot when key pressed | `true` |
| `shell_timeout_seconds` | How long before a shell command is killed | `20` |
| `brain_timeout_seconds` | How long to wait for Ollama | `30` |
| `stt_mode` | `"remote_first"` tries mac whisper first, then local | `"remote_first"` |
| `gemini_api_key` | Needed for vision ("what's on my screen") | `""` (blank) |
| `jellyfin_api_key` | Needed for Jellyfin search | `""` (blank) |

`config_defaults.json` has the same keys but is never modified. APRIL writes only the *differences* from defaults back to `config.json`.

---

## What Gets Written to Disk (Observability)

You don't need a web UI. These files tell you everything:

### `state/events.jsonl` — The full truth
Every event APRIL records. One JSON object per line. Open in VS Code — it live-updates.

```jsonl
{"id":"evt_abc123","ts":"2026-05-18T10:00:01Z","event_type":"april_started","payload":{}}
{"id":"evt_abc124","ts":"2026-05-18T10:00:05Z","event_type":"transcript_received","payload":{"transcript":"open youtube"}}
{"id":"evt_abc125","ts":"2026-05-18T10:00:05Z","event_type":"intent_planned","payload":{"intent":"browser"}}
{"id":"evt_abc126","ts":"2026-05-18T10:00:05Z","event_type":"action_completed","payload":{"reply":"Opening https://www.youtube.com."}}
```

To tail it in PowerShell:
```powershell
Get-Content april\state\events.jsonl -Wait -Tail 20
```

### `state/context_snapshot.json` — Current state summary
Rebuilt after every event. Shows: current status, last transcript, last reply, active window, open loops, recent timeline. Human-readable JSON — just open it.

### `logs/debug.jsonl` — Lighter debug log
Simpler format. Good for quick checks:
```powershell
Get-Content april\logs\debug.jsonl -Wait -Tail 20
```

### `memory.json` — Conversation history
Shows the last 20 turns APRIL remembers.

### `learned_phrases.json` — Taught shortcuts
Shows every phrase you've taught APRIL via "remember that X means Y".

---

## The Stress Test — What It Covers and How to Run It

```powershell
cd april
python stress_test.py -v
```

**What it tests (11 tests):**
1. Routing — does "open youtube" → browser, "set volume to 40" → device, etc.
2. Learning — teach a phrase, check it rewrites correctly
3. Config writes — are only overrides written, not full defaults
4. Debug introspection — "what just happened" returns real log data
5. Event ledger projection — events written → snapshot built correctly
6. Transcript failure — silence/failure shows up as open loop
7. Execution dispatch — all 8 major command types run without crashing
8. Desktop observation → snapshot — foreground window captured correctly
9. Interrupted request — cancelled request cleared from active state
10. Shell timeout — 124 exit code → `shell_timeout` error kind
11. Main runtime failure/discard — failed actions recorded correctly

**What it doesn't test:**
- Actual audio capture (no mic in tests)
- Actual TTS output (no speakers in tests)
- Actual Ollama responses (mocked)
- Actual browser opening (mocked)
- The widget visually (no GUI in tests)

So the stress tests verify the *logic plumbing*, not the actual user experience. That's why the human test plan matters.

---

## The 4 Biggest Gaps Right Now

These are things Codex didn't finish. They will definitely show up during testing.

### Gap 1 — APRIL has no personality (HIGH)
The `prompts/` directory doesn't exist. `config.json` lists `soul.md`, `style.md`, `capabilities.md`, `rules.md` but none of these files were created.

**Effect:** When Ollama is called, it gets a generic system prompt: *"You are APRIL, a concise home assistant running on a Windows laptop."* That's it. APRIL doesn't know what Citadel is, doesn't know your name, has no character.

**Fix needed:** Create `april/prompts/` and write those 4 files.

### Gap 2 — Mac speaker TTS not implemented (HIGH)
The design doc intended APRIL to speak through your Mac's speakers (via `ssh homelab@mac say "..."`) when at home. This would sound much better than Windows SAPI.

**Effect:** `tts.py` always uses Windows SAPI regardless of `at_home` or `tts_engine` setting. If you set `tts_engine: "say"`, the behavior is undefined (it'll fall to the SAPI path anyway, or error).

**Fix needed:** Implement the `say` branch in `tts.py`.

### Gap 3 — SSH to mac/dell not key-configured (HIGH)
`session_manager.py` connects to mac/dell with `paramiko.connect(host, username=user)` — no `key_filename`. Paramiko will search `~/.ssh/` for keys. If your Lenovo has the right SSH key for mac there, it'll work. If not, it'll fail.

**Effect:** "run hostname on mac" will either work by luck or fail with an auth error.

**Fix needed:** Add `mac_ssh_key` / `dell_ssh_key` to config, pass to paramiko.

### Gap 4 — Ollama model may not exist (CRITICAL)
`config.json` has `"ollama_model": "gemma4:e2b"`. This is an unusual model name.

**How to check right now:**
```bash
# SSH to mac and run:
ollama list
```
If `gemma4:e2b` isn't listed, every single Ollama call fails silently (returns "Brain service is unavailable"). All free-form conversation, intent planning fallback, and command summarization are dead.

**Fix needed:** Either pull `gemma4:e2b` on mac, or change `ollama_model` in config to a model that actually exists (e.g. `qwen2.5:3b` or `qwen3:14b` which you already have).

---

## What Codex Did Well

To be fair — the architecture Codex built is genuinely good for a 1-day sprint:

- **Event ledger + state projection** is real infrastructure. Most toy assistants don't have this.
- **Interruptible request model** (newer request cancels older one) is correct and non-trivial.
- **Override-only config writes** (only diffs from defaults) is thoughtful.
- **Native Win32 hook** for the Copilot key (actually suppresses Windows Copilot) rather than a simpler approach that would have let both run.
- **Stress test harness** that actually isolates file side effects and restores them — properly written tests.
- **Widget** is polished for what it is — animations, hover detection, context panel, drag-and-drop positioning.

The gaps are real but they're finishing work, not rearchitecting work.

---

## The Honest State Assessment

```
Working, probably:        widget UI, Copilot key hook, audio capture, 
                          config toggles, browser actions, local shell,
                          device control (if pycaw installed), 
                          hardcoded local replies (time, joke, etc.)

Working if mac is up:     STT (whisper), Ollama conversation/planning,
                          shell commands to mac/dell (if SSH key works)

Not working at all:       personality/persona (no prompt files),
                          mac say TTS,
                          vision (needs Gemini key),
                          Jellyfin API search (needs API key)

Unknown until tested:     whether gemma4:e2b actually exists on your mac,
                          whether pycaw is installed in the venv,
                          whether screen-brightness-control works on Lenovo
```

---

## Before Any Testing — Do These 3 Things

**1. Verify the Ollama model exists (on mac):**
```bash
ssh homelab@192.168.0.234 "ollama list"
```
If `gemma4:e2b` is missing, update `config.json`:
```json
"ollama_model": "qwen2.5:3b"
```
(or whichever model you have)

**2. Check the venv has the dependencies installed:**
```powershell
cd april
.venv\Scripts\python.exe -c "import pynput, pyaudio, paramiko, requests; print('ok')"
```
Any ImportError here means that dependency is missing from the venv.

**3. Run the stress tests:**
```powershell
.venv\Scripts\python.exe stress_test.py -v
```
All 11 should pass. If any fail before you've even touched the app, that's a Codex bug.

---

## Glossary

| Term | Meaning in this project |
|------|------------------------|
| intent | What APRIL thinks you want: shell / browser / device / config / media / vision / conversation |
| plan | The JSON object brain.py returns: `{intent, action, response_preview}` |
| event | A structured JSON record written to `events.jsonl` every time something happens |
| snapshot | The current-state summary rebuilt from events — lives in `context_snapshot.json` |
| open loop | Something that went wrong and hasn't been resolved — shown in widget context panel |
| at_home | Config flag meaning "I'm on LAN, mac and dell are reachable" |
| suppress_copilot | Whether APRIL intercepts the key before Windows Copilot sees it |
