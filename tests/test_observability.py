import json
import unittest
from pathlib import Path
from unittest import mock

import brain
import debug_log
import event_ledger
import learning
import main
import semantic_store
import state_engine

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


class TestObservability(unittest.TestCase):
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

    def test_recent_activity_introspection(self):
        debug_log.log_event("request_begin", source="voice", request_id=7)
        debug_log.log_event("transcript", transcript="open youtube", request_id=7)
        debug_log.log_event("intent_plan", intent="browser", request_id=7)
        debug_log.log_event(
            "action_result",
            intent="browser",
            ok=True,
            reply="Opening https://www.youtube.com.",
        )

        activity = brain.respond("what just happened", self.config)
        heard = brain.respond("what did you hear", self.config)

        self.assertIn("Heard: open youtube", activity)
        self.assertIn("Planned intent: browser.", activity)
        self.assertIn("latest transcript", heard.lower())

    def test_event_ledger_projects_snapshot_and_context(self):
        event_ledger.append_event(
            "april_started", source="system", state="started", entity_id="april_runtime"
        )
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
            payload={
                "foreground": {
                    "window_title": "APRIL - Notes",
                    "app_hint": "Notes",
                    "pid": 123,
                }
            },
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
            payload={
                "request_id": 1,
                "intent": "browser",
                "reply": "Opening https://www.youtube.com.",
            },
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
        self.assertTrue(
            any("Planned browser action." in text for _role, text in widget_lines)
        )
        widget_data = state_engine.get_widget_snapshot_data(limit=5)
        self.assertEqual(widget_data["status"], "idle")
        self.assertEqual(widget_data["focus"], "Notes")
        self.assertEqual(widget_data["last_transcript"], "open youtube")
        self.assertIn("Opening https://www.youtube.com.", widget_data["last_reply"])
        self.assertEqual(
            len(snapshot["domain_summaries"]["april"]["recent_replies"]), 1
        )

    def test_transcript_failure_surfaces_open_loop(self):
        event_ledger.append_event(
            "april_started", source="system", state="started", entity_id="april_runtime"
        )
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
        event_ledger.append_event(
            "april_started", source="system", state="started", entity_id="april_runtime"
        )
        event_ledger.append_event(
            "request_started",
            source="voice",
            state="started",
            entity_id="request_5",
            payload={
                "request_id": 5,
                "source": "voice",
                "trigger_kind": "voice_command",
            },
        )
        event_ledger.append_event(
            "action_validated",
            source="system",
            state="observed",
            entity_id="request_5",
            payload={
                "request_id": 5,
                "verdict": "misroute_intent",
                "detail": "planner_selected_unexecutable_action",
            },
        )

        snapshot = state_engine.refresh_state_snapshot(config=self.config)
        self.assertIn(
            "Validation flagged misroute_intent: planner_selected_unexecutable_action",
            snapshot["open_loops"],
        )

    def test_record_state_event_creates_runtime_snapshot(self):
        main.record_state_event(
            "desktop_observed",
            source="desktop",
            domain="desktop",
            payload={
                "foreground": {
                    "window_title": "Chrome - YouTube",
                    "app_hint": "YouTube",
                    "pid": 456,
                }
            },
            config=self.config,
        )
        snapshot = state_engine.load_snapshot()
        self.assertEqual(snapshot.get("desktop_state", {}).get("active_app"), "YouTube")

    def test_interrupted_request_is_cleared_from_projection(self):
        event_ledger.append_event(
            "april_started", source="system", state="started", entity_id="april_runtime"
        )
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
        self.assertIn(
            "A request was interrupted by a newer request.", snapshot["open_loops"]
        )

    def test_main_records_failure_and_discard_events(self):
        with (
            mock.patch(
                "main.collect_runtime_observation",
                return_value={
                    "foreground": {"window_title": "Codex", "app_hint": "Codex"}
                },
            ),
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
            reply = main.handle_user_text(
                "what's on my screen", source="text", request_id=request_id
            )
            self.assertIn("Vision request failed", reply)

        events = event_ledger.read_events(limit=20)
        self.assertTrue(
            any(event.get("event_type") == "action_failed" for event in events)
        )

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
            mock.patch(
                "main.transcribe_with_metadata",
                return_value=(
                    "open youtube",
                    {"stt_source": "remote", "stt_model": "whisper-1"},
                ),
            ),
            mock.patch(
                "main.handle_user_text", return_value="Opening https://www.youtube.com."
            ),
        ):
            main.on_audio_captured(b"fake audio", 1.25)

        events = debug_log.read_recent_events(limit=10)
        transcript_events = [
            event for event in events if event.get("event") == "transcript"
        ]
        self.assertTrue(transcript_events)
        event = transcript_events[-1]
        self.assertEqual(event.get("stt_source"), "remote")
        self.assertEqual(event.get("stt_model"), "whisper-1")

    def test_pipeline_error_recovery_and_stuck_state(self):
        mock_bridge = mock.MagicMock()
        with (
            mock.patch("main._bridge_ref", mock_bridge),
            mock.patch(
                "main.plan_with_brain", side_effect=ConnectionError("Ollama offline")
            ),
            mock.patch("runtime_trace.trace_event") as mock_trace,
        ):
            with self.assertRaises(ConnectionError):
                main.handle_user_text(
                    "test exception recovery",
                    source="text",
                    request_id=45,
                    request_id_str="REQ-0045",
                )

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
                payload={
                    "error": "Ollama offline",
                    "source": "text",
                    "text": "test exception recovery",
                },
            )

    def test_sft_export_format(self):
        import export_sft

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
            },
        ]

        with open(SEMANTIC_PATH, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

        output_file = SRC_DIR / "state" / "sft_export_test.jsonl"
        if output_file.exists():
            output_file.unlink()

        try:
            with mock.patch(
                "sys.argv",
                ["export_sft.py", "--output", str(output_file), "--format", "chat"],
            ):
                export_sft.main()

            self.assertTrue(output_file.exists())
            lines = output_file.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)

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

    def test_handle_user_text_records_provenance_and_validation(self):
        with (
            mock.patch(
                "main.collect_runtime_observation",
                return_value={
                    "foreground": {"window_title": "Codex", "app_hint": "Codex"}
                },
            ),
            mock.patch(
                "main.plan_with_brain",
                return_value={
                    "intent": "device",
                    "action": {
                        "mode": "open_app",
                        "app": "notepad",
                        "text": "open notepad",
                    },
                    "_routing": {
                        "planner_source": "llm_intent_plan",
                        "planner_reason": "ollama_json_plan",
                    },
                },
            ),
            mock.patch(
                "main.execute_plan",
                return_value={
                    "reply": "Opening notepad.",
                    "config_changed": False,
                    "ok": True,
                    "error_kind": "",
                },
            ),
            mock.patch("main.speak_reply"),
        ):
            request_id = main.begin_interruptible_request(
                "voice", trigger_kind="voice_command"
            )
            reply = main.handle_user_text(
                "open notepad",
                source="voice",
                request_id=request_id,
                request_id_str="REQ-0099",
                trigger_kind="voice_command",
            )
            self.assertEqual(reply, "Opening notepad.")

        events = event_ledger.read_events(limit=20)
        planned = [
            event for event in events if event.get("event_type") == "intent_planned"
        ]
        validated = [
            event for event in events if event.get("event_type") == "action_validated"
        ]
        self.assertTrue(planned)
        self.assertEqual(
            planned[-1]["payload"]["routing"]["planner_source"], "llm_intent_plan"
        )
        self.assertTrue(validated)
        self.assertEqual(validated[-1]["payload"]["verdict"], "auto_pass")

    def test_opentelemetry_span_export(self):
        """Verify that OpenTelemetry instrumentation emits spans correctly."""
        from opentelemetry import trace
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )

        import runtime_trace

        # Get the active TracerProvider and add our InMemorySpanExporter to it
        provider = trace.get_tracer_provider()
        memory_exporter = InMemorySpanExporter()
        processor = SimpleSpanProcessor(memory_exporter)
        provider.add_span_processor(processor)

        # Temporarily swap runtime_trace tracer
        original_tracer = runtime_trace._tracer
        runtime_trace._tracer = trace.get_tracer("april.runtime_trace.test")

        try:
            runtime_trace.trace_event(
                "test_otel_event",
                subsystem="test_system",
                severity="ERROR",
                request_id="REQ-OTEL",
                payload={"key": "value"},
            )

            # Flush spans
            runtime_trace.flush(0.1)

            spans = memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)
            span = spans[0]
            self.assertEqual(span.name, "test_otel_event")

            events = span.events
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].name, "test_otel_event")

            attrs = events[0].attributes
            self.assertEqual(attrs.get("subsystem"), "test_system")
            self.assertEqual(attrs.get("severity"), "ERROR")
            self.assertEqual(attrs.get("request_id"), "REQ-OTEL")
            self.assertIn("key", attrs.get("payload", ""))
            self.assertIn("value", attrs.get("payload", ""))
        finally:
            # Clean up the processor to prevent leakage to other tests
            try:
                with provider._active_span_processor._lock:
                    processors = provider._active_span_processor._span_processors
                    provider._active_span_processor._span_processors = tuple(
                        p for p in processors if p is not processor
                    )
            except Exception:
                pass
            # Restore
            runtime_trace._tracer = original_tracer
