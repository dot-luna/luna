"""Exercise the recording worker with fake capture tools and an isolated runtime directory."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location("luna_record", REPO / "src/luna-cli/record/record.py")
record = importlib.util.module_from_spec(spec)
spec.loader.exec_module(record)


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna recording '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        tools = self.root / "bin"
        tools.mkdir()
        commands = {
            "qs": "#!/bin/sh\nexit 0\n",
            "notify-send": "#!/usr/bin/env python3\nimport json, os, sys, time\nwith open(os.environ['LUNA_TEST_NOTICES'], 'a') as file: file.write(json.dumps(sys.argv[1:]) + '\\n')\ntime.sleep(float(os.environ.get('LUNA_TEST_NOTICE_DELAY', '0')))\n",
            "wf-recorder": '''#!/usr/bin/env python3
import json, os, signal, sys, time
from pathlib import Path
Path(os.environ['LUNA_TEST_ARGUMENTS']).write_text(json.dumps(sys.argv[1:]))
if os.environ.get('LUNA_TEST_FAIL'):
    print('Capture device unavailable', file=sys.stderr)
    sys.exit(3)
path = Path(sys.argv[sys.argv.index('-f') + 1])
path.write_bytes(b'\\x00\\x00\\x00\\x20ftyp' + b'video-data' * 8)
stopped = False
def stop(signum, frame):
    global stopped
    stopped = True
signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGTERM, stop)
while not stopped:
    time.sleep(.02)
with path.open('ab') as file:
    file.write(b'finalized')
''',
        }
        for name, script in commands.items():
            path = tools / name
            path.write_text(script)
            path.chmod(0o755)
        self.env = patch.dict(os.environ, {
            "PATH": str(tools) + ":" + os.environ["PATH"],
            "XDG_RUNTIME_DIR": str(self.root / "runtime"),
            "LUNA_RECORDING_DIR": str(self.root / "videos with spaces"),
            "LUNA_TEST_ARGUMENTS": str(self.root / "arguments.json"),
            "LUNA_TEST_NOTICES": str(self.root / "notices.jsonl"),
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.patches = [patch.object(record, "ensure_indicator"), patch.object(record.capture, "hide_launcher"),
                        patch.object(record.capture, "capture_arguments", return_value=["-o", "TEST-1"])]
        for mock in self.patches:
            mock.start()
            self.addCleanup(mock.stop)
        self.addCleanup(self.stop_worker)

    def stop_worker(self):
        if record.status()["running"]:
            record.stop()

    def test_start_and_stop_finalize_one_private_file(self):
        path = record.start("screen")
        state = record.status()
        self.assertTrue(state["running"])
        self.assertEqual(state["phase"], "recording")
        self.assertEqual(Path(state["file"]), path)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        arguments = json.loads((self.root / "arguments.json").read_text())
        self.assertIn("TEST-1", arguments)
        self.assertNotIn("--audio", arguments)
        self.assertEqual(record.stop(), path)
        self.assertFalse(record.status()["running"])
        self.assertTrue(path.read_bytes().endswith(b"finalized"))

    def test_duplicate_start_preserves_original_recording(self):
        path = record.start("screen")
        before = record.status()
        with self.assertRaisesRegex(ValueError, "already running"):
            record.start("screen")
        self.assertEqual(record.status()["pid"], before["pid"])
        self.assertEqual(list(path.parent.iterdir()), [path])

    def test_cancelled_selection_creates_no_video_or_worker(self):
        with patch.object(record.capture, "capture_arguments", return_value=None):
            self.assertIsNone(record.start("region"))
        self.assertFalse(record.status()["running"])
        self.assertFalse((self.root / "videos with spaces").exists())

    def test_start_failure_reports_error_and_removes_empty_file(self):
        with patch.dict(os.environ, {"LUNA_TEST_FAIL": "1"}):
            with self.assertRaisesRegex(ValueError, "Capture device unavailable"):
                record.start("screen")
        self.assertFalse(record.status()["running"])
        self.assertEqual(list((self.root / "videos with spaces").iterdir()), [])

    def test_stale_pid_cannot_stop_an_unrelated_process(self):
        record.write_state({"running": True, "pid": os.getpid(), "identity": "stale", "file": "/tmp/not-ours.mp4"})
        with patch.object(os, "pidfd_open") as opener:
            self.assertIsNone(record.stop())
            opener.assert_not_called()
        self.assertFalse(record.status()["running"])

    def test_missing_identity_and_malformed_state_are_not_running(self):
        record.write_state({"running": True, "pid": 2147483647, "identity": None})
        self.assertFalse(record.status()["running"])
        (record.runtime() / "state.json").write_text("[]")
        self.assertFalse(record.status()["running"])

    def test_sequential_recordings_have_distinct_names(self):
        first = record.start("screen")
        record.stop()
        second = record.start("screen")
        record.stop()
        self.assertNotEqual(first, second)
        self.assertTrue(first.read_bytes().endswith(b"finalized"))

    def test_slow_saved_notification_does_not_block_the_next_recording(self):
        with patch.dict(os.environ, {"LUNA_TEST_NOTICE_DELAY": "1.5"}):
            first = record.start("screen")
            previous = record.status()
            record.stop()
            self.assertEqual(record.process_identity(previous["pid"]), previous["identity"])
            second = record.start("screen")
            record.stop()
        self.assertNotEqual(first, second)
        self.assertTrue(first.read_bytes().endswith(b"finalized"))
        self.assertTrue(second.read_bytes().endswith(b"finalized"))

    def test_interrupted_start_stops_the_worker_and_finalizes_its_child(self):
        original_status = record.status
        worker = {}

        def interrupt_after_recorder_starts():
            state = original_status()
            if state["running"] and (self.root / "arguments.json").exists():
                worker.update(state)
                raise KeyboardInterrupt()
            return state

        with patch.object(record, "status", side_effect=interrupt_after_recorder_starts):
            with self.assertRaises(KeyboardInterrupt):
                record.start("screen")
        self.assertTrue(worker)
        self.assertIsNone(record.process_identity(worker["pid"]))
        self.assertFalse(record.status()["running"])
        self.assertTrue(Path(worker["file"]).read_bytes().endswith(b"finalized"))

    def test_environment_uses_system_libraries(self):
        with patch.dict(os.environ, {"LD_LIBRARY_PATH": "/fake", "LD_PRELOAD": "/fake.so"}):
            self.assertNotIn("LD_LIBRARY_PATH", record.environment())
            self.assertNotIn("LD_PRELOAD", record.environment())

    def test_invalid_mode_is_rejected_before_capture(self):
        with self.assertRaisesRegex(ValueError, "region or screen"):
            record.start("all")


if __name__ == "__main__":
    unittest.main()
