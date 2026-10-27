"""Exercise the Stay awake widget through the real QML client and a private bridge."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import unittest


REPO = Path(__file__).resolve().parents[4]


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
        client = self.root / "src/screensaver/src/shell"
        client.mkdir(parents=True)
        shutil.copy(REPO / "src/screensaver/src/shell/Screensaver.qml", client)
        (module / "qmldir").write_text("module Luna\nsingleton StayAwake 1.0 StayAwake.qml\n"
                                       "singleton Screensaver 1.0 ../../screensaver/src/shell/Screensaver.qml\n")
        (self.root / "shell.qml").write_text('''import QtQuick
import Quickshell
import Quickshell.Io
import Luna as Luna
ShellRoot {
    Component.onCompleted: Quickshell.watchFiles = false
    IpcHandler {
        target: "test"
        function state(): string {
            return JSON.stringify({enabled: Luna.StayAwake.enabled, ready: Luna.StayAwake.ready,
                busy: Luna.StayAwake.busy, apiBusy: Luna.Screensaver.busy, error: Luna.StayAwake.error});
        }
        function run(actions: string): void {
            for (const action of actions.split(",")) {
                if (action === "toggle") Luna.StayAwake.toggle();
                else if (action === "external-status") Luna.Screensaver.getState();
                else if (action === "external-toggle") Luna.Screensaver.toggleStayAwake();
                else Luna.StayAwake.refresh();
            }
        }
    }
}
''')
        # The actual QML client locates this neighboring bridge. It records calls
        # and never imports the production Lua runtime or contacts a live session.
        self.bridge = client.parent / "bridge.lua"
        self.bridge.write_text('''local json = dofile(os.getenv("TEST_REPO") .. "/lib/json.lua")
local root = os.getenv("LUNA_AWAKE_UI_TEST_ROOT")
local function read(path)
    local file = assert(io.open(root .. "/" .. path, "r"))
    local value = file:read("*a")
    file:close()
    return value
end
local function write(path, value, mode)
    local file = assert(io.open(root .. "/" .. path, mode or "w"))
    file:write(value)
    file:close()
end
local options = json.decode(read("options"))
local request = json.decode(arg[1])
write("calls", json.encode(request) .. "\\n", "a")
if options.delay then os.execute("sleep " .. tostring(tonumber(options.delay))) end
if options.output then
    print(options.output)
elseif (options.exit or 0) == 0 then
    local enabled = read("enabled") == "true"
    if request.method == "toggleStayAwake" then
        enabled = not enabled
        write("enabled", tostring(enabled))
    end
    print(json.encode({ok = true, configPath = root .. "/config.toml", result = {
        running = true, active = false, stayAwake = enabled, outputsOff = false,
        rendererState = "hidden", error = ""}}))
end
if options.error then io.stderr:write(options.error, "\\n") end
os.exit(options.exit or 0)
''')
        (self.root / "enabled").write_text("false")
        self.options()

        runtime = self.root / "runtime"
        runtime.mkdir(mode=0o700)
        self.environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", XDG_RUNTIME_DIR=str(runtime),
                                QML_IMPORT_PATH=str(self.root / "src/qml"), QS_NO_RELOAD_POPUP="1",
                                LUNA_AWAKE_UI_TEST_ROOT=str(self.root), TEST_REPO=str(REPO),
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
        return [json.loads(line)["method"] for line in path.read_text().splitlines()] if path.exists() else []

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
        self.until(lambda: not self.state()["busy"] and not self.state()["apiBusy"])
        return self.state()

    def test_requests_serialize_and_external_state_refreshes(self):
        self.assertFalse(self.state()["ready"])
        self.run_action("toggle")
        self.assertEqual(self.calls(), [])
        self.options(delay=0.2)
        self.ipc("run", "status,status,toggle")
        self.assertTrue(self.state()["busy"])
        self.until(lambda: not self.state()["busy"])
        self.assertTrue(self.state()["ready"])
        self.assertEqual(self.calls(), ["getState"])
        self.ipc("run", "toggle,toggle,status")
        self.assertTrue(self.state()["busy"])
        self.assertFalse(self.state()["enabled"])
        self.until(lambda: not self.state()["busy"])
        self.assertTrue(self.state()["enabled"])
        self.assertEqual(self.calls(), ["getState", "toggleStayAwake"])
        (self.root / "enabled").write_text("false")
        self.assertFalse(self.run_action("status")["enabled"])

    def test_invalid_status_preserves_state_and_prevents_toggling(self):
        (self.root / "enabled").write_text("true")
        self.assertTrue(self.run_action("status")["enabled"])
        for output in ("not json", '{"ok":true,"result":{"stayAwake":"false"},"configPath":"/tmp/x"}', "null", "{}"):
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
        # A nonzero bridge result cannot apply an otherwise valid state payload.
        reply = {"ok": True, "configPath": "/tmp/config.toml", "result": {
            "running": True, "active": False, "stayAwake": True, "outputsOff": False,
            "rendererState": "hidden", "error": ""}}
        self.options(exit=1, output=json.dumps(reply), error="Session unavailable")
        state = self.run_action("toggle")
        self.assertFalse(state["enabled"])
        self.assertTrue(state["ready"])
        self.assertEqual(state["error"], "Session unavailable")
        self.options()
        self.assertEqual(self.run_action("status")["error"], "Session unavailable")
        state = self.run_action("toggle")
        self.assertTrue(state["enabled"])
        self.assertEqual(state["error"], "")

    def test_missing_bridge_reports_failure_and_allows_retry(self):
        saved = self.bridge.with_name("bridge-saved.lua")
        self.bridge.rename(saved)
        state = self.run_action("status")
        self.assertFalse(state["ready"])
        self.assertFalse(state["busy"])
        self.assertIn("status", state["error"])
        saved.rename(self.bridge)
        state = self.run_action("status")
        self.assertTrue(state["ready"])
        self.assertEqual(state["error"], "")

    def test_other_consumers_requests_do_not_update_widget_or_absorb_its_reply(self):
        self.options(delay=0.15)
        self.run_action("external-status,status")
        self.assertFalse(self.state()["ready"])
        self.assertEqual(self.calls(), ["getState"])
        self.run_action("status,external-toggle")
        self.assertTrue(self.state()["ready"])
        self.assertFalse(self.state()["enabled"])
        self.assertEqual((self.root / "enabled").read_text(), "true")
        self.assertTrue(self.run_action("status")["enabled"])


if __name__ == "__main__":
    unittest.main()
