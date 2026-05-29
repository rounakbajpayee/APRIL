# APRIL — Design Document
> **Version:** 0.2 · **Date:** 2026-05-18 · **Status:** Pre-build (step 1 in progress)
> Autonomous Personal Reasoning & Intelligence Layer — Primitive Implementation
> This document is the single source of truth for building APRIL from scratch.
> If tokens run out mid-session, hand this doc to a new model and continue.

---

## What APRIL Is

A locally-running personal assistant on the Lenovo Yoga Slim 7i (Windows, daily driver).
Activated by the Copilot key. Always listening when active. Speaks back via system TTS.
Executes commands on local machine and remote nodes (mac, dell) over SSH.
Classifies every utterance into one of six intent categories and routes accordingly.
Designed to look impressive — the Tony Stark aesthetic is a first-class requirement.

This is a primitive implementation of the larger APRIL vision (the homelab orchestrator).
It is a standalone project. It does not depend on the homelab stack being up.
It degrades gracefully when homelab services are offline.

---

## Hardware Context

| Machine | Role | OS | Notes |
|---------|------|----|-------|
| Lenovo Yoga Slim 7i (Core Ultra 7 155H, 16GB) | APRIL host | Windows 11 | Daily driver, script runs here |
| Apple Mac Mini M4 (16GB) | Inference + voice | macOS | Ollama, faster-whisper @ :8001, say command |
| Dell XPS 9360 (8GB) | Apps + storage | Debian | Docker services, Jellyfin, n8n etc. |

**Network:**
- At home: all three on LAN (192.168.x.x) + Tailscale overlay
- Mac LAN IP: 192.168.0.234 · Tailscale: 100.70.3.86
- Dell LAN IP: 192.168.0.162 · Tailscale: 100.103.208.28
- Away: Tailscale only

---

## Copilot Key — CONFIRMED

Verified on hardware 2026-05-18 using pynput.

**The Copilot key fires: `Win + Shift + F23`**

- `Key.cmd` (VK 91) down
- `Key.shift` (VK 160) down
- `Key.f23` (VK 134) down — this is the unique trigger
- All three release in reverse order

**Detection strategy:** hook on `Key.f23` keydown (while Win+Shift are held).
F23 is the unique identifier — nothing else on the system fires it.
Use `pynput` for the hook (confirmed working, no admin required for detection).

---

## Repository Structure

```
april/
├── main.py                  # Entry point — starts all subsystems
├── config.json              # Runtime config — read/written by APRIL
├── config_defaults.json     # Default config — never overwritten
├── widget.py                # Floating always-on-top UI widget
├── input_handler.py         # Copilot key hook + audio capture
├── stt.py                   # Speech-to-text — faster-whisper via HTTP
├── brain.py                 # LLM intent classification + response (Ollama)
├── tts.py                   # TTS router — say/SAPI/espeak-ng
├── session_manager.py       # SSH session pool + Windows Terminal pane control
├── device_control.py        # Local Lenovo device control
├── media.py                 # Jellyfin API + browser launcher
├── screen_capture.py        # Screenshot + Gemini Flash vision queries
├── intent/
│   ├── __init__.py
│   ├── shell.py             # SSH/shell intent handler
│   ├── device.py            # Device control intent handler
│   ├── browser.py           # Browser/URL intent handler
│   ├── media_intent.py      # Media playback intent handler
│   ├── config_intent.py     # Config change intent handler
│   └── conversation.py      # Pure conversation intent handler
├── prompts/
│   ├── system.txt           # APRIL system prompt for gemma4:e2b
│   ├── classify.txt         # Intent classification prompt
│   └── summarise.txt        # Command output summarisation prompt
├── requirements.txt
├── start_april.bat          # Windows Task Scheduler entry point
└── README.md
```

---

## Config Schema

`config.json` — read at startup, written on any config change command, watched for changes.

```json
{
  "voice": true,
  "at_home": true,
  "tts_engine": "auto",
  "terminal_visible": true,
  "active_sessions": [],
  "ollama_host": "http://192.168.0.234:11434",
  "ollama_model": "gemma4:e2b",
  "whisper_host": "http://192.168.0.234:8001",
  "mac_ssh_host": "192.168.0.234",
  "mac_ssh_user": "homelab",
  "dell_ssh_host": "192.168.0.162",
  "dell_ssh_user": "homelab",
  "jellyfin_host": "http://media.home.lan",
  "jellyfin_api_key": "",
  "gemini_api_key": "",
  "vision_model": "gemini-2.5-flash"
}
```

