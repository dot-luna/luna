"""Exercise the shared Stay awake controller against an isolated session CLI."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import textwrap
import time
import unittest


REPO = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("qs") and shutil.which("dbus-run-session"),
                     "Quickshell and dbus-run-session required")
class StayAwakeUiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna awake ' ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        module = self.root / "src/qml/Luna"
        module.mkdir(parents=True)
        shutil.copy(REPO / "src/qml/Luna/StayAwake.qml", module)
        (module / "qmldir").write_text("module Luna\nsingleton StayAwake 1.0 StayAwake.qml\n")
        (self.root / "shell.qml").write_text('''import QtQuick
import Quickshell
import Quickshell.Io
import Luna as Luna
ShellRoot {
    IpcHandler {
        target: "test"
        function state(): string {
            return JSON.stringify({enabled: Luna.StayAwake.enabled, ready: Luna.StayAwake.ready,
                busy: Luna.StayAwake.busy, error: Luna.StayAwake.error});
        }
        function run(actions: string): void {
            for (const action of actions.split(",")) {
                if (action === "toggle") Luna.StayAwake.toggle();
                else Luna.StayAwake.refresh();
            }
        }
    }
}
''')

        # Preserve the checkout layout so the real QML URL-to-path conversion is exercised.
        cli = self.root / "bin/luna"
        cli.parent.mkdir()
        cli.write_text(textwrap.dedent('''\
            #!/usr/bin/python3
            import json, os, pathlib, sys, time
            root = pathlib.Path(os.environ["LUNA_AWAKE_UI_TEST_ROOT"])
            options = json.loads((root / "options").read_text())
            with (root / "calls").open("a") as log:
                log.write(json.dumps(sys.argv[1:]) + "\\n")
            time.sleep(options.get("delay", 0))
            if "output" in options:
                print(options["output"])
            elif options.get("exit", 0) == 0:
                enabled = (root / "enabled").read_text() == "true"
                if sys.argv[2] == "toggle":
                    enabled = not enabled
                    (root / "enabled").write_text(str(enabled).lower())
                print(json.dumps({"enabled": enabled}))
            if options.get("error"):
                print(options["error"], file=sys.stderr)
            sys.exit(options.get("exit", 0))
        '''))
        cli.chmod(0o755)
        (self.root / "enabled").write_text("false")
        self.options()

        runtime = self.root / "runtime"
        runtime.mkdir(mode=0o700)
        self.environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", XDG_RUNTIME_DIR=str(runtime),
                                QML_IMPORT_PATH=str(self.root / "src/qml"), QS_NO_RELOAD_POPUP="1",
                                LUNA_AWAKE_UI_TEST_ROOT=str(self.root),
                                DBUS_SYSTEM_BUS_ADDRESS="unix:path=/nonexistent-luna-test-system-bus")
        self.environment.pop("WAYLAND_DISPLAY", None)
        self.log = (self.root / "shell.log").open("w+")
        self.addCleanup(self.log.close)
        self.process = subprocess.Popen(["dbus-run-session", "--", "qs", "-p", str(self.root)],
                                        env=self.environment, stdout=self.log, stderr=subprocess.STDOUT,
                                        start_new_session=True)
        self.addCleanup(self.stop)
        self.until(lambda: self.ipc("state", check=False).stdout.startswith("{"))

    def stop(self):
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        self.process.wait(timeout=5)

    def options(self, **values):
        (self.root / "options").write_text(json.dumps(values))

    def ipc(self, method, *arguments, check=True):
        return subprocess.run(["qs", "ipc", "-p", str(self.root), "call", "test", method, *arguments],
                              env=self.environment, capture_output=True, text=True, timeout=3, check=check)

    def state(self):
        return json.loads(self.ipc("state").stdout)

    def calls(self):
        path = self.root / "calls"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def until(self, predicate):
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            if predicate():
                return
            if self.process.poll() is not None:
                break
            time.sleep(0.02)
        self.fail("Stay awake condition failed: " + (self.root / "shell.log").read_text())

    def run_action(self, action):
        self.ipc("run", action)
        self.until(lambda: not self.state()["busy"])
        return self.state()

    def test_commands_serialize_and_external_state_refreshes(self):
        self.assertFalse(self.state()["ready"])
        self.run_action("toggle")
        self.assertEqual(self.calls(), [])

        self.options(delay=0.2)
        self.ipc("run", "status,status,toggle")
        self.assertTrue(self.state()["busy"])
        self.until(lambda: not self.state()["busy"])
        self.assertTrue(self.state()["ready"])
        self.assertEqual(self.calls(), [["awake", "status"]])

        self.ipc("run", "toggle,toggle,status")
        self.assertTrue(self.state()["busy"])
        self.assertFalse(self.state()["enabled"])
        self.until(lambda: not self.state()["busy"])
        self.assertTrue(self.state()["enabled"])
        self.assertEqual(self.calls(), [["awake", "status"], ["awake", "toggle"]])

        (self.root / "enabled").write_text("false")
        self.assertFalse(self.run_action("status")["enabled"])

    def test_invalid_status_preserves_state_and_prevents_toggling(self):
        (self.root / "enabled").write_text("true")
        self.assertTrue(self.run_action("status")["enabled"])
        for output in ("not json", '{"enabled":"false"}', "null", "{}"):
            with self.subTest(output=output):
                self.options(output=output)
                state = self.run_action("status")
                self.assertTrue(state["enabled"])
                self.assertFalse(state["ready"])
                self.assertIn("status", state["error"])
                calls = self.calls()
                self.run_action("toggle")
                self.assertEqual(self.calls(), calls)

        self.options()
        state = self.run_action("status")
        self.assertTrue(state["ready"])
        self.assertEqual(state["error"], "")

    def test_failed_toggle_preserves_state_and_error_until_retry(self):
        self.run_action("status")
        # A nonzero command result must not apply even an otherwise valid JSON payload.
        self.options(exit=1, output='{"enabled":true}', error="Session unavailable")
        state = self.run_action("toggle")
        self.assertFalse(state["enabled"])
        self.assertTrue(state["ready"])
        self.assertEqual(state["error"], "Session unavailable")

        self.options()
        self.assertEqual(self.run_action("status")["error"], "Session unavailable")
        state = self.run_action("toggle")
        self.assertTrue(state["enabled"])
        self.assertEqual(state["error"], "")

    def test_missing_cli_reports_failure_and_allows_retry(self):
        cli = self.root / "bin/luna"
        saved = self.root / "bin/luna-saved"
        cli.rename(saved)
        state = self.run_action("status")
        self.assertFalse(state["ready"])
        self.assertFalse(state["busy"])
        self.assertIn("status", state["error"])

        saved.rename(cli)
        state = self.run_action("status")
        self.assertTrue(state["ready"])
        self.assertEqual(state["error"], "")


if __name__ == "__main__":
    unittest.main()
