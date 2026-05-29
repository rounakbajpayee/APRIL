# APRIL MVP — Human Tester Test Plan
> **Date:** 2026-05-18 · **Build:** Sessions 1–29
> **Purpose:** Systematic UX + code audit before handing back to Codex for hardening.
> Read this fully before starting. Work through sections in order. Log every result.

---

## Before You Begin

### Setup checklist
- [ ] APRIL is running (`python main.py` from `april/`)
- [ ] Widget is visible on screen, bottom-center, showing grey dot + "APRIL" label
- [ ] Mac is on LAN (192.168.0.234) — Ollama and whisper service should be reachable
- [ ] Microphone is connected and working
- [ ] Default browser is set

### How to log results
For each test: mark **PASS**, **FAIL**, or **PARTIAL**. Write exactly what happened — what you said, what APRIL said back, what the widget showed, and whether the side effect occurred (browser opened, volume changed, etc.).

---

## SECTION 1 — Startup and Widget

### 1.1 — Single instance
- Run `python main.py`
- While it's running, run `python main.py` again in another terminal
- **Expected:** Second instance prints "another APRIL instance is already running" and exits immediately
- **Watch for:** Both instances staying alive (mutex broken)

### 1.2 — Widget appearance
- **Expected:** Pill shape, bottom-center of screen, dark background `#111214`, grey dot, "APRIL" text
- **Check:** Is it actually at the bottom-center? Or off-screen, clipped, wrong position?
- **Check:** Is the DPI scaling correct? Does it look crisp on your display?
- **Watch for:** Pill appearing as a rectangle (window region not set), transparent color showing, widget appearing then immediately hiding

### 1.3 — Widget always-on-top
- Open any full-screen or maximised window
- **Expected:** APRIL widget remains visible above it
- **Watch for:** Widget disappearing behind other windows

### 1.4 — Widget collapse
- Leave APRIL idle for ~10 seconds (no interaction)
- **Expected:** Widget collapses to a small dot (46×46px)
- **Watch for:** Widget staying expanded, or collapsing instantly rather than after the delay

### 1.5 — Widget uncollapse
- With widget collapsed to dot, press Copilot key once
- **Expected:** Widget expands back to full pill showing "Listening"
- **Watch for:** Nothing happening, widget staying collapsed

### 1.6 — Widget drag
- Click and drag the widget to a different corner
- Release, wait for it to collapse
- Close APRIL and reopen it
- **Expected:** Widget appears at the position you dragged it to, not back at center-bottom
- **Watch for:** Position not persisting (config write failing silently)

### 1.7 — Right-click context menu
- Right-click the widget
- **Expected:** Menu appears with: Voice ON/OFF, At Home YES/NO, Terminal SHOW/HIDE, Quit APRIL
- Click each toggle, check that the label updates in the menu immediately
- Click Quit — APRIL should close cleanly

### 1.8 — Hover keeps widget expanded
- Let widget collapse to dot
- Hover mouse over the dot
- **Expected:** Widget stays as dot, does not collapse further
- Expand the widget (press key), hover over it
- **Expected:** Widget does not auto-collapse while mouse is over it
- Move mouse away
- **Expected:** Widget collapses after ~7 seconds

---

## SECTION 2 — Copilot Key + Audio Capture

### 2.1 — Single tap (quick press and release)
- Press and release Copilot key in under 0.3 seconds while saying "what time is it"
- **Expected:** Widget shows Listening → Thinking → Speaking → idle with response
- **Watch for:** Key not detected, widget state not updating, audio not captured

### 2.2 — Hold-to-talk
- Hold Copilot key down, say "open youtube", release key
- **Expected:** Same pipeline as above
- **Watch for:** Key release not triggering pipeline

### 2.3 — Double-tap (continuous mode)
- Tap Copilot key twice quickly (within 0.4 seconds)
- Widget should show "Listening" and stay there
- Say a longer phrase, then press Copilot key once more to send
- **Expected:** Widget stays in listening state until second press, then processes
- **Watch for:** Double tap not detected, widget going back to idle after first tap

