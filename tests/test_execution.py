import json
import os
from pathlib import Path
import types
import unittest
from unittest import mock

import brain
import device_control
import learning
import session_manager
import tts
from intent import config_intent, execute_plan

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


class TestExecution(unittest.TestCase):
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
        self.config = json.loads(
            (SRC_DIR / "config_defaults.json").read_text(encoding="utf-8")
        )

    def tearDown(self):
        learning._rules_cache = None
        for item in reversed(self._managed_files):
            item.__exit__(None, None, None)

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
            mock.patch(
                "intent.media_intent.handle_media", return_value="Media action ok."
            ),
            mock.patch("intent.capture_and_query", return_value="Vision action ok."),
            mock.patch(
                "intent.shell.execute_session_command",
                return_value={
                    "ok": True,
                    "node": "local",
                    "command": "whoami",
                    "output": "rouna",
                    "returncode": 0,
                },
            ),
        ):
            for iteration in range(10):
                for text in requests:
                    with self.subTest(iteration=iteration, text=text):
                        plan = brain.process(text, self.config)
                        result = execute_plan(plan, self.config, context={"text": text})
                        reply = str(result.get("reply", "") or "").strip()
                        self.assertTrue(reply)

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
                {
                    "intent": "shell",
                    "action": {
                        "mode": "command",
                        "node": "local",
                        "command": "sleep",
                        "text": "run sleep",
                    },
                },
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
                {
                    "intent": "shell",
                    "action": {
                        "mode": "natural",
                        "node": "local",
                        "text": "who am i on local",
                    },
                },
                self.config,
                context={"text": "who am i on local"},
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["reply"], "rouna")
        executor.assert_called_once()

    def test_device_volume_prefers_endpoint_volume(self):
        volume = mock.MagicMock()
        volume.GetMasterVolumeVolumeScalar = mock.MagicMock()  # pycaw mock handles it
        volume.GetMasterVolumeLevelScalar.return_value = 0.5
        fake_device = types.SimpleNamespace(EndpointVolume=volume)
        fake_pycaw = types.SimpleNamespace(
            AudioUtilities=types.SimpleNamespace(GetSpeakers=lambda: fake_device),
            IAudioEndpointVolume=types.SimpleNamespace(_iid_="endpoint"),
        )
        with mock.patch.dict(
            "sys.modules",
            {
                "pycaw": types.SimpleNamespace(pycaw=fake_pycaw),
                "pycaw.pycaw": fake_pycaw,
            },
        ):
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
                {
                    "mac_ssh_host": "example.local",
                    "mac_ssh_user": "alice",
                    "mac_ssh_key": "~/.ssh/id_ed25519",
                },
                timeout=5,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(
            fake_client.connect.call_args.kwargs["key_filename"],
            os.path.expanduser("~/.ssh/id_ed25519"),
        )

    def test_say_engine_routes_over_ssh(self):
        with mock.patch("tts.execute_session_command") as executor:
            tts._speak_say(
                "hello from april", {"tts_say_node": "mac", "tts_timeout_seconds": 9}
            )
        executor.assert_called_once()
        self.assertIn("say", executor.call_args.args[1])

    def test_aprilctl_launcher_quotes_the_main_script(self):
        # aprilctl is now in the scripts/ folder at repo root
        launcher_path = (
            Path(__file__).resolve().parent.parent / "scripts" / "aprilctl.ps1"
        )
        contents = launcher_path.read_text(encoding="utf-8")
        self.assertIn("-PassThru", contents)
        self.assertIn("$startArgs = '\"' + $MainScript + '\"'", contents)
        self.assertIn("-ArgumentList $startArgs", contents)

    def test_config_writes_overrides_only(self):
        merged = dict(self.config)
        merged["voice"] = False
        merged["terminal_visible"] = False
        config_intent._write_user_overrides(merged)
        payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload, {"voice": False, "terminal_visible": False})