**`tts_engine` values:**
- `"auto"` — use mac `say` if at_home and SSH alive, else SAPI
- `"say"` — force mac say via SSH
- `"sapi"` — force Windows SAPI (PowerShell)
- `"espeak"` — force espeak-ng in WSL

**Away mode:** when `at_home` set to false, mac SSH channel closes, tts_engine auto-switches to SAPI.

---

## Intent Categories

Every utterance is classified into exactly one of these by the LLM before any action is taken.

| Intent | Examples | Handler |
|--------|----------|---------|
| `shell` | "connect to mac", "check network load on dell", "what's in the oracle folder" | `intent/shell.py` |
| `device` | "set volume to 50", "increase brightness", "open Spotify" | `intent/device.py` |
| `browser` | "open YouTube", "search for lo-fi beats on YouTube" | `intent/browser.py` |
| `media` | "play Family Guy on Jellyfin", "continue what I was watching" | `intent/media_intent.py` |
| `config` | "turn off voice", "I'm leaving home", "show the terminal", "switch to WSL voice" | `intent/config_intent.py` |
| `vision` | "what's on my screen", "what's this error", "read this for me" | `screen_capture.py` + Gemini |
| `conversation` | "what time is it in London", "remind me what we discussed" | `intent/conversation.py` |

---

## Component Design + Pseudocode

### 1. main.py — Entry Point

```python
# Pseudocode

on startup:
    load config.json
    init widget (start in tray, always on top)
    if config.voice and config.at_home:
        open persistent SSH channel to mac (for say)
    start input_handler (register Copilot key hook)
    start config file watcher (reload on change)
    widget.set_state("idle")
    block until shutdown signal
```

---

### 2. widget.py — Floating Widget

Always-on-top small window. Sits in corner. Shows current state + active node.

**States and colors:**
- `idle` — grey dot — "APRIL"
- `listening` — green pulsing — "listening..."
- `thinking` — amber — "thinking..."
- `speaking` — blue — "speaking..."
- `error` — red — short error message

**Layout:**
```
╭──────────────────╮
│ ● APRIL  [MAC]   │
│ "checking logs…" │
╰──────────────────╯
```

```python
# Pseudocode

class Widget:
    init:
        create tkinter Tk window
        set always_on_top = True
        set window_alpha = 0.92
        position: bottom-right corner
        no title bar, no taskbar entry
        bind right-click → context menu (quit, toggle voice, toggle terminal)

    set_state(state, message="", node=""):
        update dot color based on state
        update label text
        update node indicator

    context_menu:
        options: quit | voice on/off | show/hide terminal | at_home toggle
        each option writes to config.json and calls relevant handler
```

---

### 3. input_handler.py — Copilot Key + Audio Capture

**Copilot key combo: Win + Shift + F23**
Hook on F23 keydown as the trigger (unique, nothing else fires it).
Use pynput for the listener — confirmed working on this hardware without admin.

```python
# Pseudocode

TRIGGER_KEY = Key.f23
HOLD_THRESHOLD = 0.3 seconds
DOUBLE_TAP_WINDOW = 0.4 seconds

state = idle
f23_down_time = None
last_tap_time = None

on key_down(key):
    if key == TRIGGER_KEY:
        f23_down_time = now
        start recording audio (PyAudio, 16kHz mono)
        widget.set_state("listening")
        state = recording_hold

    elif state == continuous_recording and key == TRIGGER_KEY:
        # second press in continuous mode — send
        stop recording
        pipeline(audio_buffer)
        state = idle

on key_up(key):
    if key != TRIGGER_KEY:
        return

    elapsed = now - f23_down_time

    if elapsed < HOLD_THRESHOLD:
        # tap — check double tap
        if last_tap_time and (now - last_tap_time) < DOUBLE_TAP_WINDOW:
            # double tap → continuous mode
            state = continuous_recording
            widget.set_state("listening")
            # keep recording, don't send yet
        else:
            last_tap_time = now
            stop recording
            if audio_length > 0.5s:
                pipeline(audio_buffer)
            state = idle
    else:
        # hold-to-talk release
        stop recording
        pipeline(audio_buffer)
        state = idle

def pipeline(audio_bytes):
    text = stt.transcribe(audio_bytes)
    if not text.strip():
        widget.set_state("idle")
        return
    widget.set_state("thinking")
    intent, response, action = brain.process(text)
    execute_intent(intent, action)
    widget.set_state("speaking")
    tts.speak(response)
    widget.set_state("idle")
```