### 2.4 — Too-short audio rejection
- Tap and release key without saying anything
- **Expected:** Widget returns to idle without attempting transcription
- **Watch for:** Empty audio being sent to whisper and returning garbage

### 2.5 — Copilot suppression
- While APRIL is running, press the Copilot key
- **Expected:** Windows Copilot does NOT open; APRIL handles the key instead
- **Watch for:** Copilot opening alongside APRIL

### 2.6 — Interruption
- Press Copilot key and say something; while APRIL is speaking or thinking, press Copilot key again
- **Expected:** Current TTS stops immediately; widget resets to Listening for new input
- **Watch for:** TTS continuing over itself, widget getting stuck

---

## SECTION 3 — STT (Speech to Text)

### 3.1 — Remote whisper (normal path)
- With mac on LAN, say "what is the capital of France"
- Check APRIL's context panel or debug log for transcript
- **Expected:** Transcript reads "what is the capital of France" or close to it
- **Watch for:** Transcript being empty, garbled, or cut off

### 3.2 — Remote whisper failure fallback
- In `config.json`, temporarily change `whisper_host` to `http://192.168.0.234:9999` (wrong port)
- Say something
- **Expected:** APRIL tries remote, fails, attempts local whisper CLI fallback; either produces transcript or says it couldn't transcribe
- **Watch for:** APRIL crashing, hanging indefinitely, or giving no feedback
- Restore `whisper_host` to `:8001` after

### 3.3 — Silence handling
- Hold Copilot key for 2 seconds in a completely silent room, release
- **Expected:** Transcript is empty, APRIL says "I captured that, but I couldn't transcribe it" or similar, returns to idle
- **Watch for:** Whisper returning confabulated text for silence, APRIL acting on hallucinated transcript

### 3.4 — Non-English input
- Say something in Hindi or another language
- **Expected:** Either transcribes it or returns empty/gibberish; APRIL handles gracefully either way
- **Watch for:** Crash or hang

---

## SECTION 4 — TTS (Text to Speech)

### 4.1 — Basic SAPI voice
- Say "what time is it"
- **Expected:** APRIL speaks the time via Windows SAPI voice
- **Check:** Voice is intelligible, speed is reasonable
- **Watch for:** No audio output, PowerShell window briefly flashing, error logged

### 4.2 — Long response TTS
- Ask "tell me about photosynthesis" (forces Ollama conversation path)
- **Expected:** APRIL speaks a 2–4 sentence response; TTS runs to completion
- **Watch for:** TTS cutting off mid-sentence, PowerShell hanging

### 4.3 — TTS interruption
- Ask something that generates a long spoken response
- While APRIL is speaking, press Copilot key
- **Expected:** Speaking stops immediately, new listening session begins
- **Watch for:** Old PowerShell TTS process continuing, overlap of two voices

### 4.4 — Voice off mode
- Right-click → Voice: OFF
- Ask a question by pressing Copilot key
- **Expected:** APRIL processes normally but does not speak; widget panel appears in text mode
- **Watch for:** SAPI still triggering, widget not switching to text panel

### 4.5 — Voice off → text panel appears
- With voice off: widget should expand to full panel mode (392×378px)
- **Expected:** Context panel visible with summary cards, timeline, open loops, text input box
- **Watch for:** Panel not appearing, panel cut off by screen edge, cards empty

### 4.6 — Text input mode
- With voice off, type "what time is it" in the text box, press Enter or click Send
- **Expected:** Response appears in the output area as "APRIL: It's..." text
- **Watch for:** Nothing happening on Enter, response not appearing, Send button staying disabled after typing

---

## SECTION 5 — Conversation Intent

### 5.1 — Time query
- Say "what time is it"
- **Expected:** "It's [time] on [day]" — answered locally without hitting Ollama
- **Watch for:** Ollama being called for a trivial question (latency spike)

