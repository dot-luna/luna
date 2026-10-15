"""Check best-effort Docker activation with fake sudo and systemctl commands."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]


class SetupServicesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna services '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.checkout = self.root / "checkout"
        for name in ("scripts/setup/services.sh", "lib/common.sh"):
            destination = self.checkout / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, destination)
        self.env = dict(os.environ, PATH=str(self.bin) + ":" + os.environ["PATH"],
                        HOME=str(self.root / "home"), TEST_SERVICE_ROOT=str(self.root), BASH_ENV="")
        for name in ("TEST_MANAGER_STATUS", "TEST_ENABLE_STATUS", "TEST_ENABLED_STATUS", "TEST_ACTIVE_STATUS"):
            self.env.pop(name, None)

        backend = f"#!{sys.executable}\n" + '''
import json, os, pathlib, sys
root = pathlib.Path(os.environ["TEST_SERVICE_ROOT"])
tool = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with (root / "calls.jsonl").open("a") as output:
    output.write(json.dumps([tool, *args]) + "\\n")
if tool == "sudo":
    if not args or args[0] != "systemctl":
        sys.exit("Unexpected sudo invocation")
    os.execv(str(root / "bin/systemctl"), args)
statuses = {
    ("show", "--property=Version"): "TEST_MANAGER_STATUS",
    ("enable", "--now", "docker.service"): "TEST_ENABLE_STATUS",
    ("is-enabled", "--quiet", "docker.service"): "TEST_ENABLED_STATUS",
    ("is-active", "--quiet", "docker.service"): "TEST_ACTIVE_STATUS",
}
if tuple(args) not in statuses:
    sys.exit("Unexpected systemctl invocation: " + repr(args))
if args[0] == "enable":
    print("Fixture systemctl output")
sys.exit(int(os.environ.get(statuses[tuple(args)], "0")))
'''
        for name in ("sudo", "systemctl"):
            path = self.bin / name
            path.write_text(backend)
            path.chmod(0o755)

    def setup(self, *arguments):
        return subprocess.run(["bash", str(self.checkout / "scripts/setup/services.sh"), *arguments],
                              env=self.env, cwd=self.root, input="", capture_output=True,
                              text=True, timeout=10)

    def calls(self):
        path = self.root / "calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_docker_is_enabled_started_and_verified(self):
        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Docker is enabled and running", result.stdout)
        self.assertIn("Fixture systemctl output", result.stdout)
        self.assertEqual([call for call in self.calls() if call[0] == "systemctl"], [
            ["systemctl", "show", "--property=Version"],
            ["systemctl", "enable", "--now", "docker.service"],
            ["systemctl", "is-enabled", "--quiet", "docker.service"],
            ["systemctl", "is-active", "--quiet", "docker.service"],
        ])
        expected = [["sudo", "systemctl", "enable", "--now", "docker.service"]] if os.geteuid() else []
        self.assertEqual([call for call in self.calls() if call[0] == "sudo"], expected)

    def test_unavailable_manager_warns_without_privileged_commands(self):
        self.env["TEST_MANAGER_STATUS"] = "1"
        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("running systemd manager is unavailable", result.stdout + result.stderr)
        self.assertEqual(self.calls(), [["systemctl", "show", "--property=Version"]])

    def test_enable_failure_warns_and_continues(self):
        self.env["TEST_ENABLE_STATUS"] = "5"
        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("could not be enabled or started", result.stdout + result.stderr)
        self.assertNotIn("Docker is enabled and running", result.stdout)
        self.assertFalse(any(call[1] in ("is-active", "is-enabled") for call in self.calls()))

    def test_unhealthy_or_disabled_service_warns_after_enable(self):
        for name in ("TEST_ENABLED_STATUS", "TEST_ACTIVE_STATUS"):
            with self.subTest(status=name):
                self.env[name] = "1"
                result = self.setup()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("not both enabled and running", result.stdout + result.stderr)
                self.assertNotIn("Docker is enabled and running", result.stdout)
                del self.env[name]

    def test_help_and_unknown_options_do_not_run_commands(self):
        result = self.setup("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.setup("--unknown").returncode, 2)
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
