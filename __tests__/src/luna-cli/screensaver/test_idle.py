"""Validate screensaver CLI and idle preference adapters without host processes."""

import importlib.util
import json
from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[4]
SPEC = importlib.util.spec_from_file_location("screensaver_fixture", ROOT / "__tests__/src/screensaver/src/test_runtime.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
ScreensaverFixture = MODULE.ScreensaverFixture


class IdleTests(ScreensaverFixture, unittest.TestCase):
    def test_defaults_and_independent_toggles(self):
        result = self.cli("idle", "status")
        self.assertEqual(json.loads(result.stdout),
                         {"screensaver_seconds": 300, "lock_seconds": 600, "display_off_seconds": 0})
        self.assertFalse(self.calls())
        for name, value in (("screensaver", "0"), ("lock", "900"), ("display", "1200")):
            result = self.cli("idle", "set", name, value)
            self.assertEqual(result.returncode, 0, result.stderr)
        expected = {"screensaver_seconds": 0, "lock_seconds": 900, "display_off_seconds": 1200}
        self.assertEqual(json.loads(self.cli("idle", "status").stdout), expected)
        self.assertEqual(tomllib.loads(self.config.read_text())["idle"], expected)
        self.assertEqual(len(self.starts()), 1)
        self.assertFalse((self.config.parent / "idle.json").exists())

    def test_invalid_setting_keeps_saved_preferences(self):
        self.assertEqual(self.cli("idle", "set", "lock", "600").returncode, 0)
        before = self.config.read_bytes()
        for args in [("set", "lock", "-1"), ("set", "lock", "0.5"),
                     ("set", "display", "90000"), ("set", "lock", "bad"),
                     ("set", "lock"), ("set", "unknown", "5")]:
            result = self.cli("idle", *args)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(self.config.read_bytes(), before)

    def test_bare_screensaver_shows_and_explicit_start_stays_hidden(self):
        result = self.cli("screensaver", "start")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertFalse(json.loads((self.root / "state").read_text())["active"])
        result = self.cli("screensaver")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertTrue(json.loads((self.root / "state").read_text())["active"])
        self.assertTrue(any(call[-1] == "show" for call in self.calls()))

    def test_config_commands_are_offline_and_support_wallpaper_spelling(self):
        result = self.cli("screensaver", "get-config", "idle.lock_seconds")
        self.assertEqual(result.stdout, "600\n")
        result = self.cli("screensaver", "updateConfig", '{"settings":{"clock":false}}')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIs(json.loads(result.stdout)["settings"]["clock"], False)
        self.assertEqual(self.cli("screensaver", "getConfig", "settings.clock").stdout, "false\n")
        self.assertEqual(self.cli("screensaver", "get-config-file").stdout.strip(), str(self.config))
        self.assertEqual(self.cli("screensaver", "getConfigFile").stdout.strip(), str(self.config))
        self.assertFalse(self.calls())

    def test_invalid_saved_config_is_rejected_and_old_json_is_not_read(self):
        (self.config.parent / "idle.json").write_text('{"lock_seconds":42}')
        result = self.cli("idle", "status")
        self.assertEqual(json.loads(result.stdout)["lock_seconds"], 600)
        self.config.write_text('[idle]\nlock_seconds = false\n')
        self.assertNotEqual(self.cli("idle", "status").returncode, 0)

    def test_status_state_and_hide_never_launch(self):
        self.assertEqual(self.cli("screensaver", "status").stdout, "stopped\n")
        self.assertFalse(json.loads(self.cli("screensaver", "state").stdout)["running"])
        self.assertEqual(self.cli("screensaver", "hide").returncode, 0)
        self.assertFalse(self.starts())

    def test_apply_failure_reports_saved_file_and_keeps_stdout_clean(self):
        self.env["TEST_START_FAILURE"] = "1"
        result = self.cli("idle", "set", "display", "900")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("Idle settings saved", result.stderr)
        self.assertEqual(tomllib.loads(self.config.read_text())["idle"]["display_off_seconds"], 900)


if __name__ == "__main__":
    unittest.main()