### 5.2 — Model query
- Say "what model are you using"
- **Expected:** "I'm using the Ollama model gemma4:e2b" — answered locally
- **Watch for:** Blank reply

### 5.3 — Joke
- Say "tell me a joke"
- **Expected:** Hardcoded scarecrow joke; answered immediately
- **Watch for:** Ollama being called, wrong joke, no reply

### 5.4 — Free conversation (Ollama path)
- Say "what is the population of India"
- **Expected:** APRIL calls Ollama, returns a factual answer in 1–3 sentences
- **Watch for:** Ollama timeout (30s), empty reply, crash, Ollama not reachable error

### 5.5 — Ollama unavailable
- Stop Ollama on mac temporarily (or set `ollama_host` to a wrong port)
- Ask a conversation question
- **Expected:** "Brain service is unavailable right now" or similar graceful message
- **Watch for:** Crash, hang, empty reply with no feedback
- Restore Ollama after

### 5.6 — Recent activity introspection
- Do a few actions (open YouTube, set volume, ask time)
- Ask "what just happened"
- **Expected:** Bulleted summary of recent debug events — transcripts, intents, results
- **Watch for:** "I don't have any recent activity logged yet" despite activity existing

### 5.7 — What did you hear
- Say something, then immediately ask "what did you transcribe"
- **Expected:** Repeats back the last transcript
- **Watch for:** Wrong transcript, empty reply

### 5.8 — Context awareness
- Ask "what do you know right now"
- **Expected:** Returns current status, voice/home flags, maybe foreground window, open loops
- **Watch for:** Empty reply, stale data

### 5.9 — Conversation memory
- Say "my favourite colour is blue"
- Say "what is my favourite colour"
- **Expected:** Ollama should have context from the recent turn; ideally answers correctly
- **Watch for:** APRIL having no recollection (memory not being injected into prompt)

---

## SECTION 6 — Browser Intent

### 6.1 — Open named site
- Say "open YouTube"
- **Expected:** Default browser opens `https://www.youtube.com`; APRIL says "Opening youtube."
- **Watch for:** Wrong URL, browser not opening

### 6.2 — Open explicit URL
- Say "open https://news.ycombinator.com"
- **Expected:** Browser opens that URL
- **Watch for:** URL not parsed, browser not opening

### 6.3 — Web search
- Say "search for best Python async libraries"
- **Expected:** Browser opens Google search for that query
- **Watch for:** Search query cut off, wrong search engine

### 6.4 — YouTube search
- Say "search YouTube for lo-fi beats"
- **Expected:** Browser opens YouTube results for "lo-fi beats"
- **Watch for:** Google search opened instead, wrong query encoding

### 6.5 — Unknown site
- Say "open twitter"
- **Expected:** Either routes to Ollama which produces a browser plan, OR graceful "I don't have a mapping" reply
- **Watch for:** Crash, silent failure, empty reply

### 6.6 — "Go to" phrasing
- Say "go to github"
- **Expected:** Browser opens `https://github.com`
- **Watch for:** Not recognized as browser intent

---

## SECTION 7 — Device Intent

### 7.1 — Set volume to specific level
- Say "set volume to 30"
- **Expected:** System volume changes to 30%; APRIL confirms "Volume set to 30 percent"
- **Watch for:** Volume not changing, pycaw import error (graceful message), wrong level

### 7.2 — Increase volume
- Say "volume up"
- **Expected:** Volume increases by ~10 percentage points
- **Watch for:** No change, error reply

### 7.3 — Decrease volume
- Say "lower the volume"
- **Expected:** Volume decreases by ~10 points

### 7.4 — Mute
- Say "mute"
- **Expected:** Audio mutes; confirmation spoken/shown

### 7.5 — Set brightness
- Say "set brightness to 70"
- **Expected:** Display brightness changes to 70%; confirmation
- **Watch for:** "not installed" error, no change, driver error on Lenovo

### 7.6 — Open app
- Say "open notepad"
- **Expected:** Notepad opens; APRIL says "Opening notepad."

