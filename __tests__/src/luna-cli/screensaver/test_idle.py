"""Validate idle preferences and shell commands without changing the host session."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class IdleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        tool = self.root / "qs"
        tool.write_text("#!/bin/sh\nexit 0\n")
        tool.chmod(0o755)
        self.env = dict(os.environ, XDG_CONFIG_HOME=str(self.root / "config"),
                        PATH=str(self.root) + ":" + os.environ["PATH"], WAYLAND_DISPLAY="test")

    def cli(self, *args):
        return subprocess.run([str(ROOT / "bin/luna"), "idle", *args],
                              env=self.env, text=True, capture_output=True, timeout=10)

    def test_defaults_and_independent_toggles(self):
        result = self.cli("status")
        self.assertEqual(json.loads(result.stdout), {"screensaver_seconds": 300, "lock_seconds": 600})
        result = self.cli("set", "screensaver", "0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"screensaver_seconds": 0, "lock_seconds": 600})
        result = self.cli("set", "lock", "900")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.cli("status").stdout), {"screensaver_seconds": 0, "lock_seconds": 900})

    def test_invalid_setting_keeps_saved_preferences(self):
        self.assertEqual(self.cli("set", "lock", "600").returncode, 0)
        path = self.root / "config/luna/idle.json"
        before = path.read_text()
        for args in [("set", "lock", "-1"), ("set", "lock", "0.5"),
                     ("set", "lock", "90000"), ("set", "lock", "bad"),
                     ("set", "lock"), ("set", "unknown", "5")]:
            self.assertNotEqual(self.cli(*args).returncode, 0)
            self.assertEqual(path.read_text(), before)

    def test_bare_screensaver_defaults_to_open(self):
        tool = self.root / "qs"
        tool.write_text("""#!/usr/bin/python3
import json, os, pathlib, sys
with pathlib.Path(os.environ["TEST_QS_LOG"]).open("a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
""")
        self.env["TEST_QS_LOG"] = str(self.root / "qs.log")
        result = subprocess.run([str(ROOT / "bin/luna"), "screensaver"],
                                env=self.env, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [json.loads(line) for line in (self.root / "qs.log").read_text().splitlines()]
        self.assertEqual(calls[-1][-3:], ["call", "screensaver", "open"])

    def test_invalid_saved_config_is_rejected(self):
        path = self.root / "config/luna/idle.json"
        path.parent.mkdir(parents=True)
        path.write_text('{"lock_seconds": false}')
        self.assertNotEqual(self.cli("status").returncode, 0)
