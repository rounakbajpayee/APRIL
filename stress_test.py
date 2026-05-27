"""
stress_test.py - Deterministic MVP stress coverage for APRIL.

This script focuses on the local, repeatable parts of the MVP:
- intent planning coverage
- config override persistence
- teachable phrase learning
- debug timeline introspection
- execution dispatch with side effects stubbed out
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import types
import unittest
from unittest import mock

import brain
import debug_log
import event_ledger
import device_control
import learning
import main
import semantic_store
import state_engine
import session_manager
import tts
from intent import config_intent, execute_plan


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
LEARNING_PATH = BASE_DIR / "learned_phrases.json"
MEMORY_PATH = BASE_DIR / "memory.json"
SEMANTIC_PATH = BASE_DIR / "state" / "semantic_records.jsonl"
LOG_PATH = BASE_DIR / "logs" / "debug.jsonl"
LEDGER_PATH = BASE_DIR / "state" / "events.jsonl"
SNAPSHOT_PATH = BASE_DIR / "state" / "context_snapshot.json"
APRIL_STATE_PATH = BASE_DIR / "state" / "april_state.json"
DESKTOP_STATE_PATH = BASE_DIR / "state" / "desktop_state.json"


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


class AprilStressTests(unittest.TestCase):
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
        self.config = json.loads((BASE_DIR / "config_defaults.json").read_text(encoding="utf-8"))

    def tearDown(self):
        learning._rules_cache = None
        semantic_store._records_cache = None
        for item in reversed(self._managed_files):
            item.__exit__(None, None, None)

    def test_routing_covers_core_components(self):
        cases = {
            "turn off voice": "config",
            "open youtube": "browser",
            "set volume to 40": "device",
            "what's on my screen": "vision",
            "play family guy": "media",
            "who am i on local": "shell",
        }
        for text, expected_intent in cases.items():
            with self.subTest(text=text):
                plan = brain.process(text, self.config)
                self.assertEqual(plan["intent"], expected_intent)
                self.assertIsInstance(plan.get("action"), dict)

    def test_conversation_question_stays_conversation(self):
        plan = brain.process("what is the population of India", self.config)
        self.assertEqual(plan["intent"], "conversation")

    def test_pause_media_routes_to_device(self):
        plan = brain.process("Pause Media", self.config)
        self.assertEqual(plan["intent"], "device")
        self.assertEqual(plan["action"].get("mode"), "media_key")

    def test_learning_round_trip_rewrites_phrases(self):
        learning.remember_phrase("movie time", "open jellyfin")
        self.assertEqual(learning.apply_rewrites("movie time"), "open jellyfin")
        self.assertEqual(learning.apply_rewrites("please do movie time now"), "please do open jellyfin now")

    def test_config_writes_overrides_only(self):
        merged = dict(self.config)
        merged["voice"] = False
        merged["terminal_visible"] = False
        config_intent._write_user_overrides(merged)
        payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload, {"voice": False, "terminal_visible": False})

    def test_recent_activity_introspection(self):
        debug_log.log_event("request_begin", source="voice", request_id=7)
        debug_log.log_event("transcript", transcript="open youtube", request_id=7)
        debug_log.log_event("intent_plan", intent="browser", request_id=7)
        debug_log.log_event("action_result", intent="browser", ok=True, reply="Opening https://www.youtube.com.")

        activity = brain.respond("what just happened", self.config)
        heard = brain.respond("what did you hear", self.config)

        self.assertIn("Heard: open youtube", activity)
        self.assertIn("Planned intent: browser.", activity)
        self.assertIn("latest transcript", heard.lower())

    def test_event_ledger_projects_snapshot_and_context(self):
        event_ledger.append_event("april_started", source="system", state="started", entity_id="april_runtime")
        event_ledger.append_event(
            "request_started",
            source="voice",
            state="started",
            entity_id="request_1",
            payload={"request_id": 1, "source": "voice"},
        )
        event_ledger.append_event(
            "desktop_observed",
            source="desktop",
            domain="desktop",
            payload={"foreground": {"window_title": "APRIL - Notes", "app_hint": "Notes", "pid": 123}},
        )
        event_ledger.append_event(
            "transcript_received",
            source="voice",
            state="completed",
            entity_id="request_1",
            payload={"request_id": 1, "transcript": "open youtube"},
        )
        event_ledger.append_event(
            "intent_planned",
            source="voice",
            state="observed",
            entity_id="request_1",
            payload={"request_id": 1, "intent": "browser", "text": "open youtube"},
        )
        event_ledger.append_event(
            "action_completed",
            source="voice",
            state="completed",
            entity_id="request_1",
            payload={"request_id": 1, "intent": "browser", "reply": "Opening https://www.youtube.com."},
        )
        event_ledger.append_event(
            "assistant_replied",
            source="voice",
            state="completed",
            entity_id="request_1",
            payload={"request_id": 1, "response": "Opening https://www.youtube.com."},
        )

        snapshot = state_engine.refresh_state_snapshot(config=self.config)
        summary = state_engine.get_prompt_context_summary(limit=5)

        self.assertTrue(SNAPSHOT_PATH.exists())
        self.assertEqual(snapshot["current_state"]["active_app"], "Notes")
        self.assertIn("open youtube", json.dumps(snapshot))
        self.assertIsNone(snapshot["current_state"]["active_request"])
        self.assertIn("APRIL runtime context:", summary)
        self.assertIn("Planned browser action.", summary)
        widget_lines = state_engine.get_widget_snapshot_lines(limit=5)
        self.assertTrue(any("State:" in text for _role, text in widget_lines))
        self.assertTrue(any("Planned browser action." in text for _role, text in widget_lines))
        widget_data = state_engine.get_widget_snapshot_data(limit=5)
        self.assertEqual(widget_data["status"], "idle")
        self.assertEqual(widget_data["focus"], "Notes")
        self.assertEqual(widget_data["last_transcript"], "open youtube")
        self.assertIn("Opening https://www.youtube.com.", widget_data["last_reply"])
        self.assertEqual(len(snapshot["domain_summaries"]["april"]["recent_replies"]), 1)

    def test_transcript_failure_surfaces_open_loop(self):
        event_ledger.append_event("april_started", source="system", state="started", entity_id="april_runtime")
        event_ledger.append_event(
            "request_started",
            source="voice",
            state="started",
            entity_id="request_3",
            payload={"request_id": 3, "source": "voice"},
        )
        event_ledger.append_event(
            "transcript_unavailable",
            source="voice",
            state="failed",
            entity_id="request_3",
            payload={"request_id": 3},
        )

        snapshot = state_engine.refresh_state_snapshot(config=self.config)
        self.assertEqual(snapshot["current_state"]["status"], "error")
        self.assertIn("Transcription was unavailable.", snapshot["open_loops"])

    def test_action_validation_projects_open_loop(self):
        event_ledger.append_event("april_started", source="system", state="started", entity_id="april_runtime")
        event_ledger.append_event(
            "request_started",
            source="voice",
            state="started",
            entity_id="request_5",
            payload={"request_id": 5, "source": "voice", "trigger_kind": "voice_command"},
        )
        event_ledger.append_event(
            "action_validated",
            source="system",
            state="observed",
            entity_id="request_5",
            payload={"request_id": 5, "verdict": "misroute_intent", "detail": "planner_selected_unexecutable_action"},
        )

        snapshot = state_engine.refresh_state_snapshot(config=self.config)
        self.assertIn("Validation flagged misroute_intent: planner_selected_unexecutable_action", snapshot["open_loops"])

    def test_execution_dispatch_survives_mixed_workload(self):
        requests = [
            "open youtube",
            "search for april project status",
            "set volume to 40",
            "play family guy",
            "what's on my screen",
            "turn off voice",
            "who am i on local",
            "what time is it",
        ]

        with (
            mock.patch("intent.browser._open_visible"),
            mock.patch("intent.device.perform", return_value="Device action ok."),
            mock.patch("intent.media_intent.handle_media", return_value="Media action ok."),
            mock.patch("intent.capture_and_query", return_value="Vision action ok."),
            mock.patch(
                "intent.shell.execute_session_command",
                return_value={"ok": True, "node": "local", "command": "whoami", "output": "rouna", "returncode": 0},
            ),
        ):
            for iteration in range(10):
                for text in requests:
                    with self.subTest(iteration=iteration, text=text):
                        plan = brain.process(text, self.config)
                        result = execute_plan(plan, self.config, context={"text": text})
                        reply = str(result.get("reply", "") or "").strip()
                        self.assertTrue(reply)

    def test_record_state_event_creates_runtime_snapshot(self):
        main.record_state_event(
            "desktop_observed",
            source="desktop",
            domain="desktop",
            payload={"foreground": {"window_title": "Chrome - YouTube", "app_hint": "YouTube", "pid": 456}},
            config=self.config,
        )
        snapshot = state_engine.load_snapshot()
        self.assertEqual(snapshot.get("desktop_state", {}).get("active_app"), "YouTube")

    def test_interrupted_request_is_cleared_from_projection(self):
        event_ledger.append_event("april_started", source="system", state="started", entity_id="april_runtime")
        event_ledger.append_event(
            "request_started",
            source="voice",
            state="started",
            entity_id="request_9",
            payload={"request_id": 9, "source": "voice"},
        )
        event_ledger.append_event(
            "request_interrupted",
            source="text",
            state="updated",
            entity_id="request_9",
            payload={"request_id": 9, "replaced_by_request_id": 10, "source": "text"},
        )

        snapshot = state_engine.refresh_state_snapshot(config=self.config)
        self.assertIsNone(snapshot["current_state"]["active_request"])
        self.assertIn("A request was interrupted by a newer request.", snapshot["open_loops"])

    def test_shell_timeout_is_projected_as_failure(self):
        with mock.patch(
            "intent.shell.execute_session_command",
            return_value={
                "ok": False,
                "node": "local",
                "command": "sleep",
                "output": "Command timed out after 20 seconds.",
                "returncode": 124,
            },
        ):
            result = execute_plan(
                {"intent": "shell", "action": {"mode": "command", "node": "local", "command": "sleep", "text": "run sleep"}},
                self.config,
                context={"text": "run sleep"},
            )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_kind"], "shell_timeout")

    def test_shell_execute_uses_session_manager_executor(self):
        with mock.patch(
            "intent.shell.execute_session_command",
            return_value={
                "ok": True,
                "node": "local",
                "command": "whoami",
                "output": "rouna",
                "returncode": 0,
            },
        ) as executor:
            result = execute_plan(
                {"intent": "shell", "action": {"mode": "natural", "node": "local", "text": "who am i on local"}},
                self.config,
                context={"text": "who am i on local"},
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["reply"], "rouna")
        executor.assert_called_once()

    def test_device_volume_prefers_endpoint_volume(self):
        volume = mock.MagicMock()
        volume.GetMasterVolumeLevelScalar.return_value = 0.5
        fake_device = types.SimpleNamespace(EndpointVolume=volume)
        fake_pycaw = types.SimpleNamespace(
            AudioUtilities=types.SimpleNamespace(GetSpeakers=lambda: fake_device),
            IAudioEndpointVolume=types.SimpleNamespace(_iid_="endpoint"),
        )
        with mock.patch.dict("sys.modules", {"pycaw": types.SimpleNamespace(pycaw=fake_pycaw), "pycaw.pycaw": fake_pycaw}):
            reply = device_control.set_volume(70)
        self.assertEqual(reply, "Volume set to 70 percent.")
        volume.SetMasterVolumeLevelScalar.assert_called_once_with(0.7, None)

    def test_open_app_uses_visible_windows_launcher(self):
        with mock.patch("device_control.subprocess.Popen") as popen:
            reply = device_control.open_app("notepad")
        self.assertEqual(reply, "Opening notepad.")
        popen.assert_called()

    def test_remote_shell_uses_configured_key_path(self):
        fake_client = mock.MagicMock()
        fake_stdout = mock.MagicMock()
        fake_stderr = mock.MagicMock()
        fake_stdout.read.return_value = b""
        fake_stderr.read.return_value = b""
        fake_stdout.channel.recv_exit_status.return_value = 0

        class FakeParamiko:
            class SSHClient:
                def __init__(self):
                    self._client = fake_client

                def set_missing_host_key_policy(self, _policy):
                    return None

                def connect(self, *args, **kwargs):
                    return fake_client.connect(*args, **kwargs)

                def exec_command(self, *args, **kwargs):
                    fake_client.exec_command(*args, **kwargs)
                    return None, fake_stdout, fake_stderr

                def close(self):
                    return None

            class AutoAddPolicy:
                pass

        with mock.patch.dict("sys.modules", {"paramiko": FakeParamiko()}):
            result = session_manager._execute_remote(
                "mac",
                "hostname",
                {"mac_ssh_host": "example.local", "mac_ssh_user": "alice", "mac_ssh_key": "~/.ssh/id_ed25519"},
                timeout=5,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(fake_client.connect.call_args.kwargs["key_filename"], os.path.expanduser("~/.ssh/id_ed25519"))

    def test_say_engine_routes_over_ssh(self):
        with mock.patch("tts.execute_session_command") as executor:
            tts._speak_say("hello from april", {"tts_say_node": "mac", "tts_timeout_seconds": 9})
        executor.assert_called_once()
        self.assertIn("say", executor.call_args.args[1])

    def test_aprilctl_launcher_quotes_the_main_script(self):
        contents = (BASE_DIR / "aprilctl.ps1").read_text(encoding="utf-8")
        self.assertIn("-PassThru", contents)
        self.assertIn('$startArgs = \'"\' + $MainScript + \'"\'', contents)
        self.assertIn('-ArgumentList $startArgs', contents)

    def test_main_records_failure_and_discard_events(self):
        with (
            mock.patch("main.collect_runtime_observation", return_value={"foreground": {"window_title": "Codex", "app_hint": "Codex"}}),
            mock.patch(
                "main.execute_plan",
                return_value={
                    "reply": "Vision request failed: API unavailable.",
                    "config_changed": False,
                    "ok": False,
                    "error_kind": "vision_failed",
                },
            ),
        ):
            request_id = main.begin_interruptible_request("text")
            reply = main.handle_user_text("what's on my screen", source="text", request_id=request_id)
            self.assertIn("Vision request failed", reply)

        events = event_ledger.read_events(limit=20)
        self.assertTrue(any(event.get("event_type") == "action_failed" for event in events))

        event_ledger.append_event(
            "request_started",
            source="text",
            state="started",
            entity_id="request_20",
            payload={"request_id": 20, "source": "text"},
        )
        event_ledger.append_event(
            "response_discarded",
            source="text",
            state="updated",
            entity_id="request_20",
            payload={"request_id": 20, "source": "text"},
        )
        snapshot = state_engine.refresh_state_snapshot(config=self.config)
        self.assertIsNone(snapshot["current_state"]["active_request"])

    def test_transcript_logs_include_stt_metadata(self):
        with (
            mock.patch("main.begin_interruptible_request", return_value=123),
            mock.patch("main.transcribe_with_metadata", return_value=("open youtube", {"stt_source": "remote", "stt_model": "whisper-1"})),
            mock.patch("main.handle_user_text", return_value="Opening https://www.youtube.com."),
        ):
            main.on_audio_captured(b"fake audio", 1.25)

        events = debug_log.read_recent_events(limit=10)
        transcript_events = [event for event in events if event.get("event") == "transcript"]
        self.assertTrue(transcript_events)
        event = transcript_events[-1]
        self.assertEqual(event.get("stt_source"), "remote")
        self.assertEqual(event.get("stt_model"), "whisper-1")

    def test_semantic_store_can_recall_confirmed_phrases(self):
        semantic_store.record_semantic_example(
            kind="turn",
            text="open project docs folder",
            source="text",
            resolved_intent="shell",
            response="Opening the project docs folder.",
            action={"mode": "natural", "node": "local", "text": "open project docs folder"},
            outcome="success",
            subject_type="utterance",
            subject_ref="1",
            confidence=1.0,
        )
        plan = semantic_store.semantic_plan("open the project documents directory")
        self.assertEqual(plan["intent"], "shell")
        self.assertEqual(plan["action"].get("mode"), "natural")

    def test_semantic_store_does_not_replay_failed_examples(self):
        semantic_store.record_semantic_example(
            kind="turn",
            text="open local document folder",
            source="voice",
            resolved_intent="device",
            response="I understood that as a device request, but I couldn't map the action yet.",
            action={"open_app": "local document folder", "text": "open local document folder"},
            outcome="failure",
            subject_type="utterance",
            subject_ref="2",
            confidence=0.6,
            validation_label="misroute_intent",
        )
        plan = semantic_store.semantic_plan("open local document folder", confidence_threshold=0.1)
        self.assertIsNone(plan)

    def test_semantic_router_uses_examples_for_paraphrases(self):
        plan = brain.process("pull up youtube", self.config)
        self.assertEqual(plan["intent"], "browser")
        self.assertEqual(plan["action"].get("mode"), "open_url")
        self.assertIn("youtube", str(plan["action"].get("url", "")).lower())

    def test_dynamic_semantic_routing_via_brain(self):
        semantic_store.record_semantic_example(
            kind="turn",
            text="start local database backup",
            source="text",
            resolved_intent="shell",
            response="Starting dynamic DB backup.",
            action={"mode": "command", "node": "local", "command": "backup_db.bat"},
            outcome="success",
            subject_type="utterance",
            subject_ref="42",
            confidence=1.0,
        )
        self.config["semantic_routing_threshold"] = 0.50
        plan = brain.process("please start the local database backup script", self.config)
        self.assertEqual(plan["intent"], "shell")
        self.assertEqual(plan["action"].get("mode"), "command")
        self.assertEqual(plan["action"].get("command"), "backup_db.bat")
        self.assertEqual(plan["_routing"]["planner_source"], "semantic_store_replay")

    def test_dictation_mode_types_text(self):
        from main import _post_process_dictation
        raw = "Hello dictation mode period Um, this is a test new line and we we are recording"
        cleaned = _post_process_dictation(raw)
        self.assertEqual(cleaned, "Hello dictation mode. This is a test\nand we are recording")

        mock_controller = mock.MagicMock()
        fake_keyboard = types.SimpleNamespace(Controller=mock.MagicMock(return_value=mock_controller))
        fake_pynput = types.SimpleNamespace(keyboard=fake_keyboard)
        with (
            mock.patch("main.transcribe_with_metadata", return_value=(raw, {"stt_source": "remote"})),
            mock.patch.dict("sys.modules", {"pynput": fake_pynput, "pynput.keyboard": fake_keyboard}),
        ):
            res = main.on_audio_captured(b"fake audio", 1.5, trigger_kind="voice_dictation")
            self.assertEqual(res, "Hello dictation mode. This is a test\nand we are recording")
            mock_controller.type.assert_called_once_with("Hello dictation mode. This is a test\nand we are recording")

    def test_handle_user_text_records_provenance_and_validation(self):
        with (
            mock.patch("main.collect_runtime_observation", return_value={"foreground": {"window_title": "Codex", "app_hint": "Codex"}}),
            mock.patch(
                "main.plan_with_brain",
                return_value={
                    "intent": "device",
                    "action": {"mode": "open_app", "app": "notepad", "text": "open notepad"},
                    "_routing": {"planner_source": "llm_intent_plan", "planner_reason": "ollama_json_plan"},
                },
            ),
            mock.patch(
                "main.execute_plan",
                return_value={"reply": "Opening notepad.", "config_changed": False, "ok": True, "error_kind": ""},
            ),
            mock.patch("main.speak_reply"),
        ):
            request_id = main.begin_interruptible_request("voice", trigger_kind="voice_command")
            reply = main.handle_user_text(
                "open notepad",
                source="voice",
                request_id=request_id,
                request_id_str="REQ-0099",
                trigger_kind="voice_command",
            )
            self.assertEqual(reply, "Opening notepad.")

        events = event_ledger.read_events(limit=20)
        planned = [event for event in events if event.get("event_type") == "intent_planned"]
        validated = [event for event in events if event.get("event_type") == "action_validated"]
        self.assertTrue(planned)
        self.assertEqual(planned[-1]["payload"]["routing"]["planner_source"], "llm_intent_plan")
        self.assertTrue(validated)
        self.assertEqual(validated[-1]["payload"]["verdict"], "auto_pass")

    def test_input_handler_concurrency_and_key_repeat(self):
        from input_handler import InputHandler
        import threading
        import time

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



    def test_post_process_dictation_with_phonetics(self):
        from main import _post_process_dictation
        
        # Test single word "newline" mapping
        raw1 = "This is a test newline and another one"
        self.assertEqual(_post_process_dictation(raw1), "This is a test\nand another one")

        # Test phonetic variants "sewline" and "shoeline"
        raw2 = "This is a test sewline say hi"
        self.assertEqual(_post_process_dictation(raw2), "This is a test\nsay hi")

        raw3 = "This is a test shoeline and we are done"
        self.assertEqual(_post_process_dictation(raw3), "This is a test\nand we are done")

    def test_pipeline_error_recovery_and_stuck_state(self):
        mock_bridge = mock.MagicMock()
        with (
            mock.patch("main._bridge_ref", mock_bridge),
            mock.patch("main.plan_with_brain", side_effect=ConnectionError("Ollama offline")),
            mock.patch("runtime_trace.trace_event") as mock_trace,
        ):
            with self.assertRaises(ConnectionError):
                main.handle_user_text("test exception recovery", source="text", request_id=45, request_id_str="REQ-0045")
            
            # Verify bridge was set to thinking first
            mock_bridge.set_state.assert_any_call("thinking", request_id="REQ-0045")
            # Verify bridge was reset to idle in the finally block
            mock_bridge.set_state.assert_any_call("idle", request_id="REQ-0045")
            
            # Verify trace_event logged the pipeline error
            mock_trace.assert_any_call(
                "pipeline_error",
                subsystem="brain",
                severity="ERROR",
                request_id="REQ-0045",
                payload={"error": "Ollama offline", "source": "text", "text": "test exception recovery"},
            )

    def test_sft_export_format(self):
        import export_sft
        # Write sample semantic records to the temporary test path
        # Note: SEMANTIC_PATH in setup is mapping to a clean test file.
        records = [
            {
                "id": "sem_1",
                "ts": "2026-05-27T12:00:00Z",
                "kind": "turn",
                "source": "text",
                "text": "turn on voice",
                "response": "Turning voice on.",
                "action": {"updates": {"voice": True}},
                "outcome": "success",
                "confidence": 1.0,
                "session_id": "session_abc",
                "system_prompt_hash": "hash_123",
                "enriched_context": "State:\nactive\n\nMemory:\nnone",
            },
            {
                "id": "sem_2",
                "ts": "2026-05-27T12:01:00Z",
                "kind": "turn",
                "source": "text",
                "text": "open youtube",
                "response": "Opening YouTube.",
                "action": {"mode": "open_url", "url": "https://www.youtube.com"},
                "outcome": "success",
                "confidence": 1.0,
                "session_id": "session_abc",
                "system_prompt_hash": "hash_123",
                "enriched_context": "State:\nactive",
            }
        ]
        
        with open(SEMANTIC_PATH, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
                
        # Run export_sft with custom args
        output_file = BASE_DIR / "state" / "sft_export_test.jsonl"
        if output_file.exists():
            output_file.unlink()
            
        try:
            # We mock sys.argv to run the main() function in export_sft
            with mock.patch("sys.argv", ["export_sft.py", "--output", str(output_file), "--format", "chat"]):
                export_sft.main()
                
            self.assertTrue(output_file.exists())
            lines = output_file.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)  # Grouped into 1 multi-turn session
            
            exported = json.loads(lines[0])
            self.assertIn("messages", exported)
            messages = exported["messages"]
            self.assertEqual(messages[0]["role"], "system")
            self.assertEqual(messages[1]["role"], "user")
            self.assertEqual(messages[1]["content"], "turn on voice")
            self.assertEqual(messages[2]["role"], "assistant")
            self.assertEqual(messages[2]["content"], "Turning voice on.")
            self.assertEqual(messages[3]["role"], "user")
            self.assertEqual(messages[3]["content"], "open youtube")
            self.assertEqual(messages[4]["role"], "assistant")
            self.assertEqual(messages[4]["content"], "Opening YouTube.")
        finally:
            if output_file.exists():
                output_file.unlink()


if __name__ == "__main__":
    unittest.main(verbosity=2)