### 7.7 — Open unmapped app
- Say "open slack"
- **Expected:** "I don't have an app mapping for slack yet." — graceful
- **Watch for:** Silent failure, crash

### 7.8 — Media key — play/pause
- Have Spotify or any media playing
- Say "pause music"
- **Expected:** Media pauses; APRIL says "Toggled playback."

---

## SECTION 8 — Shell Intent

### 8.1 — Local whoami
- Say "run whoami"
- **Expected:** APRIL runs `whoami` via PowerShell locally, summarizes result
- **Watch for:** PowerShell window flashing visibly, empty output, timeout

### 8.2 — Natural language shell — current directory
- Say "what's the current directory"
- **Expected:** APRIL infers `Get-Location`, runs it, summarizes output

### 8.3 — Natural language shell — disk usage
- Say "check disk usage"
- **Expected:** APRIL infers `Get-PSDrive`, runs it, summarizes result readably
- **Watch for:** Raw terminal output dumped verbatim

### 8.4 — Natural language shell — memory usage
- Say "memory usage"
- **Expected:** APRIL runs WMI query, summarizes free/total memory

### 8.5 — Remote shell to mac
- Say "run hostname on mac"
- **Expected:** APRIL SSHes to 192.168.0.234, runs `hostname`, returns result
- **Watch for:** Auth failure (no key configured — likely to fail), timeout
- > **Expected failure mode:** paramiko will try system key discovery. If it fails, APRIL should say "SSH to mac failed: [reason]" cleanly.

### 8.6 — Shell timeout
- Say "run ping 8.8.8.8" (pings indefinitely on Windows)
- **Expected:** Command times out after 20 seconds, APRIL says "The command on local failed: Command timed out after 20 seconds."
- **Watch for:** APRIL hanging indefinitely, widget stuck in thinking state

### 8.7 — Shell summarization quality
- Say "run Get-Process | Sort-Object CPU -Descending | Select-Object -First 5"
- **Expected:** APRIL runs this, Ollama summarizes the table in 1–2 sentences
- **Watch for:** Raw table dumped to TTS (unreadable)

---

## SECTION 9 — Config Intent

### 9.1 — Turn voice off via voice
- Say "turn off voice"
- **Expected:** APRIL speaks "Done. voice set to False." — then voice is off
- Say another question — should get text reply only, widget switches to panel mode

### 9.2 — Turn voice back on via text input
- With voice off, type "turn on voice" in text box
- **Expected:** Voice turns back on, widget collapses back to pill, next responses are spoken

### 9.3 — Away mode
- Say "I'm leaving home"
- **Expected:** `at_home` set to false in config.json; confirmation spoken

### 9.4 — Back home
- Say "I'm home"
- **Expected:** `at_home` set back to true

### 9.5 — Config persistence across restart
- Change a config value (e.g., turn voice off)
- Close APRIL, reopen it
- **Expected:** Voice is still off; widget starts in text panel mode

### 9.6 — Override-only writes
- Look at `config.json` after a voice toggle
- **Expected:** Only the changed key (`"voice": false`) is written; defaults absent
- **Watch for:** Entire default config being written every time

### 9.7 — Teach a phrase
- Say "remember that movie time means open jellyfin"
- **Expected:** "Got it. When you say movie time, I'll treat it as open jellyfin."
- Now say "movie time"
- **Expected:** Jellyfin opens
- **Watch for:** Phrase not learned, rewrite not applied, `learned_phrases.json` not written

---

## SECTION 10 — Media Intent

### 10.1 — Play on Jellyfin
- Say "play Breaking Bad"
- **Expected:** Browser opens Jellyfin search for "Breaking Bad"

### 10.2 — Continue watching
- Say "continue what I was watching"
- **Expected:** Browser opens Jellyfin web UI homepage

### 10.3 — Jellyfin not configured
- Temporarily clear `jellyfin_host` in config
- Say "play something"
- **Expected:** "Jellyfin host is not configured yet." — graceful

---

## SECTION 11 — Vision Intent

