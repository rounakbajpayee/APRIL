"""
dev.py — APRIL widget hot-reload dev tool
Run this instead of widget.py while tweaking.
Watches widget.py for changes and auto-restarts it on save.
Not part of the APRIL runtime — dev only.
"""

import subprocess
import sys
import os
import time

WATCH_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "widget.py")
PYTHON     = sys.executable

def get_mtime():
    return os.stat(WATCH_FILE).st_mtime

print(f"[dev] watching {WATCH_FILE}")
print(f"[dev] save widget.py to reload — Ctrl+C to quit\n")

last_mtime = get_mtime()
proc = subprocess.Popen([PYTHON, WATCH_FILE])

try:
    while True:
        time.sleep(0.4)
        mtime = get_mtime()
        if mtime != last_mtime:
            last_mtime = mtime
            print("[dev] change detected — restarting...")
            proc.terminate()
            proc.wait()
            proc = subprocess.Popen([PYTHON, WATCH_FILE])
except KeyboardInterrupt:
    print("\n[dev] stopping")
    proc.terminate()
