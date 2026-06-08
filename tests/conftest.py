import os
import sys
from unittest.mock import MagicMock, patch
import pytest

# Ensure "src" is in PYTHONPATH so python can locate the modules
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
)

# ---------------------------------------------------------
# PyAudio and Sound Mocks
# ---------------------------------------------------------
try:
    import pyaudio
except ImportError:
    pyaudio_mock = MagicMock()
    # Stub PyAudio object creation
    pyaudio_mock.PyAudio.return_value = MagicMock()
    sys.modules["pyaudio"] = pyaudio_mock

# ---------------------------------------------------------
# Pycaw and Windows Volume Endpoint Mocks
# ---------------------------------------------------------
try:
    import pycaw
except ImportError:
    pycaw_mock = MagicMock()
    sys.modules["pycaw"] = pycaw_mock
    sys.modules["pycaw.pycaw"] = pycaw_mock

# ---------------------------------------------------------
# Screen Brightness Control Mock
# ---------------------------------------------------------
try:
    import screen_brightness_control
except ImportError:
    sbc_mock = MagicMock()
    sys.modules["screen_brightness_control"] = sbc_mock

# ---------------------------------------------------------
# Pynput and Keyboard Hook Mocks
# ---------------------------------------------------------
try:
    import pynput
except ImportError:
    pynput_mock = MagicMock()
    keyboard_mock = MagicMock()
    pynput_mock.keyboard = keyboard_mock
    sys.modules["pynput"] = pynput_mock
    sys.modules["pynput.keyboard"] = keyboard_mock

# ---------------------------------------------------------
# Pyperclip Mock
# ---------------------------------------------------------
try:
    import pyperclip
except ImportError:
    pyperclip_mock = MagicMock()
    sys.modules["pyperclip"] = pyperclip_mock

# ---------------------------------------------------------
# Paramiko SSH Mock
# ---------------------------------------------------------
try:
    import paramiko
except ImportError:
    paramiko_mock = MagicMock()
    sys.modules["paramiko"] = paramiko_mock

# Initialize tests SQLite database
import database
database.init_db()

