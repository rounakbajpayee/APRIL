"""
input_handler.py - Copilot key hook and microphone capture.

The Copilot key presents as Win+Shift+F23 on this machine. This module owns
the key timing state and returns captured audio as WAV bytes to the main
pipeline. STT/brain/TTS are deliberately outside this file.
"""

import ctypes
import ctypes.wintypes
import io
import os
import threading
import time
import wave
from datetime import datetime, timezone

from runtime_state_sink import RuntimeStateSink
from tts import speak as speak_reply


TRIGGER_KEY_NAME = "Key.f23"
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_CHANNELS = 1
DEFAULT_CHUNK_SIZE = 1024
SAMPLE_WIDTH_BYTES = 2
WH_KEYBOARD_LL = 13
HC_ACTION = 0
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012
VK_F23 = 0x86

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", ctypes.wintypes.DWORD),
        ("scanCode", ctypes.wintypes.DWORD),
        ("flags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.wintypes.ULONG)),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.wintypes.LPARAM,
    ctypes.c_int,
    ctypes.wintypes.WPARAM,
    ctypes.wintypes.LPARAM,
)

user32.SetWindowsHookExW.argtypes = [
    ctypes.c_int,
    HOOKPROC,
    ctypes.wintypes.HINSTANCE,
    ctypes.wintypes.DWORD,
]
user32.SetWindowsHookExW.restype = ctypes.wintypes.HHOOK
user32.CallNextHookEx.argtypes = [
    ctypes.wintypes.HHOOK,
    ctypes.c_int,
    ctypes.wintypes.WPARAM,
    ctypes.wintypes.LPARAM,
]
user32.CallNextHookEx.restype = ctypes.wintypes.LPARAM
user32.UnhookWindowsHookEx.argtypes = [ctypes.wintypes.HHOOK]
user32.UnhookWindowsHookEx.restype = ctypes.wintypes.BOOL
user32.GetMessageW.argtypes = [
    ctypes.POINTER(ctypes.wintypes.MSG),
    ctypes.wintypes.HWND,
    ctypes.wintypes.UINT,
    ctypes.wintypes.UINT,
]
user32.GetMessageW.restype = ctypes.wintypes.BOOL
user32.PostThreadMessageW.argtypes = [
    ctypes.wintypes.DWORD,
    ctypes.wintypes.UINT,
    ctypes.wintypes.WPARAM,
    ctypes.wintypes.LPARAM,
]
user32.PostThreadMessageW.restype = ctypes.wintypes.BOOL
kernel32.GetModuleHandleW.argtypes = [ctypes.wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = ctypes.wintypes.HMODULE
kernel32.GetCurrentThreadId.argtypes = []
kernel32.GetCurrentThreadId.restype = ctypes.wintypes.DWORD

TRACE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "startup_trace.log")


def trace_startup(message: str) -> None:
    os.makedirs(os.path.dirname(TRACE_PATH), exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    with open(TRACE_PATH, "a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} [input_handler] {message}\n")


class AudioUnavailable(RuntimeError):
    pass


class AudioRecorder:
    def __init__(self, config):
        self.sample_rate = int(config.get("audio_sample_rate", DEFAULT_SAMPLE_RATE))
        self.channels = int(config.get("audio_channels", DEFAULT_CHANNELS))
        self.chunk_size = int(config.get("audio_chunk_size", DEFAULT_CHUNK_SIZE))
        self._pyaudio = None
        self._pa = None
        self._stream = None
        self._frames = []
        self._thread = None
        self._recording = threading.Event()
        self._started_at = None
        self._lock = threading.Lock()

    def _load_pyaudio(self):
        if self._pyaudio is not None:
            return self._pyaudio
        try:
            import pyaudio
        except ImportError as exc:
            raise AudioUnavailable("PyAudio is not installed") from exc
        self._pyaudio = pyaudio
        return pyaudio

    def start(self):
        with self._lock:
            if self._recording.is_set():
                return
            pyaudio = self._load_pyaudio()
            self._pa = pyaudio.PyAudio()
            self._frames = []
            self._started_at = time.monotonic()
            self._recording.set()
            self._stream = self._pa.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size,
            )
            self._thread = threading.Thread(target=self._capture_loop, daemon=True)
            self._thread.start()

    def _capture_loop(self):
        while self._recording.is_set():
            try:
                data = self._stream.read(self.chunk_size, exception_on_overflow=False)
            except Exception:
                break
            self._frames.append(data)

    def stop(self):
        with self._lock:
            if not self._recording.is_set():
                return b"", 0.0
            self._recording.clear()
            duration = time.monotonic() - self._started_at if self._started_at else 0.0

        if self._thread:
            self._thread.join(timeout=1.0)

        with self._lock:
            try:
                if self._stream:
                    self._stream.stop_stream()
                    self._stream.close()
            finally:
                self._stream = None
                if self._pa:
                    self._pa.terminate()
                    self._pa = None

            frames = list(self._frames)
            self._frames = []
            self._started_at = None

        return self._to_wav(frames), duration

    def _to_wav(self, frames):
        if not frames:
            return b""
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(self.channels)
            wav.setsampwidth(SAMPLE_WIDTH_BYTES)
            wav.setframerate(self.sample_rate)
            wav.writeframes(b"".join(frames))
        return buffer.getvalue()


