import json
import unittest
from pathlib import Path

import brain
import learning
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


class TestRoutingAndLearning(unittest.TestCase):
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
        self.assertEqual(
            learning.apply_rewrites("please do movie time now"),
            "please do open jellyfin now",
        )

    def test_semantic_store_can_recall_confirmed_phrases(self):
        semantic_store.record_semantic_example(
            kind="turn",
            text="open project docs folder",
            source="text",
            resolved_intent="shell",
            response="Opening the project docs folder.",
            action={
                "mode": "natural",
                "node": "local",
                "text": "open project docs folder",
            },
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
            action={
                "open_app": "local document folder",
                "text": "open local document folder",
            },
            outcome="failure",
            subject_type="utterance",
            subject_ref="2",
            confidence=0.6,
            validation_label="misroute_intent",
        )
        plan = semantic_store.semantic_plan(
            "open local document folder", confidence_threshold=0.1
        )
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
        plan = brain.process(
            "please start the local database backup script", self.config
        )
        self.assertEqual(plan["intent"], "shell")
        self.assertEqual(plan["action"].get("mode"), "command")
        self.assertEqual(plan["action"].get("command"), "backup_db.bat")
        self.assertEqual(plan["_routing"]["planner_source"], "semantic_store_replay")