---

### 4. stt.py — Speech to Text

Sends audio to faster-whisper HTTP service on mac port 8001.
Falls back to local whisper CLI if mac is unreachable.

```python
# Pseudocode

def transcribe(audio_bytes) -> str:
    try:
        POST http://config.whisper_host/v1/audio/transcriptions
            file = audio_bytes (WAV format)
            model = "whisper-1"
        return response.text

    except ConnectionError:
        # fallback: local whisper if installed
        write audio_bytes to /tmp/april_input.wav
        run: whisper /tmp/april_input.wav --model base --output_format txt
        return contents of output txt file

    except all else:
        return ""
```

---

### 5. brain.py — Intent Classification + Response

Two-pass LLM interaction:
1. Classify intent + extract action parameters
2. After action executes, summarise raw output into natural language

Model: gemma4:e2b via Ollama on mac.

```python
# Pseudocode

SYSTEM_PROMPT = load("prompts/system.txt")

def process(text) -> (intent, response, action_params):

    prompt = f"""
    User said: "{text}"
    Current context: active_node={session_manager.active_node}, at_home={config.at_home}

    Classify the intent into one of:
    shell | device | browser | media | config | vision | conversation

    If shell: extract target_node (mac/dell/local) and natural language description of command
    If device: extract action (volume/brightness/open_app) and value
    If browser: extract url or search query
    If media: extract title, media_type
    If config: extract setting and value
    If vision: extract question about screen
    If conversation: just answer

    Respond as JSON only:
    {{
      "intent": "...",
      "response_preview": "one sentence confirming what you're about to do",
      "action": {{ ... intent-specific params ... }}
    }}
    """

    result = ollama_call(SYSTEM_PROMPT, prompt)
    parsed = json.loads(result)
    return parsed.intent, parsed.response_preview, parsed.action


def summarise(raw_output, original_request) -> str:
    prompt = f"""
    The user asked: "{original_request}"
    The command returned this raw output:
    {raw_output}

    Summarise in 1-3 natural language sentences.
    Do not dump raw output. Extract what matters.
    Be concise. Sound like a person, not a terminal.
    """
    return ollama_call(SYSTEM_PROMPT, prompt)


def ollama_call(system, user) -> str:
    POST http://config.ollama_host/api/chat
        model = config.ollama_model
        messages = [
            {role: "system", content: system},
            {role: "user", content: user}
        ]
        stream = False
    return response.message.content
```

---

### 6. tts.py — Voice Output Router

```python
# Pseudocode

def speak(text):
    if not config.voice:
        return

    engine = resolve_engine()

    if engine == "say":
        ssh_channel.exec_command(f'say "{escape(text)}"')

    elif engine == "sapi":
        subprocess.run([
            "powershell", "-Command",
            f'Add-Type -AssemblyName System.Speech; '
            f'(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak("{escape(text)}")'
        ])

    elif engine == "espeak":
        subprocess.run(["wsl", "espeak-ng", f'"{escape(text)}"'])


def resolve_engine() -> str:
    if config.tts_engine != "auto":
        return config.tts_engine
    if config.at_home and ssh_mac_alive():
        return "say"
    return "sapi"


def ssh_mac_alive() -> bool:
    return mac_ssh_channel is not None and mac_ssh_channel.active
```

---

### 7. session_manager.py — SSH Session Pool + Terminal Panes