class NativeCopilotHook:
    def __init__(self, handler):
        self.handler = handler
        self._hook = None
        self._callback = None
        self._thread = None
        self._thread_id = None
        self._ready = threading.Event()
        self._error = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=2.0)
        if self._error:
            raise RuntimeError(self._error)
        return self._hook is not None

    def stop(self):
        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)
            self._hook = None
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _run(self):
        self._thread_id = kernel32.GetCurrentThreadId()
        self._callback = HOOKPROC(self._hook_proc)
        module = kernel32.GetModuleHandleW(None)
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._callback, module, 0)
        if not self._hook:
            self._error = "could not install native Copilot key hook"
            self._ready.set()
            return
        self._ready.set()
        msg = ctypes.wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            pass

    def _hook_proc(self, n_code, w_param, l_param):
        if n_code == HC_ACTION:
            event = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if event.vkCode == VK_F23:
                # Filter injected events: the Copilot key fires a synthetic
                # injected event (LLKHF_INJECTED, flags bit 4 = 0x10) before
                # the real hardware event.  Ignore injected events so that
                # only the real keydown/keyup reaches the handler.
                LLKHF_INJECTED = 0x10
                if event.flags & LLKHF_INJECTED:
                    return 1  # suppress but do not dispatch
                if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    threading.Thread(target=self.handler._handle_trigger_press, daemon=True).start()
                elif w_param in (WM_KEYUP, WM_SYSKEYUP):
                    threading.Thread(target=self.handler._handle_trigger_release, daemon=True).start()
                return 1
        return user32.CallNextHookEx(self._hook, n_code, w_param, l_param)


