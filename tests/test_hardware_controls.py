"""Run hardware controls offscreen with fake devices and silent command replacements."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import time
import unittest


REPO = Path(__file__).resolve().parents[1]


@unittest.skipUnless(all(shutil.which(tool) for tool in ("qs", "lua", "dbus-run-session")),
                     "Quickshell, Lua and dbus-run-session required")
class HardwareControlsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna-hardware-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        module = self.root / "bar"
        module.mkdir()
        for name in ("Desktop.qml", "Status.js", "HardwareControls.qml", "BatteryAlerts.qml"):
            (module / name).symlink_to(REPO / "src/luna-bar" / name)
        # Offscreen Qt cannot construct layer-shell windows; exercise their controller without a surface.
        (module / "HardwareOsd.qml").write_text("import QtQuick\nQtObject { property var screen; "
            "property string icon; property real level; property bool muted; property string error }\n")
        (module / "qmldir").write_text("singleton Desktop 1.0 Desktop.qml\n"
            "HardwareControls 1.0 HardwareControls.qml\nHardwareOsd 1.0 HardwareOsd.qml\n"
            "BatteryAlerts 1.0 BatteryAlerts.qml\n")
        (self.root / "shell.qml").write_text('''import QtQuick
import Quickshell
import Quickshell.Io
import "bar" as Bar
ShellRoot {
    QtObject {
        id: fake
        property bool audioAvailable: true
        property real volume: 0.5
        property bool muted: false
        property bool microphoneAvailable: true
        property bool microphoneMuted: false
        property real microphoneVolume: 0.7
        property bool brightnessAvailable: true
        property int brightness: 50
        property int requestedBrightness: 50
        property bool brightnessPending: false
        property bool hasBattery: false
        property var battery: ({percentage: 1, state: 2})
        signal brightnessFinished(bool success, string message)
        function setVolume(value) { volume = Math.max(0, Math.min(1, value)); }
        function toggleMute() { muted = !muted; }
        function toggleMicrophoneMute() { microphoneMuted = !microphoneMuted; }
        function adjustBrightness(change) {
            requestedBrightness = Math.max(1, Math.min(100, (brightnessPending ? requestedBrightness : brightness) + change));
            brightnessPending = true;
        }
    }
    Bar.HardwareControls { id: controls; backend: fake; screen: null }
    Bar.BatteryAlerts { backend: fake }
    IpcHandler {
        target: "test"
        function run(action: string): bool { return controls.run(action); }
        function repeat(action: string, count: int): void { for (let i = 0; i < count; i++) controls.run(action); }
        function state(): string { return JSON.stringify({osd:JSON.parse(controls.status()), volume:fake.volume,
            muted:fake.muted, microphoneMuted:fake.microphoneMuted, brightness:fake.brightness,
            requested:fake.requestedBrightness, pending:fake.brightnessPending}); }
        function availability(audio: bool, microphone: bool, brightness: bool): void {
            fake.audioAvailable = audio; fake.microphoneAvailable = microphone; fake.brightnessAvailable = brightness;
        }
        function finishBrightness(success: bool): void {
            if (success) fake.brightness = fake.requestedBrightness;
            else fake.requestedBrightness = fake.brightness;
            fake.brightnessPending = false;
            fake.brightnessFinished(success, success ? "" : "Permission denied");
        }
        function battery(percentage: real, state: int, present: bool): void {
            fake.battery = {percentage:percentage, state:state}; fake.hasBattery = present;
        }
        function nativeBrightness(): string { return JSON.stringify({available:Bar.Desktop.brightnessAvailable,
            value:Bar.Desktop.brightness, requested:Bar.Desktop.requestedBrightness,
            pending:Bar.Desktop.brightnessPending, error:Bar.Desktop.error}); }
        function nativeStep(change: int, count: int): void { for (let i = 0; i < count; i++) Bar.Desktop.adjustBrightness(change); }
    }
}
''')
        runtime = self.root / "runtime"
        runtime.mkdir(mode=0o700)
        tools = self.root / "tools"
        tools.mkdir()
        self.options()
        (self.root / "brightness").write_text("50")
        command = textwrap.dedent('''\
            #!/usr/bin/python3
            import fcntl, json, os, sys, time
            from pathlib import Path
            root = Path(os.environ["LUNA_HARDWARE_TEST_ROOT"])
            tool = Path(sys.argv[0]).name
            options = json.loads((root / "options").read_text())
            def record(event):
                with (root / "calls").open("a") as log:
                    log.write(json.dumps({"tool":tool, "event":event, "args":sys.argv[1:],
                        "injected":[key for key in ("LD_LIBRARY_PATH", "LD_PRELOAD") if key in os.environ]}) + "\\n")
            if tool == "notify-send":
                record("notify")
                time.sleep(options["notify_delay"])
                sys.exit(0)
            if "set" in sys.argv:
                lock = (root / "brightness.lock").open("w")
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    record("overlap")
                    sys.exit(1)
                record("write")
                time.sleep(options["brightness_delay"])
                if options["brightness_failure"]:
                    print("Permission denied", file=sys.stderr)
                    sys.exit(1)
                value = int(sys.argv[-1][:-1])
                (root / "brightness").write_text(str(value))
            else:
                record("read")
                value = int((root / "brightness").read_text())
            print(f"test,backlight,{value},{value}%,100")
        ''')
        for name in ("notify-send", "brightnessctl"):
            path = tools / name
            path.write_text(command)
            path.chmod(0o755)
        theme = subprocess.run(["lua", "-E", "-", str(REPO)], input='''local root = arg[1]
local resolved = dofile(root .. "/lib/theme/resolved.lua")(root)
local validate = dofile(root .. "/lib/theme/validate.lua")()
print(resolved.encode(resolved.resolve(validate.load(root .. "/themes/bundled/tokyo-night"), "tokyo-night")))
''', capture_output=True, text=True, check=True).stdout.strip()
        self.environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", XDG_RUNTIME_DIR=str(runtime),
                                QS_NO_RELOAD_POPUP="1", PATH=str(tools) + ":" + os.environ["PATH"],
                                QML_IMPORT_PATH=str(REPO / "src/qml"), LUNA_UI_THEME=theme,
                                LUNA_HARDWARE_TEST_ROOT=str(self.root), LD_LIBRARY_PATH=str(self.root / "libraries"),
                                LD_PRELOAD="")
        self.environment.pop("WAYLAND_DISPLAY", None)
        self.log = (self.root / "shell.log").open("w+")
        self.addCleanup(self.log.close)
        self.process = subprocess.Popen(["dbus-run-session", "--", "qs", "-p", str(self.root)],
                                        env=self.environment, stdout=self.log, stderr=subprocess.STDOUT,
                                        start_new_session=True)
        self.addCleanup(self.stop)
        self.until(lambda: self.ipc("state", check=False).stdout.startswith('{"osd":'))

    def stop(self):
        import signal
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        self.process.wait(timeout=5)

    def options(self, brightness_delay=0.05, brightness_failure=False, notify_delay=0.01):
        (self.root / "options").write_text(json.dumps({"brightness_delay":brightness_delay,
            "brightness_failure":brightness_failure, "notify_delay":notify_delay}))

    def ipc(self, method, *arguments, check=True):
        arguments = [str(value).lower() if isinstance(value, bool) else str(value) for value in arguments]
        return subprocess.run(["qs", "ipc", "-p", str(self.root), "call", "test", method, *arguments],
                              env=self.environment, capture_output=True, text=True, timeout=3, check=check)

    def state(self):
        return json.loads(self.ipc("state").stdout)

    def native(self):
        return json.loads(self.ipc("nativeBrightness").stdout)

    def calls(self, event):
        path = self.root / "calls"
        entries = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        return [entry for entry in entries if entry["event"] == event]

    def until(self, predicate, timeout=4):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            if self.process.poll() is not None:
                break
            time.sleep(0.02)
        self.fail("Hardware condition failed: " + (self.root / "shell.log").read_text())

    def test_volume_steps_bounds_mute_and_microphone(self):
        self.ipc("run", "volume-up")
        self.assertEqual(self.state()["volume"], 0.55)
        self.ipc("repeat", "volume-up", 30)
        self.assertEqual(self.state()["volume"], 1)
        self.ipc("run", "volume-mute")
        self.assertTrue(self.state()["osd"]["muted"])
        self.ipc("run", "volume-down")
        self.assertFalse(self.state()["muted"])
        self.assertEqual(self.state()["volume"], 0.95)
        self.ipc("repeat", "volume-down", 30)
        self.assertEqual(self.state()["volume"], 0)
        self.ipc("run", "mic-mute")
        self.assertTrue(self.state()["microphoneMuted"])
        self.assertEqual(self.state()["osd"]["icon"], "mic-off")
        self.ipc("run", "mic-mute")
        self.assertFalse(self.state()["microphoneMuted"])
        self.assertEqual(self.calls("write"), [])
        self.assertEqual(self.calls("notify"), [])

    def test_osd_hides_and_missing_devices_return_clear_failures(self):
        self.ipc("availability", False, False, False)
        for action, message in (("volume-up", "No audio output"), ("mic-mute", "No microphone"),
                                ("brightness-up", "Brightness unavailable")):
            self.assertEqual(self.ipc("run", action).stdout.strip(), "false")
            self.assertEqual(self.state()["osd"]["error"], message)
        self.assertTrue(self.state()["osd"]["visible"])
        self.until(lambda: not self.state()["osd"]["visible"], timeout=2)
        self.assertEqual(self.ipc("run", "unsupported").stdout.strip(), "false")

    def test_brightness_repeats_accumulate_and_failure_rolls_osd_back(self):
        self.ipc("repeat", "brightness-up", 4)
        self.assertEqual(self.state()["requested"], 70)
        self.assertEqual(self.state()["osd"]["level"], 0.7)
        self.ipc("finishBrightness", False)
        self.assertEqual(self.state()["osd"]["level"], 0.5)
        self.assertEqual(self.state()["osd"]["error"], "Brightness change failed")
        self.ipc("repeat", "brightness-down", 30)
        self.assertEqual(self.state()["requested"], 1)
        self.ipc("finishBrightness", True)
        self.assertEqual(self.state()["osd"]["error"], "")

    def test_native_brightness_serializes_requests_while_a_write_is_running(self):
        self.options(brightness_delay=0.35)
        self.until(lambda: self.native()["available"])
        self.ipc("nativeStep", 5, 2)
        self.until(lambda: len(self.calls("write")) == 1)
        self.ipc("nativeStep", 5, 3)
        self.until(lambda: not self.native()["pending"])
        self.assertEqual(self.native()["value"], 75)
        self.assertEqual([entry["args"][-1] for entry in self.calls("write")], ["60%", "75%"])
        self.assertEqual(self.calls("overlap"), [])

    def test_native_brightness_failure_cancels_queued_repeats(self):
        self.options(brightness_delay=0.3, brightness_failure=True)
        self.until(lambda: self.native()["available"])
        self.ipc("nativeStep", 5, 1)
        self.until(lambda: len(self.calls("write")) == 1)
        self.ipc("nativeStep", 5, 5)
        self.until(lambda: not self.native()["pending"])
        self.assertEqual(self.native()["value"], 50)
        self.assertEqual(self.native()["requested"], 50)
        self.assertEqual(self.native()["error"], "Permission denied")
        time.sleep(0.3)
        self.assertEqual(len(self.calls("write")), 1)

    def test_battery_thresholds_fire_once_and_rearm_after_recovery_or_charge(self):
        self.ipc("battery", 0.15, 2, True)
        self.until(lambda: len(self.calls("notify")) == 1)
        first = self.calls("notify")[0]
        self.assertIn("--urgency=normal", first["args"])
        self.assertEqual(first["injected"], [])
        for percentage in (0.14, 0.16, 0.15):
            self.ipc("battery", percentage, 2, True)
            time.sleep(0.12)
        self.assertEqual(len(self.calls("notify")), 1)
        self.ipc("battery", 0.05, 2, True)
        self.until(lambda: len(self.calls("notify")) == 2)
        self.assertIn("--urgency=critical", self.calls("notify")[1]["args"])
        self.ipc("battery", 0.06, 2, True)
        time.sleep(0.12)
        self.ipc("battery", 0.05, 2, True)
        time.sleep(0.12)
        self.assertEqual(len(self.calls("notify")), 2)
        self.ipc("battery", 0.08, 2, True)
        time.sleep(0.12)
        self.ipc("battery", 0.05, 2, True)
        self.until(lambda: len(self.calls("notify")) == 3)
        self.ipc("battery", 0.04, 1, True)
        time.sleep(0.12)
        self.ipc("battery", 0.04, 2, True)
        self.until(lambda: len(self.calls("notify")) == 4)
        self.ipc("battery", 0.20, 2, True)
        time.sleep(0.12)
        self.ipc("battery", 0.15, 2, True)
        self.until(lambda: len(self.calls("notify")) == 5)
        self.assertIn("--urgency=normal", self.calls("notify")[4]["args"])

    def test_battery_ignores_absent_unknown_or_charging_devices(self):
        for present, state in ((False, 2), (True, 0), (True, 1), (True, 4), (True, 5)):
            self.ipc("battery", 0.03, state, present)
            time.sleep(0.12)
        self.assertEqual(self.calls("notify"), [])
        self.ipc("battery", 0.03, 2, True)
        self.until(lambda: len(self.calls("notify")) == 1)
        self.assertIn("--urgency=critical", self.calls("notify")[0]["args"])

    def test_charging_cancels_a_queued_critical_alert(self):
        self.options(notify_delay=0.6)
        self.ipc("battery", 0.15, 2, True)
        self.until(lambda: len(self.calls("notify")) == 1)
        self.ipc("battery", 0.05, 2, True)
        time.sleep(0.12)
        self.ipc("battery", 0.05, 1, True)
        time.sleep(0.7)
        self.assertEqual(len(self.calls("notify")), 1)


if __name__ == "__main__":
    unittest.main()
