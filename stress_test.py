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
from pathlib import Path
import unittest
from unittest import mock

import brain
import debug_log
import event_ledger
import learning
import main
import state_engine
from intent import config_intent, execute_plan


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
LEARNING_PATH = BASE_DIR / "learned_phrases.json"
MEMORY_PATH = BASE_DIR / "memory.json"
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
            (LOG_PATH, ""),
            (LEDGER_PATH, ""),
        ):
            path.write_text(empty_text, encoding="utf-8")

        learning._rules_cache = None
        self.config = json.loads((BASE_DIR / "config_defaults.json").read_text(encoding="utf-8"))

    def tearDown(self):
        learning._rules_cache = None
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
                "intent.shell.execute",
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
            "intent.shell.execute",
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
