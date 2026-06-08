# APRIL

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)
[![Coverage](https://img.shields.io/badge/coverage-90%25-success.svg)](https://github.com)


AI Desktop Copilot and Windows Home Assistant. APRIL acts as a local background daemon that listens for hotkey voice controls, handles speech-to-text, maps intents locally or via fallback LLMs, and performs desktop automation on Windows.

---

## 1. Documentation Index

Detailed guides are located in the [docs/](docs/) directory:
* **[Architecture Guide](docs/architecture.md)**: Details the background execution path, PyQt signal bridge, state authoritative loop, and request/job ID correlation.
* **[Operations Runbook](docs/runbook.md)**: Commands for starting/stopping the daemon, viewing logs, state snapshots, and troubleshooting.
* **[Deployment Guide](docs/deployment.md)**: Guidelines for local environment setup, PyQt window configurations, and Windows Startup configurations.
* **ADR Decisions:** Located in the [docs/adr/](docs/adr/) folder:
  - **[ADR-001: Canonical Observability Tracing](docs/adr/0001-canonical-observability-tracing.md)**
  - **[ADR-002: request_id & job_id Correlation](docs/adr/0002-request-id-job-id-propagation.md)**

---

## 2. Features

* **Dictation Mode:** Transcribe natural speech with real-time stutters cleaning, spoken punctuation parsing (e.g. "comma", "new line" -> `,`, `\n`), and paste back into active editors.
* **Hybrid Intent Routing:** Instant local rule matching for device controls (volume, brightness) and custom phrases, backed by Ollama JSON intent planning fallback.
* **PyQt Overlay Interface:** Sleek, borderless, non-intrusive translucent anchor orb in the screen corner representing assistant status (idle, listening, thinking, speaking).
* **Causal Observability Tracing:** Dedicated background thread logging structured JSON event ledgers with explicit request correlation across async boundaries.

---

## 3. Tech Stack

* **UI Layer:** PyQt6 (Vanilla CSS and custom QPainter paint loops).
* **AI & NLP:** Ollama (default: `gemma4:e2b`), Lens vision service (local VLM, OCR, telemetry).
* **Speech Processing:** OpenAI Whisper (remote endpoint or local CLI fallback).
* **Automation:** Native Windows `ctypes`, `pycaw` (speakers volume), `pynput` (global LowLevel keyboard hooks).

---

## 4. Setup & Running

### A. Quick Setup
1. Create your local config by copying templates:
   ```cmd
   copy config.json.example config.json
   copy memory.json.example memory.json
   copy learned_phrases.json.example learned_phrases.json
   copy .env.example .env
   ```
2. Open `.env` and set `VISION_HOST` to your local Lens service address.
3. Install dependencies inside your virtual environment:
   ```cmd
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

### B. Shortcut Commands
Start and monitor the background service using root-level shortcut commands:
* **`start.cmd`**: Starts APRIL silently in the background (hidden powershell window).
* **`status.cmd`**: Prints whether APRIL is running (gives PID if active).
* **`stop.cmd`**: Stops the active background daemon process.

---

## 5. Running Tests

Run the mocked pytest suite locally:
```powershell
# Run all unit & integration tests
powershell -File scripts/test-host.ps1

# Run tests with code coverage report
powershell -File scripts/test-ci.ps1
```
All hardware devices (microphone, speakers, keyhooks, SSH remote clients) are mocked out in `tests/conftest.py` so tests can run safely on any host.


## License

This project is licensed under the AGPLv3. For commercial use without open-sourcing your application, please contact the author to purchase a commercial license.