class InputHandler:
    def __init__(
        self,
        surface: RuntimeStateSink | None,
        config: dict,
        on_audio=None,
        on_interrupt=None,
    ):
        self._surface = surface
        self.config = config
        self.on_audio = on_audio
        self.on_interrupt = on_interrupt
        self.recorder = AudioRecorder(config)
        self.listener = None
        self.native_hook = None
        self.state = "idle"
        self.f23_down_time = None
        self.last_tap_time = None
        self.trigger_down = False
        self.hold_threshold = float(config.get("copilot_hold_threshold", 0.3))
        self.double_tap_window = float(config.get("copilot_double_tap_window", 0.4))
        self.min_audio_seconds = float(config.get("copilot_min_audio_seconds", 0.5))
        self._lock = threading.Lock()

    def _update_surface_state(self, state: str, *args, **kwargs) -> None:
        """Notify the runtime state sink of a state transition.

        Extra positional/keyword args are accepted and silently dropped so
        call-sites that pass descriptive text (e.g. _update_surface_state("error",
        msg)) do not need to be rewritten in this pass.
        """
        if self._surface is not None:
            self._surface.set_state(state)

    def start(self):
        trace_startup(f"InputHandler.start suppress_copilot={bool(self.config.get('suppress_copilot', True))}")
        if bool(self.config.get("suppress_copilot", True)):
            try:
                self.native_hook = NativeCopilotHook(self)
                if self.native_hook.start():
                    trace_startup("native hook installed successfully")
                    return True
                trace_startup("native hook start returned false")
            except Exception as exc:
                trace_startup(f"native hook failed: {exc}")
                self._update_surface_state("error", str(exc))
                return False

        try:
            from pynput import keyboard
        except ImportError:
            trace_startup("pynput import failed")
            self._update_surface_state("error", "pynput not installed")
            return False

        self.listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
            suppress=False,
        )
        self.listener.start()
        trace_startup("pynput listener started")
        return True

    def stop(self):
        if self.native_hook:
            self.native_hook.stop()
            self.native_hook = None
        if self.listener:
            self.listener.stop()
            self.listener = None
        if self.state in {"recording_hold", "continuous_recording"}:
            self._stop_recording(send=False)

    def _is_trigger(self, key):
        return str(key) == TRIGGER_KEY_NAME

    def _on_press(self, key):
        if not self._is_trigger(key):
            return
        self._handle_trigger_press()

    def _on_release(self, key):
        if not self._is_trigger(key):
            return
        self._handle_trigger_release()

    def _handle_trigger_press(self):
        trace_startup(f"_handle_trigger_press entry state={self.state} trigger_down={self.trigger_down}")
        with self._lock:
            if self.trigger_down:
                trace_startup("_handle_trigger_press ignored because trigger already down")
                return
            self.trigger_down = True
            if self.state == "continuous_recording":
                self.trigger_down = False
                trace_startup("_handle_trigger_press ending continuous recording")
                self._stop_recording(send=True)
                return
            if self.state != "idle":
                trace_startup(f"_handle_trigger_press forcing stop from state={self.state}")
                self._stop_recording(send=False)
            if self.on_interrupt:
                try:
                    self.on_interrupt("voice_press")
                except Exception:
                    pass
            self.f23_down_time = time.monotonic()
            try:
                self.recorder.start()
            except AudioUnavailable as exc:
                self.state = "idle"
                trace_startup(f"_handle_trigger_press audio unavailable: {exc}")
                self._update_surface_state("error", str(exc))
                return
            except Exception as exc:
                self.state = "idle"
                trace_startup(f"_handle_trigger_press recorder failure: {exc}")
                self._update_surface_state("error", f"mic failed: {exc}")
                return
            self.state = "recording_hold"
            trace_startup("_handle_trigger_press recorder started; state=recording_hold")
            trace_startup("TRACE1 INPUT state=listening")
            trace_startup(f"TRACE1 INPUT surface={self._surface!r} surface_type={type(self._surface).__name__}")
            try:
                self._update_surface_state("listening")
            except Exception:
                import traceback as _tb
                trace_startup("TRACE1 INPUT _update_surface_state EXCEPTION")
                trace_startup(_tb.format_exc())
                raise
            trace_startup("TRACE1 INPUT _update_surface_state returned")

    def _handle_trigger_release(self):
        trace_startup(f"_handle_trigger_release entry state={self.state} trigger_down={self.trigger_down}")
        with self._lock:
            if not self.trigger_down:
                trace_startup("_handle_trigger_release ignored because trigger not down")
                return
            self.trigger_down = False
            if self.state != "recording_hold":
                trace_startup(f"_handle_trigger_release ignored because state={self.state}")
                return
            now = time.monotonic()
            elapsed = now - self.f23_down_time if self.f23_down_time else 0.0

            if elapsed < self.hold_threshold:
                if self.last_tap_time and now - self.last_tap_time <= self.double_tap_window:
                    self.last_tap_time = None
                    self.state = "continuous_recording"
                    trace_startup("_handle_trigger_release entered continuous recording")
                    self._update_surface_state("listening")
                    return
                self.last_tap_time = now
                trace_startup(f"_handle_trigger_release tap detected elapsed={elapsed:.3f}")
                self._stop_recording(send=True)
                return

            self.last_tap_time = None
            trace_startup(f"_handle_trigger_release hold detected elapsed={elapsed:.3f}")
            self._stop_recording(send=True)

    def _stop_recording(self, send):
        trace_startup(f"_stop_recording send={send} state={self.state}")
        audio_bytes, duration = self.recorder.stop()
        self.state = "idle"
        self.f23_down_time = None
        self.trigger_down = False
        if not send or duration < self.min_audio_seconds or not audio_bytes:
            trace_startup(
                f"_stop_recording discarded send={send} duration={duration:.3f} bytes={len(audio_bytes)}"
            )
            trace_startup("TRACE1 INPUT state=idle (discarded)")
            try:
                self._update_surface_state("idle")
            except Exception:
                import traceback as _tb
                trace_startup("TRACE1 INPUT _update_surface_state EXCEPTION (idle)")
                trace_startup(_tb.format_exc())
                raise
            return
        trace_startup(f"_stop_recording dispatching duration={duration:.3f} bytes={len(audio_bytes)}")
        trace_startup("TRACE1 INPUT recorder.stop dispatching to pipeline")
        self._dispatch_audio(audio_bytes, duration)

    def _dispatch_audio(self, audio_bytes, duration):
        def run_pipeline():
            trace_startup("TRACE1 INPUT state=thinking (pipeline entry)")
            try:
                self._update_surface_state("thinking")
            except Exception:
                import traceback as _tb
                trace_startup("TRACE1 INPUT _update_surface_state EXCEPTION (thinking)")
                trace_startup(_tb.format_exc())
                raise
            if self.on_audio:
                try:
                    self.on_audio(audio_bytes, duration)
                except Exception as exc:
                    self._update_surface_state("error", f"audio pipeline failed: {exc}")
                    return
                # on_audio drives the rest of the state machine (thinking →
                # speaking → idle) internally via the bridge.  Do not set
                # idle here — that would race with the TTS on_done callback.
            else:
                self._update_surface_state("speaking")
                time.sleep(1.2)
                self._update_surface_state("idle")

        threading.Thread(target=run_pipeline, daemon=True).start()


def start(surface: RuntimeStateSink | None, config: dict, on_audio=None, on_interrupt=None):
    handler = InputHandler(surface, config, on_audio=on_audio, on_interrupt=on_interrupt)
    handler.start()
    return handler
