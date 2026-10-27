"""Keep QML bridge replies single JSON values with an explicit method allowlist."""

import json
import subprocess
import unittest

from test_runtime import REPO, ScreensaverFixture


class ScreensaverBridgeTests(ScreensaverFixture, unittest.TestCase):
    def request(self, method, argument=None, ok=True):
        return self.raw(json.dumps({"method": method, "argument": argument}), ok)

    def raw(self, request, ok=True):
        result = subprocess.run(["/usr/bin/lua", "-E", str(REPO / "src/screensaver/src/bridge.lua"), request],
                                cwd=self.root, env=self.env, text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 1)
        value = json.loads(result.stdout)
        self.assertIs(value["ok"], ok)
        if ok:
            self.assertEqual(value["configPath"], str(self.config))
        else:
            self.assertTrue(value["error"])
        return value

    def test_config_values_and_unknown_keys_roundtrip_offline(self):
        self.request("updateConfig", {"settings": {"clock": False, "count": 0, "colors": [], "extra": {}}})
        self.assertIs(self.request("getConfig", "settings.clock")["result"], False)
        self.assertEqual(self.request("getConfig", "settings.count")["result"], 0)
        self.assertEqual(self.request("getConfig", "settings.colors")["result"], [])
        self.assertEqual(self.request("getConfig", "settings.extra")["result"], None)
        self.assertIsNone(self.request("getConfig", "missing")["result"])
        self.assertFalse(self.calls())

    def test_start_output_is_captured_and_mutations_return_state(self):
        self.assertIsNone(self.request("start")["result"])
        self.assertTrue(self.request("setStayAwake", True)["result"]["stayAwake"])
        self.assertFalse(self.request("toggleStayAwake")["result"]["stayAwake"])
        self.assertTrue(self.request("getState")["result"]["running"])
        self.assertEqual(self.request("status")["result"], "idle")
        self.assertEqual(len(self.starts()), 1)

    def test_invalid_requests_do_not_invoke_processes_or_edit_files(self):
        for request in ("", "{", "null", "[]", '{"method":"execute"}',
                        '{"method":"start","method":"stop"}',
                        '{"method":"setStayAwake","argument":"true"}'):
            with self.subTest(request=request):
                self.raw(request, ok=False)
        self.assertFalse(self.calls())
        self.assertFalse(self.config.exists())

    def test_stopped_state_and_hide_are_passive(self):
        self.assertFalse(self.request("getState")["result"]["running"])
        self.assertIsNone(self.request("hide")["result"])
        self.assertEqual(self.request("status")["result"], "stopped")
        self.assertFalse(self.starts())

    def test_named_library_roundtrip_has_consistent_objects_and_arrays(self):
        source = self.root / "aurora.qml"
        source.write_text("import Quickshell\nShellRoot {}\n")
        installed = self.request("install", {"source": str(source), "options": {"name": "stars"}})["result"]
        self.assertEqual(installed["name"], "stars")
        self.assertFalse(installed["bundled"])
        entries = self.request("list")["result"]
        self.assertIsInstance(entries, list)
        self.assertEqual([entry["name"] for entry in entries], ["clock", "blank", "orbit", "stars"])
        self.assertTrue(entries[0]["current"])
        self.assertFalse(entries[3]["current"])
        self.assertEqual(self.request("getDirectory")["result"], str(self.root / "data/luna/screensavers"))
        self.assertFalse(self.calls())
        selected = self.request("set", "stars")["result"]
        self.assertTrue(selected["current"])
        self.request("remove", ["stars"], ok=False)
        self.request("set", "clock")
        self.assertEqual(self.request("removalPlan", ["stars"])["result"], [installed])
        self.assertEqual(self.request("remove", ["stars"])["result"], ["stars"])


if __name__ == "__main__":
    unittest.main()
