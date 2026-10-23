"""Run the screensaver controller offscreen with simulated idle and lock backends."""

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


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(all(shutil.which(tool) for tool in ("qs", "lua")), "Quickshell and Lua required")
class AwakeShellTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luna-awake-shell-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.renderer = self.root / "src/screensaver"
        self.renderer.mkdir(parents=True)
        tools = self.root / "bin"
        tools.mkdir()
        (tools / "luna").symlink_to(ROOT / "bin/luna")

        # Keep the production controller, IPC, bindings, and Process callbacks. Only
        # compositor sensors and surfaces need substitutes on Qt's offscreen backend.
        source = (ROOT / "src/screensaver/shell.qml").read_text()
        controller, boundary, _ = source.partition("\n    Variants {")
        self.assertTrue(boundary, "Cannot locate the screensaver's rendering boundary")
        controller = controller.replace("import Quickshell.Wayland\n", "")
        controller = controller.replace("import Quickshell.Hyprland\n", "")
        controller = controller.replace("import Luna as Luna\n", "")
        controller = controller.replace("IdleMonitor {", "FakeIdleMonitor {")
        controller = controller.replace(
            'Hyprland.focusedMonitor?.name || Quickshell.screens[0]?.name || ""', '"test-screen"')
        (self.renderer / "shell.qml").write_text(controller + '''
    IpcHandler {
        target: "test"
        function state(): string {
            return JSON.stringify({awake: shell.stayAwake, showing: shell.showing,
                pending: shell.pendingAction, checking: lockCheck.running, locking: locker.running,
                saverEnabled: saverIdle.enabled, lockEnabled: lockIdle.enabled,
                saverTimeout: saverIdle.timeout, lockTimeout: lockIdle.timeout, config: shell.config});
        }
        function idle(action: string, value: bool): void {
            if (action === "auto") saverIdle.isIdle = value;
            else if (action === "lock") lockIdle.isIdle = value;
        }
    }
}
''')
        (self.renderer / "FakeIdleMonitor.qml").write_text('''import QtQuick
QtObject {
    property bool enabled: false
    property bool isIdle: false
    property int timeout: 0
    property bool respectInhibitors: false
    onEnabledChanged: if (!enabled) isIdle = false
}
''')
        mock = textwrap.dedent('''\
            #!/usr/bin/python3
            import json, os, pathlib, sys, time
            root = pathlib.Path(os.environ["TEST_AWAKE_ROOT"])
            name = pathlib.Path(sys.argv[0]).name
            with (root / "commands").open("a") as log:
                log.write(json.dumps({"tool": name, "args": sys.argv[1:]}) + "\\n")
            if name == "hyprctl":
                deadline = time.monotonic() + 5
                while (root / "hold-check").exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                print('{"locked":false}')
        ''')
        for name in ("hyprctl", "hyprlock", "notify-send"):
            path = tools / name
            path.write_text(mock)
            path.chmod(0o755)

        runtime = self.root / "runtime"
        runtime.mkdir(mode=0o700)
        self.env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QS_NO_RELOAD_POPUP="1",
                        XDG_RUNTIME_DIR=str(runtime), XDG_CONFIG_HOME=str(self.root / "config"),
                        XDG_DATA_HOME=str(self.root / "data"), XDG_CACHE_HOME=str(self.root / "cache"),
                        PATH=str(tools) + ":" + os.environ["PATH"], TEST_AWAKE_ROOT=str(self.root),
                        WAYLAND_DISPLAY="luna-test-mocked", LUNA_IDLE_CONFIG=json.dumps({
                            "screensaver_seconds": 300, "lock_seconds": 600}))
        self.env.pop("HYPRLAND_INSTANCE_SIGNATURE", None)
        self.log = (self.root / "shell.log").open("w+")
        self.addCleanup(self.log.close)
        self.process = subprocess.Popen(["qs", "-p", str(self.renderer)], env=self.env,
                                        stdout=self.log, stderr=subprocess.STDOUT, start_new_session=True)
        self.addCleanup(self.stop)
        self.until(lambda: self.ipc("ping", check=False).returncode == 0)

    def stop(self):
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        self.process.wait(timeout=5)

    def ipc(self, method, *arguments, target="screensaver", check=True):
        values = [str(value).lower() if isinstance(value, bool) else str(value) for value in arguments]
        return subprocess.run(["qs", "ipc", "-p", str(self.renderer), "call", target, method, *values],
                              env=self.env, text=True, capture_output=True, timeout=3, check=check)

    def state(self):
        return json.loads(self.ipc("state", target="test").stdout)

    def idle(self, action, value=True):
        self.ipc("idle", action, value, target="test")

    def calls(self, tool):
        path = self.root / "commands"
        values = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        return [value for value in values if value["tool"] == tool]

    def until(self, predicate, timeout=4):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            if self.process.poll() is not None:
                break
            time.sleep(0.02)
        self.fail("Screensaver condition failed: " + (self.root / "shell.log").read_text())

    def test_awake_disables_both_timers_and_restores_independent_preferences(self):
        for saver, lock in [(300, 600), (0, 900), (120, 0), (0, 0)]:
            with self.subTest(screensaver=saver, lock=lock):
                config = {"screensaver_seconds": saver, "lock_seconds": lock}
                self.ipc("configure", json.dumps(config))
                self.assertEqual(json.loads(self.ipc("setAwake", "on").stdout), {"enabled": True})
                state = self.state()
                self.assertFalse(state["saverEnabled"])
                self.assertFalse(state["lockEnabled"])
                self.assertEqual(state["config"], config)
                self.assertEqual((state["saverTimeout"], state["lockTimeout"]), (saver, lock))

                self.ipc("setAwake", "off")
                state = self.state()
                self.assertEqual(state["saverEnabled"], saver > 0)
                self.assertEqual(state["lockEnabled"], lock > 0)
                self.assertEqual(state["config"], config)

    def test_state_transitions_are_atomic_and_invalid_actions_do_not_change_state(self):
        self.assertEqual(json.loads(self.ipc("awakeStatus").stdout), {"enabled": False})
        for action, expected in [("on", True), ("on", True), ("toggle", False),
                                 ("off", False), ("toggle", True)]:
            self.assertEqual(json.loads(self.ipc("setAwake", action).stdout), {"enabled": expected})
            self.assertEqual(self.state()["awake"], expected)
        self.assertIn("error", json.loads(self.ipc("setAwake", "invalid").stdout))
        self.assertTrue(self.state()["awake"])

    def test_queued_idle_actions_are_cancelled_during_a_delayed_lock_check(self):
        for action in ("auto", "lock"):
            with self.subTest(action=action):
                self.ipc("setAwake", "off")
                hold = self.root / "hold-check"
                hold.touch()
                count = len(self.calls("hyprctl"))
                self.idle(action)
                self.until(lambda: len(self.calls("hyprctl")) > count)
                self.assertTrue(self.state()["checking"])
                self.assertEqual(self.state()["pending"], action)

                self.ipc("setAwake", "on")
                self.assertEqual(self.state()["pending"], "")
                hold.unlink()
                self.until(lambda: not self.state()["checking"])
                self.assertFalse(self.state()["showing"])
                self.assertFalse(self.state()["locking"])
                self.assertEqual(self.calls("hyprlock"), [])

    def test_late_idle_signals_cannot_start_automatic_work_while_awake(self):
        self.ipc("setAwake", "on")
        # Deliver stale compositor events after inhibition to exercise the request guard.
        self.idle("auto")
        self.idle("lock")
        state = self.state()
        self.assertEqual(state["pending"], "")
        self.assertFalse(state["showing"])
        self.assertFalse(state["checking"])
        self.assertFalse(state["locking"])
        self.assertEqual(self.calls("hyprctl"), [])
        self.assertEqual(self.calls("hyprlock"), [])

    def test_manual_screensaver_and_manual_lock_work_while_awake(self):
        self.ipc("setAwake", "on")
        self.ipc("open")
        self.until(lambda: self.state()["showing"])
        self.assertTrue(self.state()["awake"])
        self.ipc("hide")

        result = subprocess.run([str(ROOT / "bin/luna"), "lock"], env=self.env,
                                text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.calls("hyprlock")), 1)
        self.assertEqual(self.calls("hyprlock")[0]["args"][-2:], ["--grace", "0"])
        self.assertTrue(self.state()["awake"])
        self.assertFalse(self.state()["saverEnabled"])
        self.assertFalse(self.state()["lockEnabled"])

    def test_automatic_actions_resume_after_switching_awake_off(self):
        self.ipc("setAwake", "on")
        self.ipc("setAwake", "off")
        self.idle("auto")
        self.until(lambda: self.state()["showing"])
        self.idle("auto", False)
        self.assertFalse(self.state()["showing"])
        self.idle("lock")
        self.until(lambda: len(self.calls("hyprlock")) == 1)
        self.until(lambda: not self.state()["locking"])
        self.assertFalse(self.state()["showing"])

    def test_configuring_timeouts_while_awake_applies_when_toggled_off(self):
        self.ipc("setAwake", "on")
        self.ipc("configure", json.dumps({"screensaver_seconds": 0, "lock_seconds": 1200}))
        self.assertFalse(self.state()["saverEnabled"])
        self.assertFalse(self.state()["lockEnabled"])
        self.ipc("setAwake", "off")
        self.assertFalse(self.state()["saverEnabled"])
        self.assertTrue(self.state()["lockEnabled"])
        self.assertEqual(self.state()["lockTimeout"], 1200)


if __name__ == "__main__":
    unittest.main()