### 11.1 — No Gemini key (expected graceful failure)
- With `gemini_api_key` empty in config (default)
- Say "what's on my screen"
- **Expected:** "Vision is not configured yet because the Gemini API key is missing."
- **Watch for:** Crash, ImportError surfacing, silent empty reply

### 11.2 — Vision with key (if you have one)
- Add a Gemini API key to config
- Have something interesting on screen
- Say "what's on my screen"
- **Expected:** Screenshot taken, Gemini replies with a description

---

## SECTION 12 — Widget Context Panel

### 12.1 — Summary cards update
- With voice off (text panel mode visible), do a few interactions
- **Expected:** STATE, FOCUS, LAST HEARD, LAST REPLY cards update after each interaction

### 12.2 — Timeline updates
- Interact a few times, look at TIMELINE section
- **Expected:** Recent interactions appear chronologically

### 12.3 — Open loops
- Trigger a failure (silence transcription, shell timeout)
- Look at OPEN LOOPS section
- **Expected:** The failure appears as a loop item

### 12.4 — FOCUS card
- Have a browser window open, then switch to a code editor, ask APRIL something
- **Expected:** FOCUS card shows the app active at time of request

### 12.5 — Refresh context menu item
- Right-click widget while text panel is open
- **Expected:** "Refresh Context" option appears; clicking it rebuilds the panel

---

## SECTION 13 — State Persistence and Lifecycle

### 13.1 — Event ledger written
- After any interaction, check `april/state/events.jsonl`
- **Expected:** Valid JSONL, each line a JSON object with `id`, `ts`, `event_type`, `payload`

### 13.2 — Snapshot files written
- Check `april/state/context_snapshot.json`
- **Expected:** Valid JSON reflecting recent activity

### 13.3 — Memory file written
- After a conversation exchange, check `april/memory.json`
- **Expected:** `turns` array contains the recent exchange

### 13.4 — Log file written
- Check `april/logs/debug.jsonl`
- **Expected:** Contains structured events with timestamps

### 13.5 — UI history persistence
- Close APRIL with text panel open after several interactions, reopen
- **Expected:** Text panel repopulates with previous history

---

## SECTION 14 — Edge Cases and Robustness

### 14.1 — Rapid-fire key presses
- Press Copilot key 5 times in quick succession
- **Expected:** Last request wins, previous cancelled; no thread pile-up, no overlapping TTS

### 14.2 — Empty text input
- With voice off, submit empty text (or spaces only)
- **Expected:** Nothing happens (Send button disabled, Enter ignored)

### 14.3 — Gibberish input
- Say or type total nonsense ("asdfghjkl blarp fworp")
- **Expected:** Routes to conversation, Ollama attempts a reply; no crash, no unintended action

### 14.4 — Ambiguous intent — open Spotify
- Say "open Spotify"
- **Expected:** Device intent wins (Spotify is in APP_TARGETS); `spotify` command runs
- Check debug log for which intent fired

### 14.5 — Config: voice false on startup
- Set `"voice": false` directly in `config.json`, start APRIL
- **Expected:** Starts in text panel mode immediately without attempting to speak

### 14.6 — Very long spoken input
- Say a 30+ word sentence
- **Expected:** STT processes it fully, no truncation, brain handles it

### 14.7 — Special characters in TTS
- Get APRIL to reply with text containing apostrophes ("I don't know")
- **Expected:** TTS speaks correctly; PowerShell does not crash on the escaped quote

### 14.8 — Mac unreachable mid-session
- Disconnect from LAN while APRIL is running
- Try a shell command to mac, then try a conversation (Ollama also on mac)
- **Expected:** Both fail gracefully with clear messages within timeout
- **Watch for:** 30-second hang before any reply

### 14.9 — Unicode in transcription
- Say something that might produce special characters (names, non-ASCII words)
- **Expected:** Handled without encoding crash

### 14.10 — Config write during active request
- While APRIL is processing, toggle voice via right-click menu
- **Expected:** Config file remains valid JSON; no corruption

