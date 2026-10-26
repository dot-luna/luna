"""Exercise session reload using fake compositor commands, never the live desktop."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]


class SetupSessionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna session '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.checkout = self.root / "checkout"
        for name in ("scripts/setup/15-reload-hyprland.sh", "lib/common.sh"):
            destination = self.checkout / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, destination)

        # A closed PATH prevents a missing mock from exposing the real hyprctl.
        for name in ("bash", "readlink", "dirname"):
            (self.bin / name).symlink_to(shutil.which(name))
        self.env = dict(os.environ, PATH=str(self.bin), HOME=str(self.root / "home"),
                        TEST_SESSION_ROOT=str(self.root), BASH_ENV="", NO_COLOR="1",
                        HYPRLAND_INSTANCE_SIGNATURE="fixture-session")
        for name in ("TEST_RELOAD_STATUS", "TEST_TIMEOUT_STATUS"):
            self.env.pop(name, None)
        backend = f"#!{sys.executable}\n" + '''
import json, os, pathlib, sys
root = pathlib.Path(os.environ["TEST_SESSION_ROOT"])
tool = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with (root / "calls.jsonl").open("a") as output:
    output.write(json.dumps([tool, *args]) + "\\n")
if tool == "timeout":
    if args != ["--kill-after=2s", "10s", "hyprctl", "reload"]:
        sys.exit("Unexpected timeout invocation")
    status = int(os.environ.get("TEST_TIMEOUT_STATUS", "0"))
    if status:
        sys.exit(status)
    os.execv(str(root / "bin/hyprctl"), args[2:])
if args != ["reload"]:
    sys.exit("Unexpected hyprctl invocation")
print("Fixture compositor output")
sys.exit(int(os.environ.get("TEST_RELOAD_STATUS", "0")))
'''
        for name in ("timeout", "hyprctl"):
            path = self.bin / name
            path.write_text(backend)
            path.chmod(0o755)

    def setup(self, *arguments):
        return subprocess.run([str(self.bin / "bash"), str(self.checkout / "scripts/setup/15-reload-hyprland.sh"),
                               *arguments], env=self.env, cwd=self.root, input="",
                              capture_output=True, text=True, timeout=5)

    def calls(self):
        path = self.root / "calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_active_session_reloads_without_input_and_streams_output(self):
        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Hyprland configuration reloaded", result.stdout)
        self.assertIn("  Fixture compositor output", result.stdout)
        self.assertEqual(self.calls(), [
            ["timeout", "--kill-after=2s", "10s", "hyprctl", "reload"],
            ["hyprctl", "reload"],
        ])

    def test_absent_and_empty_session_skip_without_commands(self):
        for value in (None, ""):
            with self.subTest(signature=value):
                if value is None:
                    self.env.pop("HYPRLAND_INSTANCE_SIGNATURE", None)
                else:
                    self.env["HYPRLAND_INSTANCE_SIGNATURE"] = value
                result = self.setup()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("No active Hyprland session", result.stdout)
                self.assertEqual(self.calls(), [])

    def test_missing_hyprctl_warns_without_failing_setup(self):
        (self.bin / "hyprctl").unlink()
        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("hyprctl is unavailable", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_failed_or_timed_out_reload_warns_without_failing_setup(self):
        for name, value in (("TEST_RELOAD_STATUS", "1"), ("TEST_TIMEOUT_STATUS", "124")):
            with self.subTest(failure=name):
                self.env[name] = value
                result = self.setup()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("could not be reloaded", result.stderr)
                self.assertNotIn("Hyprland configuration reloaded", result.stdout)
                del self.env[name]

    def test_reload_works_when_timeout_is_unavailable(self):
        (self.bin / "timeout").unlink()
        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [["hyprctl", "reload"]])

    def test_arguments_are_ignored_and_not_forwarded_to_compositor(self):
        result = self.setup("--help", "-h", "--force", "--unknown", "main")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.calls(), [
            ["timeout", "--kill-after=2s", "10s", "hyprctl", "reload"],
            ["hyprctl", "reload"],
        ])


if __name__ == "__main__":
    unittest.main()
