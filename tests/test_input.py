import json
import types
import unittest
from pathlib import Path
from unittest import mock

import learning
import main
import semantic_store

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
CONFIG_PATH = SRC_DIR / "config.json"
LEARNING_PATH = SRC_DIR / "learned_phrases.json"
MEMORY_PATH = SRC_DIR / "memory.json"
SEMANTIC_PATH = SRC_DIR / "state" / "semantic_records.jsonl"
LOG_PATH = SRC_DIR / "logs" / "debug.jsonl"
LEDGER_PATH = SRC_DIR / "state" / "events.jsonl"
SNAPSHOT_PATH = SRC_DIR / "state" / "context_snapshot.json"
APRIL_STATE_PATH = SRC_DIR / "state" / "april_state.json"
DESKTOP_STATE_PATH = SRC_DIR / "state" / "desktop_state.json"


class ManagedFile:
    def __init__(self, path: Path):
        self.path = path
        self.original_exists = False
        self.original_text = ""

    def __enter__(self):
        self.original_exists = self.path.exists()
        if self.original_exists:
            self.original_text = self.path.read_text(encoding="utf-8")
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.original_exists:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(self.original_text, encoding="utf-8")
        elif self.path.exists():
            self.path.unlink()


class TestInputHandlerAndDictation(unittest.TestCase):
    def setUp(self):
        self._managed_files = [
            ManagedFile(CONFIG_PATH),
            ManagedFile(LEARNING_PATH),
            ManagedFile(MEMORY_PATH),
            ManagedFile(SEMANTIC_PATH),
            ManagedFile(LOG_PATH),
            ManagedFile(LEDGER_PATH),
            ManagedFile(SNAPSHOT_PATH),
            ManagedFile(APRIL_STATE_PATH),
            ManagedFile(DESKTOP_STATE_PATH),
        ]
        for item in self._managed_files:
            item.__enter__()

        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        for path, empty_text in (
            (CONFIG_PATH, "{}\n"),
            (LEARNING_PATH, "[]\n"),
            (MEMORY_PATH, '{"turns": []}\n'),
            (SEMANTIC_PATH, ""),
            (LOG_PATH, ""),
            (LEDGER_PATH, ""),
        ):
            path.write_text(empty_text, encoding="utf-8")

        learning._rules_cache = None
        semantic_store._records_cache = None
        self.config = json.loads(
            (SRC_DIR / "config_defaults.json").read_text(encoding="utf-8")
        )

    def tearDown(self):
        learning._rules_cache = None
        semantic_store._records_cache = None
        for item in reversed(self._managed_files):
            item.__exit__(None, None, None)

    def test_dictation_mode_types_text(self):
        from main import _post_process_dictation

        raw = "Hello dictation mode period Um, this is a test new line and we we are recording"
        cleaned = _post_process_dictation(raw)
        self.assertEqual(
            cleaned, "Hello dictation mode. This is a test\nand we are recording"
        )

        mock_controller = mock.MagicMock()
        mock_pyperclip = mock.MagicMock()
        mock_pyperclip.paste.return_value = "original user clipboard"

        fake_keyboard = types.SimpleNamespace(
            Controller=mock.MagicMock(return_value=mock_controller),
            Key=mock.MagicMock(),
        )
        fake_pynput = types.SimpleNamespace(keyboard=fake_keyboard)
        with (
            mock.patch(
                "main.transcribe_with_metadata",
                return_value=(raw, {"stt_source": "remote"}),
            ),
            mock.patch.dict(
                "sys.modules",
                {
                    "pynput": fake_pynput,
                    "pynput.keyboard": fake_keyboard,
                    "pyperclip": mock_pyperclip,
                },
            ),
        ):
            res = main.on_audio_captured(
                b"fake audio", 1.5, trigger_kind="voice_dictation"
            )
            self.assertEqual(
                res, "Hello dictation mode. This is a test\nand we are recording"
            )

            # Verify pyperclip copies were made for each split line
            copied_texts = [call.args[0] for call in mock_pyperclip.copy.call_args_list]
            self.assertIn("Hello dictation mode. This is a test", copied_texts)
            self.assertIn("and we are recording", copied_texts)

            # Verify clipboard is restored back to its original state at the end
            self.assertEqual(
                mock_pyperclip.copy.call_args_list[-1].args[0],
                "original user clipboard",
            )

    def test_post_process_dictation_with_phonetics(self):
        from main import _post_process_dictation

        # Test single word "newline" mapping
        raw1 = "This is a test newline and another one"
        self.assertEqual(
            _post_process_dictation(raw1), "This is a test\nand another one"
        )

        # Test phonetic variants "sewline" and "shoeline"
        raw2 = "This is a test sewline say hi"
        self.assertEqual(_post_process_dictation(raw2), "This is a test\nsay hi")

        raw3 = "This is a test shoeline and we are done"
        self.assertEqual(
            _post_process_dictation(raw3), "This is a test\nand we are done"
        )

    def test_input_handler_concurrency_and_key_repeat(self):
        import threading
        import time

        from input_handler import InputHandler

        mock_surface = mock.MagicMock()
        handler = InputHandler(
            surface=mock_surface,
            config={
                "copilot_hold_threshold": 0.1,
                "copilot_double_tap_window": 0.2,
                "copilot_min_audio_seconds": 0.05,
            },
        )
        handler.recorder = mock.MagicMock()
        handler.recorder.stop.return_value = (b"fake wav data", 0.5)

        # 1. First trigger press (simulates F23 keydown)
        handler._handle_trigger_press()
        self.assertTrue(handler.trigger_down)
        self.assertEqual(handler.state, "recording_hold")
        handler.recorder.start.assert_called_once()

        # 2. Key repeat triggers (should be ignored because trigger_down is True)
        handler.recorder.start.reset_mock()
        handler._handle_trigger_press()
        handler._handle_trigger_press()
        self.assertTrue(handler.trigger_down)
        self.assertEqual(handler.state, "recording_hold")
        handler.recorder.start.assert_not_called()

        # 3. Trigger release (simulates F23 keyup) after delay (hold)
        time.sleep(0.15)
        handler._handle_trigger_release()
        self.assertFalse(handler.trigger_down)
        self.assertEqual(handler.state, "idle")
        handler.recorder.stop.assert_called_once()

        # 4. Double tap test
        handler.recorder.start.reset_mock()
        handler.recorder.stop.reset_mock()
        handler.recorder.stop.return_value = (b"fake wav data", 0.05)

        # Tap 1 press
        handler._handle_trigger_press()
        self.assertEqual(handler.state, "recording_hold")
        # Tap 1 release
        handler._handle_trigger_release()
        self.assertEqual(handler.state, "idle")

        # Tap 2 press
        handler._handle_trigger_press()
        self.assertEqual(handler.state, "recording_hold")
        # Tap 2 release (within double tap window)
        handler._handle_trigger_release()
        self.assertEqual(handler.state, "continuous_recording")

        # Pressing again should end continuous recording
        handler.recorder.stop.reset_mock()
        handler._handle_trigger_press()
        self.assertEqual(handler.state, "idle")
        handler.recorder.stop.assert_called_once()

        # 5. Concurrent press/release flooding (should not deadlock)
        handler.recorder.start.reset_mock()
        handler.recorder.stop.reset_mock()
        handler.recorder.stop.return_value = (b"fake wav", 0.5)

        threads = []
        for _ in range(10):
            t_press = threading.Thread(target=handler._handle_trigger_press)
            t_release = threading.Thread(target=handler._handle_trigger_release)
            threads.extend([t_press, t_release])

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertIn(handler.state, ["idle", "recording_hold", "continuous_recording"])

    def test_native_hook_latches_altdown_from_event_flags(self):
        import ctypes

        import input_handler as ih

        handler = ih.InputHandler(
            surface=None,
            config={
                "copilot_hold_threshold": 0.1,
                "copilot_double_tap_window": 0.2,
                "copilot_min_audio_seconds": 0.05,
            },
        )
        handler.recorder = mock.MagicMock()

        original_async = ih.user32.GetAsyncKeyState
        original_thread = ih.threading.Thread

        class ImmediateThread:
            def __init__(self, target=None, daemon=None):
                self._target = target

            def start(self):
                if self._target:
                    self._target()

            def join(self, timeout=None):
                return None

        try:
            ih.user32.GetAsyncKeyState = lambda vk: 0
            ih.threading.Thread = ImmediateThread

            hook = ih.NativeCopilotHook(handler)
            event = ih.KBDLLHOOKSTRUCT()
            event.vkCode = ih.VK_F23
            event.flags = ih.LLKHF_ALTDOWN

            hook._hook_proc(ih.HC_ACTION, ih.WM_KEYDOWN, ctypes.addressof(event))

            self.assertEqual(handler._current_trigger_kind, "voice_dictation")
            handler.recorder.start.assert_called_once()
        finally:
            ih.user32.GetAsyncKeyState = original_async
            ih.threading.Thread = original_thread