---

## SECTION 15 — Known Gaps to Specifically Probe

These are confirmed issues found by reading the code. Test them and document what actually happens.

### 15.1 — TTS `say` path is dead code
- `resolve_engine()` in `tts.py` always returns `"sapi"` regardless of `at_home` or `tts_engine`
- **Test:** Set `tts_engine: "say"` in config, ask something
- **Expected:** Undefined — likely falls back to SAPI silently
- **Report to Codex:** Mac `say` via SSH is not implemented

### 15.2 — `suppress_copilot: false` fallback path
- **Test:** Set `suppress_copilot: false`, restart APRIL
- **Expected:** pynput listener starts; Copilot key works but Windows Copilot may also open
- **Watch for:** pynput not installed, listener not starting

### 15.3 — SSH remote shell has no key file configured
- `session_manager.py` does not pass `key_filename` to paramiko
- **Test:** Say "run hostname on mac"
- **Expected:** Works if SSH key exists in `~/.ssh/` on Lenovo, fails with auth error otherwise
- **Report to Codex:** `mac_ssh_key` / `dell_ssh_key` config keys needed

### 15.4 — Brain prompt files missing
- `prompts/` directory was never created; `soul.md`, `style.md`, `capabilities.md`, `rules.md` do not exist
- **Test:** Ask "who are you" or "what is your name"
- **Expected:** APRIL gives a generic reply with no persona; does not know it is "APRIL"
- **Report to Codex:** Create `prompts/` directory with persona files

### 15.5 — Widget panel on non-standard DPI
- Panel is hardcoded 392×378px
- **Test:** Check if panel fits on screen without clipping at your display scaling setting
- **Watch for:** Panel overflowing bottom of screen, text input cut off

### 15.6 — Ollama model `gemma4:e2b`
- **Verify before testing:** Run `ollama list` on mac; confirm `gemma4:e2b` is present
- If missing: every Ollama call fails; only hardcoded local replies work
- **This may be the single biggest issue**

---

## SECTION 16 — Final Holistic Assessment

Answer these after completing all sections:

1. Does the voice pipeline feel responsive? What is typical end-to-end latency (key press → APRIL finishes speaking)?
2. Is the widget readable at a glance? Does the state label communicate clearly?
3. Do replies feel like APRIL or like a generic chatbot? (Persona gap signal)
4. Is the context panel useful in practice?
5. What was the most confusing moment during testing?
6. Did APRIL ever get stuck in a non-idle state without recovering?
7. Did APRIL ever say something factually wrong or alarming?

---

## Bug Report Format

```
[SECTION X.Y] — SHORT DESCRIPTION
Severity: Critical / High / Medium / Low
What I did: [exact steps]
What happened: [exact output / behaviour]
What was expected: [from this doc]
Reproducible: Yes / No / Sometimes
Notes: [any additional context]
```

---

## Summary of Expected Failures (Known Before Testing)

| # | Issue | Severity | Location |
|---|-------|----------|----------|
| A | `prompts/` directory missing — no APRIL persona | High | `brain.py` `_load_prompt_files()` |
| B | `tts_engine: "say"` path not implemented | High | `tts.py` `resolve_engine()` |
| C | SSH has no key file path — relies on system key discovery | High | `session_manager.py` |
| D | `gemma4:e2b` model may not exist on mac | Critical | `config.json` |
| E | Widget panel 392×378 may clip on non-standard DPI | Medium | `widget.py` constants |
| F | `suppress_copilot: false` falls back to pynput passthrough | Low | `input_handler.py` |
| G | Config writes widget anchor coords even when unchanged from null | Low | `config_intent.py` |

---

## What to Send Back to Codex

After the test, compile:

1. Bug reports in the format above (one per issue)
2. Answers to Section 16 qualitative questions
3. Confirmation of which known gaps (A–G) were actually observed

Tell Codex: **"Do not add new features. Fix what's broken. Work through each issue atomically — one fix, compile check, stress test run — before moving to the next."**