```python
# Pseudocode

sessions = {}  # { "mac": SSHSession, "dell": SSHSession, "local": LocalSession }

class SSHSession:
    node: str
    client: paramiko.SSHClient
    pane_id: str | None
    visible: bool
    last_used: datetime

class LocalSession:
    node: "local"
    pane_id: str | None
    visible: bool


def get_or_create(node) -> Session:
    if node in sessions and sessions[node].is_alive():
        return sessions[node]
    return connect(node)


def connect(node) -> Session:
    if node == "local":
        pane_id = spawn_terminal_pane("wsl") if config.terminal_visible else None
        return LocalSession(pane_id=pane_id)

    creds = get_creds(node)
    client = paramiko.SSHClient()
    client.connect(creds.host, username=creds.user, key_path=creds.key)
    pane_id = spawn_terminal_pane(f"ssh {creds.user}@{creds.host}") if config.terminal_visible else None
    return SSHSession(node=node, client=client, pane_id=pane_id)


def execute(node, command) -> str:
    session = get_or_create(node)
    stdin, stdout, stderr = session.client.exec_command(command)
    return stdout.read().decode() or stderr.read().decode()


def spawn_terminal_pane(command) -> str:
    subprocess.Popen(["wt", "-w", "0", "sp", "--title", f"APRIL:{command}", "--", *command.split()])
    return generate_pane_id()


def show_all_panes():
    subprocess.run(["wt", "-w", "0", "fa"])

def hide_all_panes():
    subprocess.run(["powershell", "-Command",
        "(Get-Process WindowsTerminal).MainWindowHandle | foreach { [void][Win32]::ShowWindow($_, 6) }"])
```

---

### 8. device_control.py — Lenovo Device Control

```python
# Pseudocode

def set_volume(level: int):
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, ...)
    volume = interface.QueryInterface(IAudioEndpointVolume)
    volume.SetMasterVolumeLevelScalar(level / 100, None)

def set_brightness(level: int):
    import screen_brightness_control as sbc
    sbc.set_brightness(level)

def open_app(app_name: str):
    app_map = {
        "spotify": "spotify",
        "chrome": "chrome",
        "terminal": "wt",
        "youtube": "https://youtube.com",
    }
    target = app_map.get(app_name.lower())
    if target.startswith("http"):
        webbrowser.open(target)
    else:
        subprocess.Popen([target])

def media_key(action: str):
    import ctypes
    VK_MAP = {
        "play_pause": 0xB3,
        "next": 0xB0,
        "prev": 0xB1,
        "mute": 0xAD
    }
    vk = VK_MAP.get(action)
    if vk:
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
```

---

### 9. media.py — Jellyfin + Browser

```python
# Pseudocode

def play_on_jellyfin(title: str):
    results = GET {jellyfin_host}/Items
        params: searchTerm=title, IncludeItemTypes=Episode|Movie
        headers: X-Emby-Token = config.jellyfin_api_key

    if no results:
        return "Could not find that on Jellyfin"

    item = results[0]
    user_id = get_jellyfin_user_id()
    userdata = GET {jellyfin_host}/Users/{user_id}/Items/{item.Id}
    resume_ticks = userdata.UserData.PlaybackPositionTicks
    url = f"{jellyfin_host}/web/index.html#!/video?id={item.Id}&startPositionTicks={resume_ticks}"
    webbrowser.open(url)
    return f"Opening {item.Name} on Jellyfin"

def open_url(url: str):
    webbrowser.open(url)

def youtube_search(query: str):
    import urllib.parse
    webbrowser.open(f"https://www.youtube.com/search?q={urllib.parse.quote(query)}")
```

---

### 10. screen_capture.py — Vision Queries

```python
# Pseudocode

def capture_and_query(question: str) -> str:
    import mss, base64
    with mss.mss() as sct:
        screenshot = sct.grab(sct.monitors[0])
        img_bytes = mss.tools.to_png(screenshot.rgb, screenshot.size)

    img_b64 = base64.b64encode(img_bytes).decode()

    import google.generativeai as genai
    genai.configure(api_key=config.gemini_api_key)
    model = genai.GenerativeModel(config.vision_model)
    response = model.generate_content([
        f"The user is looking at their screen and asks: {question}",
        f"Answer based only on what you can see in this screenshot.",
        {"mime_type": "image/png", "data": img_b64}
    ])
    return response.text
```

---

### 11. config_intent.py — Config Changes via Voice

