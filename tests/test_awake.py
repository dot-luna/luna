"""Exercise Stay awake IPC through the CLI without changing the desktop session."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AwakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luna awake '")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        tool = self.root / "qs"
        tool.write_text("""#!/usr/bin/python3
import json, os, pathlib, sys

root = pathlib.Path(os.environ["TEST_ROOT"])
with (root / "commands").open("a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")

running = root / "running"
state = root / "state"
if sys.argv[1] != "ipc":
    print("INFO: Launching screensaver")
    if os.environ.get("TEST_QS_START_FAILURE"):
        print("Mock compositor unavailable")
        sys.exit(1)
    running.touch()
    state.write_text("false")
    sys.exit(0)
if not running.exists():
    sys.exit(1)

method = sys.argv[sys.argv.index("screensaver") + 1]
if method == os.environ.get("TEST_QS_BROKEN"):
    sys.exit(1)
if method == "ping":
    print("ready")
elif method in ("awakeStatus", "setAwake"):
    enabled = json.loads(state.read_text()) if state.exists() else False
    if method == "setAwake":
        action = sys.argv[-1]
        enabled = not enabled if action == "toggle" else action == "on"
        state.write_text(json.dumps(enabled))
    print(os.environ.get("TEST_QS_RESPONSE", json.dumps({"enabled": enabled})))
else:
    sys.exit(1)
""")
        tool.chmod(0o755)
        self.env = dict(os.environ, TEST_ROOT=str(self.root),
                        XDG_CONFIG_HOME=str(self.root / "config"),
                        XDG_DATA_HOME=str(self.root / "data"),
                        PATH=str(self.root) + ":" + os.environ["PATH"],
                        WAYLAND_DISPLAY="test")

    def cli(self, *args):
        return subprocess.run([str(ROOT / "bin/luna"), "awake", *args],
                              env=self.env, text=True, capture_output=True, timeout=10)

    def calls(self):
        return [json.loads(line) for line in (self.root / "commands").read_text().splitlines()]

    def test_default_status_does_not_start_idle_monitor(self):
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"enabled": False})
        self.assertFalse((self.root / "running").exists())
        self.assertTrue(all(call[0] == "ipc" for call in self.calls()))

    def test_toggle_captures_startup_logs_and_keeps_shared_preferences(self):
        preferences = self.root / "config/luna/idle.json"
        preferences.parent.mkdir(parents=True)
        before = '{"screensaver_seconds":120,"lock_seconds":900}\n'
        preferences.write_text(before)

        for action, expected in [("toggle", True), ("status", True), ("on", True),
                                 ("toggle", False), ("off", False), ("on", True)]:
            result = self.cli(action)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {"enabled": expected})
            self.assertEqual(preferences.read_text(), before)

        starts = [call for call in self.calls() if call[0] != "ipc"]
        self.assertEqual(len(starts), 1)
        self.assertIn("--no-duplicate", starts[0])
        self.assertTrue(any(call[-4:] == ["call", "screensaver", "setAwake", "toggle"]
                            for call in self.calls()))

    def test_failed_start_keeps_stdout_clean_and_reports_startup_output(self):
        self.env["TEST_QS_START_FAILURE"] = "1"
        result = self.cli("on")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("Could not start the idle monitor for Stay awake", result.stderr)
        self.assertIn("Mock compositor unavailable", result.stderr)
        self.assertFalse((self.root / "running").exists())
        self.assertFalse(any("setAwake" in call for call in self.calls()))

    def test_running_monitor_is_not_started_again(self):
        (self.root / "running").touch()
        result = self.cli("on")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"enabled": True})
        self.assertTrue(all(call[0] == "ipc" for call in self.calls()))

    def test_status_failure_on_running_monitor_is_not_reported_as_disabled(self):
        (self.root / "running").touch()
        self.env["TEST_QS_BROKEN"] = "awakeStatus"
        result = self.cli("status")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Could not read Stay awake", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_failed_toggle_reports_error_without_claiming_success(self):
        (self.root / "running").touch()
        self.env["TEST_QS_BROKEN"] = "setAwake"
        result = self.cli("toggle")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Could not update Stay awake", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_invalid_status_responses_are_rejected(self):
        (self.root / "running").touch()
        for value in ["", "ready", "null", "{}", '{"enabled":"false"}']:
            with self.subTest(value=value):
                self.env["TEST_QS_RESPONSE"] = value
                result = self.cli("status")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Invalid Stay awake response", result.stderr)

    def test_invalid_action_does_not_contact_monitor(self):
        result = self.cli("invalid")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "commands").exists())


if __name__ == "__main__":
    unittest.main()
