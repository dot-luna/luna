"""Keep the Stay awake command useful to existing UI callers through the new API."""

import json
import unittest

from test_idle import ScreensaverFixture


class AwakeTests(ScreensaverFixture, unittest.TestCase):
    def test_default_status_does_not_start_controller(self):
        result = self.cli("awake")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"enabled": False})
        self.assertFalse((self.root / "running").exists())
        self.assertTrue(all(call[0] == "ipc" for call in self.calls()))

    def test_toggle_captures_startup_logs_and_keeps_shared_preferences(self):
        before = '[idle]\nscreensaver_seconds = 120\nlock_seconds = 900\n'
        self.config.write_text(before)
        for action, expected in [("toggle", True), ("status", True), ("on", True),
                                 ("toggle", False), ("off", False), ("on", True)]:
            result = self.cli("awake", action)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {"enabled": expected})
            self.assertEqual(self.config.read_text(), before)
        self.assertEqual(len(self.starts()), 1)
        self.assertTrue(any(call[-1] == "toggleStayAwake" for call in self.calls()))
        self.assertTrue(any(call[-2:] == ["setStayAwake", "true"] for call in self.calls()))
        self.assertTrue(any(call[-2:] == ["setStayAwake", "false"] for call in self.calls()))

    def test_failed_start_keeps_stdout_clean_and_reports_output(self):
        self.env["TEST_START_FAILURE"] = "1"
        result = self.cli("awake", "on")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("Mock compositor unavailable", result.stderr)
        self.assertFalse(any("setStayAwake" in call for call in self.calls()))

    def test_running_controller_is_not_started_again(self):
        (self.root / "running").touch()
        result = self.cli("awake", "on")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"enabled": True})
        self.assertFalse(self.starts())

    def test_running_read_failure_does_not_claim_disabled(self):
        (self.root / "running").touch()
        self.env["TEST_FAIL_METHOD"] = "getState"
        result = self.cli("awake", "status")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("Could not read screensaver state", result.stderr)

    def test_failed_toggle_reports_error_without_claiming_success(self):
        (self.root / "running").touch()
        self.env["TEST_FAIL_METHOD"] = "toggleStayAwake"
        result = self.cli("awake", "toggle")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Could not update Stay awake", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_invalid_status_responses_are_rejected(self):
        (self.root / "running").touch()
        for value in ["", "ready", "null", "{}", '{"stayAwake":"false"}']:
            with self.subTest(value=value):
                self.env["TEST_STATE_RESPONSE"] = value
                result = self.cli("awake", "status")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Invalid screensaver state", result.stderr)

    def test_invalid_action_does_not_contact_controller(self):
        self.assertNotEqual(self.cli("awake", "invalid").returncode, 0)
        self.assertFalse(self.calls())


if __name__ == "__main__":
    unittest.main()
