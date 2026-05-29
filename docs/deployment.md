# Deployment Guide — APRIL

Guidelines for local installation, environment variables, startup triggers, and PyQt setups.

---

## 1. Prerequisites

* **OS:** Windows 10/11 (Lenovo Laptop)
* **Python:** Python 3.12+
* **Dependencies:** PyQt6, PyAudio, Pycaw, and optional Local Whisper CLI configurations.

---

## 2. Environment Configurations

1. Create a `.env` file at the root of the repository:
   ```cmd
   copy .env.example .env
   ```
2. Open `.env` and fill in the required keys:
   - `GEMINI_API_KEY`: Required if you query screenshots and desktop vision commands.

The application loads environment variables during initialization to configure generative AI bindings.

---

## 3. Autostart & Background Configuration

To launch APRIL automatically on Windows startup:
1. Press `Win + R`, type `shell:startup`, and click Enter to open the Windows Startup folder.
2. Right-click inside the folder, select **New -> Shortcut**.
3. Point the shortcut to the `start.cmd` batch file located at the root of your repository.
4. Set the shortcut to run in minimized window mode.

On every Windows login, the script will execute silently and start the APRIL overlay daemon.
