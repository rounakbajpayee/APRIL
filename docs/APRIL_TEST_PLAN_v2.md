# APRIL MVP - Human Test Plan
> Version: 2.1
> Date: 2026-05-21
> Purpose: validate the real runtime after the semantic-routing and UI stabilization pass

This plan is for manual validation on the actual Lenovo host. [Certain]

## Before You Begin

- Run `.venv\Scripts\python.exe stress_test.py -v` and confirm all 22 tests pass. [Certain]
- Start APRIL from `april/` with `.\aprilctl.cmd start` or `python main.py`. [Certain]
- Confirm the widget is visible. [Certain]
- If you want to validate remote features, make sure the Mac is reachable and the configured SSH key actually works. [Certain]

Weak point: the automated suite proves code paths, not user experience, device drivers, or host integration. [Certain]

## Known Gaps To Keep In Mind

- Vision requires a valid `gemini_api_key`. [Certain]
- Jellyfin search requires a valid `jellyfin_api_key`. [Certain]
- Real STT accuracy is still the least stable part of the stack. [Certain]
- `at_home` does not actively manage connections by itself. [Certain]

## Section 1 - Startup And Widget

1. Launch APRIL twice. [Certain]
Expected: the second instance exits with the duplicate-instance message. [Certain]

2. Verify the widget stays on top and collapses to the orb after idle time. [Certain]
Expected: it remains visible above normal windows and collapses only when idle. [Certain]

3. Drag the widget, restart APRIL, and confirm position persistence. [Certain]
Expected: it returns to the stored position unless the saved coordinates are off-screen. The off-screen recovery behavior should be verified manually because it is not clearly enforced in code. [Likely]

4. Click the orb when collapsed. [Certain]
Expected: the context or health panel should reopen. [Likely]

5. Turn voice off and inspect the expanded panel. [Certain]
Expected: larger panel, summary cards, open loops section, scrollable timeline, text input, and resize grip. [Certain]

6. Resize the panel. [Certain]
Expected: it grows and remains usable without clipping core content. [Likely]

## Section 2 - Copilot Key And Audio Flow

1. Single tap while speaking. [Certain]
Expected: listening to thinking to speaking to idle. [Certain]

2. Hold to talk. [Certain]
Expected: same pipeline. [Certain]

3. Double tap for continuous mode. [Certain]
Expected: recording continues until the next trigger press. [Certain]

4. Interrupt while APRIL is speaking. [Certain]
Expected: current speech stops and the new request becomes active. [Certain]

5. Tap without meaningful speech. [Certain]
Expected: transcription unavailable is handled cleanly and creates an open loop entry. [Certain]

## Section 3 - STT

1. Normal transcription with a short clean sentence. [Certain]
Expected: transcript is accurate enough to route correctly. [Likely]

2. Check STT metadata in `logs/debug.jsonl`. [Certain]
Expected: transcript events include fields such as `stt_source` and `stt_model`. [Certain]

3. Silence or noise-only capture. [Certain]
Expected: APRIL does not hallucinate an action and the failure appears in open loops. [Certain]

Weak point: if STT quality is poor, many downstream failures are not routing bugs. [Certain]

## Section 4 - TTS

1. Default spoken reply with `tts_engine: "auto"`. [Certain]
Expected: Windows SAPI speaks the reply. [Certain]

2. Long spoken reply. [Certain]
Expected: widget remains in speaking state until playback actually ends. [Certain]

3. Remote `say` path. [Certain]
Set `tts_engine` to `say`, then ask for a short reply. [Certain]
Expected: APRIL routes `say` over SSH to the configured node. If this fails, verify SSH key, node reachability, and remote `say` availability before blaming `tts.py`. [Likely]

## Section 5 - Conversation And Introspection

1. `what time is it` [Certain]
Expected: instant local reply. [Certain]

2. `what model are you using` and `what module are you using` [Certain]
Expected: both map to the configured Ollama model reply. [Certain]

3. `what just happened` [Certain]
Expected: recent activity summary from the debug log. [Certain]

4. `what do you know right now` [Certain]
Expected: prompt-safe snapshot summary from the state engine. [Certain]

5. `what are your open loops` [Certain]
Expected: current unresolved issues from the snapshot. [Certain]

6. A factual conversation question such as `what is the population of India` [Certain]
Expected: conversation intent, not browser misrouting. [Certain]

## Section 6 - Local Intents

1. Browser actions such as `open youtube`, `go to github`, and `search for async python libraries`. [Certain]
Expected: visible browser launch and sensible reply. [Likely]

2. Device actions such as `set volume to 30`, `mute`, `set brightness to 70`, `open notepad`, and `pause media`. [Certain]
Expected: each routes correctly; `Pause Media` should go to device media-key handling, not Jellyfin open. [Certain]

3. Shell actions such as `run whoami`, `check disk usage`, and `run hostname on mac`. [Certain]
Expected: local commands summarize cleanly; remote commands use configured SSH credentials and fail plainly when auth or reachability is broken. [Certain]

4. Timeout path with a long-running command. [Certain]
Expected: `shell_timeout` behavior is surfaced cleanly and reflected in open loops. [Certain]

## Section 7 - Learning And Semantic Routing

1. Teach a phrase: `remember that movie time means open jellyfin`. [Certain]
Expected: confirmation plus persistence in `learned_phrases.json`. [Certain]

2. Reuse the learned phrase. [Certain]
Expected: it rewrites before routing. [Certain]

3. Try a paraphrase that should hit example-based routing, such as `pull up youtube`. [Certain]
Expected: browser intent without needing Ollama. [Certain]

4. Inspect `state/semantic_records.jsonl` after successful requests. [Certain]
Expected: confirmed requests are stored as semantic examples with intent, action, response, outcome, and metadata. [Certain]

Weak point: semantic routing is still token-overlap based, so edge paraphrases may miss. [Certain]

## Section 8 - State And Context

1. Inspect `state/events.jsonl` after a few interactions. [Certain]
Expected: valid JSONL lifecycle events. [Certain]

2. Inspect `state/context_snapshot.json`. [Certain]
Expected: completed requests clear `active_request`; failures remain visible in open loops. [Certain]

3. Turn voice off, use the panel, and verify cards plus timeline update. [Certain]
Expected: STATE, FOCUS, LAST HEARD, and LAST REPLY reflect recent activity. [Certain]

4. Use `Refresh Context` from the context menu while the panel is open. [Certain]
Expected: panel data repopulates from the latest snapshot and logs. [Likely]

## Section 9 - Report Format

Use this format for any bug: [Certain]

```text
[SECTION X] - SHORT DESCRIPTION
Severity: Critical / High / Medium / Low
What I did: ...
What happened: ...
What I expected: ...
Reproducible: Yes / No / Sometimes
Notes: ...
```

## What To Tell Codex After Testing

- Which failures are real runtime regressions versus STT quality noise. [Certain]
- Whether the widget panel is readable and usable on the actual display scale. [Certain]
- Whether remote `say` and configured SSH keys work on the real environment, not just in tests. [Certain]
- Whether semantic routing helped enough to matter in practice. [Likely]