```python
# Pseudocode

def handle(action_params):
    key = action_params.setting
    value = action_params.value
    config[key] = value
    write_config()

    if key == "at_home" and not value:
        session_manager.close_mac_voice_channel()
    if key == "at_home" and value:
        if config.voice:
            session_manager.open_mac_voice_channel()
    if key == "terminal_visible":
        session_manager.show_all_panes() if value else session_manager.hide_all_panes()

    widget.update_from_config()
    return f"Done. {key} set to {value}."
```

---

## TTS Fallback Chain

```
voice=true, at_home=true
    → say via persistent SSH to mac
    → fail → SAPI (Windows PowerShell)
    → fail → espeak-ng (WSL)
    → fail → text only

voice=true, at_home=false
    → SAPI (Windows PowerShell)
    → fail → espeak-ng (WSL)
    → fail → text only

voice=false → text only always
```

---

## Startup Sequence

```
1. Load config.json (fall back to config_defaults.json if missing)
2. Start widget (idle state)
3. If voice=true and at_home=true:
       open persistent SSH to mac
       test say → if fails, warn, fall back to SAPI
4. Test Ollama reachability → if fails, warn in widget, still start
5. Test whisper reachability → if fails, warn, use local fallback
6. Register Copilot key hook via pynput (no admin required)
7. Widget shows idle — APRIL is ready
```

---

## Boot on Startup

`start_april.bat` registered with Windows Task Scheduler:
- Trigger: on logon
- Run with highest privileges: YES (for global key hook reliability)
- Run whether user logged on or not: NO (needs GUI for widget)

```bat
@echo off
cd C:\Users\rouna\april
python main.py
```

---

## Dependencies

```
# requirements.txt
pynput                       # global hotkey hook (confirmed working, no admin needed)
pyaudio                      # mic audio capture
paramiko                     # SSH sessions
mss                          # screen capture
Pillow                       # image handling
pycaw                        # Windows audio control
screen-brightness-control    # display brightness
requests                     # HTTP to Ollama, whisper, Jellyfin
google-generativeai          # Gemini Flash vision
# tkinter — stdlib, no install needed
```

---

## Build Order

1. `widget.py` + `main.py` stub — widget on screen ✳ IN PROGRESS
2. `input_handler.py` — Copilot key (Win+Shift+F23 via pynput F23 hook) + audio capture
3. `stt.py` — audio → text via whisper @ mac:8001
4. `brain.py` — text → intent JSON via Ollama gemma4:e2b
5. `tts.py` — text → speech via say/SAPI fallback chain
6. `session_manager.py` — SSH sessions + Windows Terminal panes
7. `intent/shell.py` — shell commands executing and summarised
8. `config_intent.py` — voice config changes
9. `device_control.py` — volume, brightness, app launch
10. `media.py` — Jellyfin + browser
11. `screen_capture.py` — vision queries via Gemini

---

## Known Constraints / Gotchas

- **Copilot key confirmed:** Win+Shift+F23. Hook on F23 keydown only — Win and Shift will already be down.
- **pynput no admin needed** — confirmed on this hardware. Do not use `keyboard` lib (requires admin).
- PyAudio on Windows requires Microsoft C++ Build Tools or pre-built wheel from Gohlke.
- paramiko SSH to mac requires key-based auth — key path in config.
- Windows Terminal `wt` pane IDs not reliably retrievable — treat pane management as fire-and-forget.
- `pycaw` Windows only — guard imports with platform check.
- Gemini API key must not be in a public repo — load from env var, fall back to config.json.
- faster-whisper endpoint format: confirm against actual service at mac:8001 before wiring stt.py.
- `say` over SSH is non-blocking — speech plays on mac speaker while script continues.
- Ollama on mac may be slow if other inference is simultaneously running (Qwen3 14B pull pending).

---

## Future Scope (Not in This Version)

- Always-on ambient screen/camera capture (Limitless-style post-call analysis)
- Integration with homelab APRIL (Oracle ingest, VELA, agent loop)
- Mobile companion (iPhone interface to this APRIL instance)
- Wake word instead of / in addition to hotkey
- Multi-monitor support for screen capture
- Proactive alerts (APRIL speaks unprompted on homelab events)
