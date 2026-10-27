"""Run the real idle controller with private sensors and recording-only children."""

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


ROOT = Path(__file__).resolve().parents[5]
QS = shutil.which("qs")


@unittest.skipUnless(QS and shutil.which("dbus-run-session"), "Quickshell and D-Bus required")
class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna-saver-controller '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.shell = self.root / "src/screensaver/src/shell"
        self.shell.mkdir(parents=True)
        self.tools = self.root / "bin"
        self.tools.mkdir()
        self.config = {"idle": {"screensaver_seconds": 300, "lock_seconds": 600,
                                "display_off_seconds": 900},
                       "renderer": {"shell": ""}, "settings": {}}
        self.theme = {"fonts": {"ui": "Outfit", "mono": "Iosevka"}}

        # Keep production IPC, policy, process management and timers. Only native
        # compositor sensors are substituted; no real display or locker is reached.
        source = (ROOT / "src/screensaver/src/shell/controller.qml").read_text()
        source = source.replace("import Quickshell.Wayland\n", "")
        source = source.replace("import Quickshell.Hyprland\n", "")
        source = source.replace("IdleMonitor {", "FakeIdleMonitor {")
        source = source.replace("Hyprland.", "fakeHyprland.")
        source = source.rsplit("}", 1)[0] + '''
    property QtObject fakeHyprland: QtObject {
        property var focusedMonitor: ({name: "DP-1"})
        property var monitors: [
            {name: "DP-1", lastIpcObject: {dpmsStatus: true}},
            {name: "DP-2", lastIpcObject: {dpmsStatus: false}},
            {name: "HDMI-A-1", lastIpcObject: {dpmsStatus: true}}
        ]
    }
    IpcHandler {
        target: "test"
        function state(): string {
            return JSON.stringify({state: controller.state(), config: controller.config,
                pending: controller.pendingAction, checking: lockCheck.running,
                locking: controller.lockPending, settled: controller.rendererSettled,
                token: controller.rendererToken, rendererPid: renderer.processId,
                saverEnabled: saverIdle.enabled, lockEnabled: lockIdle.enabled,
                displayEnabled: displayIdle.enabled, powerBusy: controller.powerBusy,
                powerQueryBusy: controller.powerQueryBusy});
        }
        function idle(action: string, value: bool): void {
            if (action === "auto") saverIdle.isIdle = value;
            else if (action === "lock") lockIdle.isIdle = value;
            else displayIdle.isIdle = value;
        }
    }
}
'''
        (self.shell / "controller.qml").write_text(source)
        (self.shell / "FakeIdleMonitor.qml").write_text('''import QtQuick
QtObject {
    property bool enabled: false
    property bool isIdle: false
    property real timeout: 0
    property bool respectInhibitors: false
    onEnabledChanged: if (!enabled) isIdle = false
}
''')

        mock = textwrap.dedent('''\
            #!/usr/bin/python3
            import json, os, pathlib, signal, subprocess, sys, time
            root = pathlib.Path(os.environ["LUNA_CONTROLLER_TEST"])
            name = pathlib.Path(sys.argv[0]).name
            record = {"tool": name, "args": sys.argv[1:], "pid": os.getpid()}
            if name == "qs":
                record["token"] = os.environ["LUNA_SCREENSAVER_TOKEN"]
                record["config"] = json.loads(os.environ["LUNA_SCREENSAVER_SETTINGS"])
                record["theme"] = json.loads(os.environ["LUNA_UI_THEME"])
            with (root / "commands").open("a") as log:
                log.write(json.dumps(record) + "\\n")
            if name == "hyprctl":
                if sys.argv[1] == "eval":
                    hold = "hold-power"
                else:
                    hold = "hold-check"
                deadline = time.monotonic() + 5
                while (root / hold).exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                if (root / "fail-check").exists(): sys.exit(1)
                if sys.argv[-1] == "monitors":
                    if (root / "monitors").exists(): print((root / "monitors").read_text())
                    else: print(json.dumps([
                        {"name": "DP-1", "dpmsStatus": True}, {"name": "DP-2", "dpmsStatus": False},
                        {"name": "HDMI-A-1", "dpmsStatus": True}]))
                else: print(json.dumps({"locked": (root / "locked").exists()}))
            elif name == "luna":
                if not (root / "fail-lock").exists(): (root / "locked").touch()
                while (root / "hold-locker").exists(): time.sleep(0.01)
            elif name == "qs":
                options = json.loads((root / "renderer-options").read_text())
                if options.get("crash"): sys.exit(3)
                if options.get("ignore_term"): signal.signal(signal.SIGTERM, signal.SIG_IGN)
                if not options.get("no_ready"):
                    subprocess.run([os.environ["LUNA_REAL_QS"], "ipc", "-p",
                        os.environ["LUNA_SCREENSAVER_CONTROLLER"], "call", "renderer", "ready",
                        os.environ["LUNA_SCREENSAVER_TOKEN"]], check=True, capture_output=True)
                while not (root / "crash-renderer").exists(): time.sleep(0.02)
                sys.exit(3)
        ''')
        for name in ("hyprctl", "luna", "qs", "notify-send"):
            path = self.tools / name
            path.write_text(mock)
            path.chmod(0o755)
        self.options()

        runtime = self.root / "runtime"
        runtime.mkdir(mode=0o700)
        self.environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", QS_NO_RELOAD_POPUP="1",
            HOME=str(self.root), XDG_RUNTIME_DIR=str(runtime), XDG_CONFIG_HOME=str(self.root / "config"),
            XDG_CACHE_HOME=str(self.root / "cache"), XDG_DATA_HOME=str(self.root / "data"),
            LUNA_CONTROLLER_TEST=str(self.root), LUNA_REAL_QS=QS,
            LUNA_SCREENSAVER_SETTINGS=json.dumps(self.config), LUNA_UI_THEME=json.dumps(self.theme),
            WAYLAND_DISPLAY="luna-controller-test",
            PATH=str(self.tools) + ":" + os.environ["PATH"],
            DBUS_SYSTEM_BUS_ADDRESS="unix:path=/nonexistent-luna-test-system-bus")
        for key in ("DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE", "DBUS_SESSION_BUS_ADDRESS"):
            self.environment.pop(key, None)
        self.log = (self.root / "shell.log").open("w+")
        self.addCleanup(self.log.close)
        self.process = subprocess.Popen(["dbus-run-session", "--", QS, "-p", str(self.shell / "controller.qml")],
            env=self.environment, stdout=self.log, stderr=subprocess.STDOUT, start_new_session=True)
        self.addCleanup(self.stop)
        self.until(lambda: self.ipc("ping", check=False).returncode == 0)

    def stop(self):
        for item in self.calls("luna"):
            try:
                os.kill(item["pid"], signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        self.process.wait(timeout=5)

    def ipc(self, method, *arguments, target="screensaver", check=True):
        values = [str(value).lower() if isinstance(value, bool) else str(value) for value in arguments]
        return subprocess.run([QS, "ipc", "-p", str(self.shell / "controller.qml"), "call", "--", target, method, *values],
            env=self.environment, text=True, capture_output=True, timeout=3, check=check)

    def state(self):
        return json.loads(self.ipc("state", target="test").stdout)

    def idle(self, action, value=True):
        self.ipc("idle", action, value, target="test")

    def options(self, **values):
        (self.root / "renderer-options").write_text(json.dumps(values))

    def configure(self):
        self.ipc("configure", json.dumps({"config": self.config, "theme": self.theme}))

    def calls(self, name):
        path = self.root / "commands"
        values = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        return [value for value in values if value["tool"] == name]

    def until(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            if self.process.poll() is not None:
                break
            time.sleep(0.02)
        self.fail("Controller condition failed: " + (self.root / "shell.log").read_text())

    def show(self):
        self.ipc("show")
        self.until(lambda: self.state()["state"]["rendererState"] == "ready")

    def test_start_is_hidden_without_renderer_or_compositor_commands(self):
        self.assertEqual(self.ipc("status").stdout.strip(), "idle")
        self.assertEqual(self.calls("qs"), [])
        self.assertEqual(self.calls("hyprctl"), [])

    def test_applied_renderer_path_is_readable_without_starting_renderer(self):
        self.assertEqual(self.ipc("getRendererShell").stdout.strip(), str(self.shell / "shell.qml"))
        self.config["renderer"]["shell"] = "~/custom/shell.qml"
        self.configure()
        self.assertEqual(self.ipc("getRendererShell").stdout.strip(), str(self.root / "custom/shell.qml"))
        self.config["renderer"]["shell"] = "/another/shell.qml"
        self.assertEqual(self.ipc("getRendererShell").stdout.strip(), str(self.root / "custom/shell.qml"))
        self.configure()
        self.assertEqual(self.ipc("getRendererShell").stdout.strip(), "/another/shell.qml")
        self.assertFalse(self.calls("qs"))

    def test_stay_awake_preserves_independent_timers_and_cancels_queued_work(self):
        for saver, lock, display in ((300, 600, 900), (0, 900, 0), (120, 0, 300), (0, 0, 0)):
            with self.subTest(saver=saver, lock=lock, display=display):
                self.config["idle"] = {"screensaver_seconds": saver, "lock_seconds": lock,
                                       "display_off_seconds": display}
                self.configure()
                self.ipc("setStayAwake", True)
                state = self.state()
                self.assertEqual([state[key] for key in ("saverEnabled", "lockEnabled", "displayEnabled")],
                                 [False, False, False])
                self.assertEqual(state["config"], self.config)
                self.ipc("setStayAwake", False)
                state = self.state()
                self.assertEqual([state[key] for key in ("saverEnabled", "lockEnabled", "displayEnabled")],
                                 [saver > 0, lock > 0, display > 0])

        for action in ("auto", "lock"):
            hold = self.root / "hold-check"
            hold.touch()
            self.idle(action)
            self.until(lambda: self.state()["checking"])
            self.ipc("setStayAwake", True)
            hold.unlink()
            self.until(lambda: not self.state()["checking"])
            self.assertFalse(self.state()["state"]["active"])
            self.assertEqual(self.calls("luna"), [])
            self.ipc("setStayAwake", False)

    def test_stale_idle_events_cannot_override_awake_but_manual_show_works(self):
        self.ipc("setStayAwake", True)
        for action in ("auto", "lock", "display"):
            self.idle(action)
        self.assertEqual(self.calls("hyprctl"), [])
        self.show()
        self.assertTrue(self.state()["state"]["stayAwake"])
        self.ipc("hide")
        self.until(lambda: self.state()["settled"])

    def test_atomic_toggle_and_config_reload_preserve_awake(self):
        self.assertTrue(json.loads(self.ipc("toggleStayAwake").stdout)["stayAwake"])
        self.config["idle"]["lock_seconds"] = 1234
        self.configure()
        self.assertTrue(self.state()["state"]["stayAwake"])
        self.assertEqual(self.state()["config"]["idle"]["lock_seconds"], 1234)
        self.assertFalse(json.loads(self.ipc("toggleStayAwake").stdout)["stayAwake"])

    def test_renderer_receives_custom_shell_settings_and_shared_theme(self):
        self.config["renderer"]["shell"] = "~/custom shell's clock.qml"
        self.config["settings"] = {"title": "My clock", "values": [False, 0]}
        self.configure()
        self.show()
        call = self.calls("qs")[0]
        self.assertEqual(call["args"], ["-p", str(self.root / "custom shell's clock.qml")])
        self.assertEqual(call["config"], self.config)
        self.assertEqual(call["theme"], self.theme)

    def test_late_renderer_callbacks_cannot_dismiss_new_activation(self):
        self.show()
        old_token = self.state()["token"]
        self.ipc("hide")
        self.until(lambda: self.state()["settled"])
        self.show()
        new_token = self.state()["token"]
        self.assertNotEqual(old_token, new_token)
        self.ipc("dismiss", old_token, target="renderer")
        self.ipc("ready", old_token, target="renderer")
        self.assertTrue(self.state()["state"]["active"])
        self.ipc("dismiss", new_token, target="renderer")
        self.until(lambda: self.state()["settled"])
        self.assertFalse(self.state()["state"]["active"])

    def test_renderer_crash_keeps_idle_policy_alive_and_can_retry(self):
        self.show()
        (self.root / "crash-renderer").touch()
        self.until(lambda: self.state()["state"]["rendererState"] == "error")
        self.assertTrue(self.state()["lockEnabled"])
        self.assertEqual(self.ipc("ping").stdout.strip(), "ready")
        self.idle("lock")
        self.until(lambda: len(self.calls("luna")) == 1)
        self.until(lambda: not self.state()["locking"])

    def test_reload_clears_inactive_renderer_failure_consistently(self):
        self.options(crash=True)
        self.ipc("show")
        self.until(lambda: self.state()["state"]["rendererState"] == "error")
        self.options()
        self.configure()
        self.assertEqual(self.ipc("status").stdout.strip(), "idle")
        self.assertEqual(self.state()["state"]["rendererState"], "hidden")
        self.assertEqual(self.state()["state"]["error"], "")
        self.show()

    def test_reload_replaces_only_renderer_and_preserves_awake(self):
        self.ipc("setStayAwake", True)
        self.show()
        first = self.calls("qs")[0]["pid"]
        self.config["settings"] = {"label": "changed"}
        self.configure()
        self.until(lambda: len(self.calls("qs")) == 2 and self.state()["state"]["rendererState"] == "ready")
        self.assertNotEqual(first, self.calls("qs")[-1]["pid"])
        self.assertTrue(self.state()["state"]["stayAwake"])
        self.assertEqual(self.calls("qs")[-1]["config"]["settings"], {"label": "changed"})

    def test_font_update_replaces_renderer_without_resetting_policy(self):
        self.show()
        self.ipc("applyFonts", json.dumps({"ui": "Changed", "mono": "Mono"}))
        self.until(lambda: len(self.calls("qs")) == 2 and self.state()["state"]["rendererState"] == "ready")
        self.assertEqual(self.calls("qs")[-1]["theme"]["fonts"]["ui"], "Changed")
        self.assertTrue(self.state()["lockEnabled"])

    def test_unresponsive_renderer_is_killed_after_dismissal(self):
        self.options(ignore_term=True)
        self.show()
        self.ipc("hide")
        self.until(lambda: self.state()["settled"])
        self.assertEqual(self.ipc("status").stdout.strip(), "idle")

    def test_missing_readiness_reports_error_without_disabling_timers(self):
        self.options(no_ready=True)
        self.ipc("show")
        self.until(lambda: self.state()["state"]["rendererState"] == "error", timeout=7)
        self.assertIn("ready", self.state()["state"]["error"])
        self.assertTrue(self.state()["lockEnabled"])

    def test_locked_session_never_starts_a_renderer(self):
        (self.root / "locked").touch()
        self.ipc("show")
        self.until(lambda: len(self.calls("hyprctl")) > 0 and not self.state()["checking"])
        self.assertFalse(self.state()["state"]["active"])
        self.assertEqual(self.calls("qs"), [])

    def test_stop_does_not_terminate_an_active_locker(self):
        (self.root / "hold-locker").touch()
        self.idle("lock")
        self.until(lambda: len(self.calls("luna")) == 1)
        self.until(lambda: not self.state()["locking"])
        locker = self.calls("luna")[0]["pid"]
        self.ipc("shutdown")
        self.process.wait(timeout=4)
        os.kill(locker, 0)

    def test_display_resume_restores_only_outputs_luna_turned_off(self):
        self.idle("display")
        self.until(lambda: self.state()["state"]["outputsOff"])
        off = self.calls("hyprctl")[-1]["args"][-1]
        self.assertIn('action="off"', off)
        self.assertIn('monitor="DP-1"', off)
        self.assertIn('monitor="HDMI-A-1"', off)
        self.assertNotIn('monitor="DP-2"', off)
        # A later screensaver timer cannot wake a screen that already powered off.
        self.idle("auto")
        self.assertEqual(self.calls("qs"), [])
        self.idle("display", False)
        self.until(lambda: not self.state()["state"]["outputsOff"])
        on = self.calls("hyprctl")[-1]["args"][-1]
        self.assertIn('action="on"', on)
        self.assertNotIn('monitor="DP-2"', on)

    def test_awake_during_inflight_power_off_queues_restoration(self):
        hold = self.root / "hold-power"
        hold.touch()
        self.idle("display")
        self.until(lambda: self.state()["powerBusy"])
        self.ipc("setStayAwake", True)
        hold.unlink()
        self.until(lambda: len(self.calls("hyprctl")) == 3 and not self.state()["powerBusy"])
        self.assertFalse(self.state()["state"]["outputsOff"])
        self.assertIn('action="on"', self.calls("hyprctl")[-1]["args"][-1])

    def test_display_power_reads_current_state_before_taking_ownership(self):
        (self.root / "monitors").write_text(json.dumps([
            {"name": "DP-1", "dpmsStatus": False}, {"name": "HDMI-A-1", "dpmsStatus": True}]))
        self.idle("display")
        self.until(lambda: self.state()["state"]["outputsOff"])
        off = self.calls("hyprctl")[-1]["args"][-1]
        self.assertIn('monitor="HDMI-A-1"', off)
        self.assertNotIn('monitor="DP-1"', off)
        self.ipc("setStayAwake", True)
        self.until(lambda: not self.state()["state"]["outputsOff"])
        self.assertNotIn('monitor="DP-1"', self.calls("hyprctl")[-1]["args"][-1])

    def test_resume_during_monitor_query_never_powers_off(self):
        hold = self.root / "hold-check"
        hold.touch()
        self.idle("display")
        self.until(lambda: self.state()["powerQueryBusy"])
        self.idle("display", False)
        hold.unlink()
        self.until(lambda: not self.state()["powerQueryBusy"])
        self.assertFalse(self.state()["state"]["outputsOff"])
        self.assertFalse(any(call["args"][0] == "eval" for call in self.calls("hyprctl")))

    def test_shutdown_restores_power_before_exiting(self):
        self.idle("display")
        self.until(lambda: self.state()["state"]["outputsOff"])
        self.ipc("shutdown")
        self.process.wait(timeout=4)
        self.assertIn('action="on"', self.calls("hyprctl")[-1]["args"][-1])

    def test_lua_runtime_uses_real_controller_ipc_for_show_reload_and_stop(self):
        # The CLI transport must traverse qs's actual argument parser. In
        # particular, an unescaped function named "show" selects qs ipc show.
        environment = dict(self.environment, PATH=os.environ["PATH"], LUNA_SCREENSAVER_CONFIG="")
        result = subprocess.run(["/usr/bin/lua", "-E", "-", str(ROOT), str(self.shell / "controller.qml")],
            input='''
local common = dofile(arg[1] .. "/lib/common.lua")
local runtime = dofile(arg[1] .. "/src/screensaver/src/runtime.lua")(common, arg[1], arg[2])
assert(runtime.status() == "idle")
runtime.show()
assert(runtime.status() == "showing")
assert(runtime.setStayAwake(true).stayAwake)
runtime.show()
runtime.reload()
assert(runtime.getState().stayAwake)
assert(runtime.status() == "showing")
runtime.hide()
assert(runtime.status() == "idle")
runtime.stop()
assert(runtime.status() == "stopped")
''', env=environment, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr + (self.root / "shell.log").read_text())
        self.assertEqual(result.stdout, "", "The public runtime leaves output to its caller")
        self.process.wait(timeout=4)


if __name__ == "__main__":
    unittest.main()
