"""Test renderer handshakes through real Quickshell IPC in a private session."""

import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import unittest


REPO = Path(__file__).resolve().parents[5]
QS = shutil.which("qs")


@unittest.skipUnless(QS and shutil.which("dbus-run-session"), "Quickshell and D-Bus required")
class ScreensaverSessionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="luna screensaver ' # session ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name in ("home", "runtime", "config", "cache", "controller", "renderer", "bin"):
            (self.root / name).mkdir(mode=0o700)
        module = self.root / "qml/Luna"
        module.mkdir(parents=True)
        (module / "qmldir").write_text("module Luna\nsingleton ScreensaverSession 1.0 ScreensaverSession.qml\n")
        source = (REPO / "src/screensaver/src/shell/ScreensaverSession.qml").read_text()
        if self._testMethodName == "test_ready_timeout_releases_dismiss_and_kills_late_sender":
            source = source.replace('"3s"', '"0.1s"')
        (module / "ScreensaverSession.qml").write_text(source)
        self.token = "current token '#雪"
        self.controller = self.root / "controller/shell.qml"
        self.controller.write_text('''import QtQuick
import Quickshell
import Quickshell.Io
ShellRoot {
    id: shell
    property var events: []
    Component.onCompleted: Quickshell.watchFiles = false
    IpcHandler {
        target: "renderer"
        function ready(token: string): void {
            shell.events = shell.events.concat([{method: "ready", token: token}]);
        }
        function dismiss(token: string): void {
            shell.events = shell.events.concat([{method: "dismiss", token: token}]);
        }
    }
    IpcHandler {
        target: "test"
        function state(): string { return JSON.stringify(shell.events); }
    }
}
''')
        self.renderer = self.root / "renderer/shell.qml"
        self.renderer.write_text('''import QtQuick
import Quickshell
import Quickshell.Io
import Luna as Luna
ShellRoot {
    Component.onCompleted: Quickshell.watchFiles = false
    IpcHandler {
        target: "test"
        function state(): string {
            return JSON.stringify({managed: Luna.ScreensaverSession.managed,
                config: Luna.ScreensaverSession.config, settings: Luna.ScreensaverSession.settings,
                readyRequested: Luna.ScreensaverSession.readyRequested,
                dismissRequested: Luna.ScreensaverSession.dismissRequested,
                busy: Luna.ScreensaverSession.activeRequest !== null || Luna.ScreensaverSession.pending.length > 0,
                error: Luna.ScreensaverSession.error});
        }
        function ready(): void { Luna.ScreensaverSession.ready(); }
        function dismiss(): void { Luna.ScreensaverSession.dismiss(); }
        function both(): void {
            Luna.ScreensaverSession.ready();
            Luna.ScreensaverSession.ready();
            Luna.ScreensaverSession.dismiss();
            Luna.ScreensaverSession.dismiss();
        }
    }
}
''')
        environment = dict(os.environ, HOME=str(self.root / "home"), QT_QPA_PLATFORM="offscreen",
                           XDG_RUNTIME_DIR=str(self.root / "runtime"),
                           XDG_CONFIG_HOME=str(self.root / "config"), XDG_CACHE_HOME=str(self.root / "cache"),
                           QML_IMPORT_PATH=str(self.root / "qml"), QS_NO_RELOAD_POPUP="1",
                           LUNA_SCREENSAVER_CONTROLLER=str(self.controller), LUNA_SCREENSAVER_TOKEN=self.token,
                           LUNA_SCREENSAVER_SETTINGS=json.dumps({"idle": {"lock_seconds": 300},
                                                                "renderer": {"shell": ""},
                                                                "settings": {"orbit_seconds": 42}}),
                           DBUS_SYSTEM_BUS_ADDRESS="unix:path=/nonexistent-luna-test-system-bus")
        for name in ("WAYLAND_DISPLAY", "DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE",
                     "DBUS_SESSION_BUS_ADDRESS", "QML2_IMPORT_PATH"):
            environment.pop(name, None)
        self.environment = environment
        self.processes = []
        self.addCleanup(self.stop_all)
        self.start(self.controller)

    def start(self, path):
        log = (path.parent / "output.log").open("w+")
        self.addCleanup(log.close)
        process = subprocess.Popen(["dbus-run-session", "--", QS, "--no-color", "-p", str(path)],
                                   env=self.environment, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        self.processes.append(process)
        self.until(lambda: self.ipc(path, "state", check=False).returncode == 0)
        return process

    def stop_all(self):
        for process in self.processes:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        for process in self.processes:
            process.wait(timeout=5)

    def ipc(self, path, method, check=True):
        return subprocess.run([QS, "ipc", "-p", str(path), "call", "test", method],
                              env=self.environment, capture_output=True, text=True, timeout=3, check=check)

    def state(self):
        return json.loads(self.ipc(self.renderer, "state").stdout)

    def events(self):
        return json.loads(self.ipc(self.controller, "state").stdout)

    def until(self, predicate):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.02)
        logs = "\n".join(path.read_text() for path in self.root.rglob("output.log"))
        self.fail("Session condition timed out:\n" + logs)

    def test_import_reads_settings_but_never_claims_ready(self):
        self.start(self.renderer)
        self.assertEqual(self.events(), [])
        state = self.state()
        self.assertTrue(state["managed"])
        self.assertEqual(state["settings"], {"orbit_seconds": 42})
        self.assertEqual(state["config"]["idle"], {"lock_seconds": 300})
        self.assertFalse(state["readyRequested"])
        self.assertFalse(state["busy"])

    def test_ready_and_dismiss_are_serialized_idempotent_and_preserve_token(self):
        self.start(self.renderer)
        self.ipc(self.renderer, "both")
        self.until(lambda: not self.state()["busy"])
        self.assertEqual(self.events(), [{"method": "ready", "token": self.token},
                                        {"method": "dismiss", "token": self.token}])
        self.assertEqual(self.state()["error"], "")
        self.ipc(self.renderer, "both")
        self.assertEqual(len(self.events()), 2)

    def test_wake_before_ready_never_sends_late_ready(self):
        self.start(self.renderer)
        self.ipc(self.renderer, "dismiss")
        self.ipc(self.renderer, "ready")
        self.until(lambda: not self.state()["busy"])
        self.assertEqual(self.events(), [{"method": "dismiss", "token": self.token}])

    def test_unmanaged_preview_has_no_controller_side_effects(self):
        self.environment["LUNA_SCREENSAVER_TOKEN"] = ""
        self.start(self.renderer)
        self.ipc(self.renderer, "both")
        self.assertFalse(self.state()["managed"])
        self.assertFalse(self.state()["busy"])
        self.assertEqual(self.events(), [])

    def test_ready_timeout_releases_dismiss_and_kills_late_sender(self):
        # Delay only the transport, never the real controller or an interactive desktop.
        shim = self.root / "bin/qs"
        shim.write_text("#!/usr/bin/python3\nimport os, sys, time\n"
                        "if 'ready' in sys.argv: time.sleep(0.4)\n"
                        f"os.execv({QS!r}, [{QS!r}] + sys.argv[1:])\n")
        shim.chmod(0o755)
        self.environment["PATH"] = str(shim.parent) + os.pathsep + os.environ.get("PATH", "")
        self.start(self.renderer)
        self.ipc(self.renderer, "both")
        self.until(lambda: not self.state()["busy"])
        self.assertEqual(self.events(), [{"method": "dismiss", "token": self.token}])
        time.sleep(0.5)
        self.assertEqual(len(self.events()), 1)


if __name__ == "__main__":
    unittest.main()
