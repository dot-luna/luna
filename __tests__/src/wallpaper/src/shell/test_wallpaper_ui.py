"""Exercise the QML wallpaper API with a private bridge and no desktop renderer.

Run from the repository root:
    python3 -m unittest discover -s __tests__/src/wallpaper/src/shell -p test_wallpaper_ui.py -v
"""

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


REPO = Path(__file__).resolve().parents[5]


@unittest.skipUnless(shutil.which("qs") and shutil.which("dbus-run-session")
                     and Path("/usr/bin/lua").exists() and Path("/usr/bin/timeout").exists(),
                     "Quickshell, D-Bus, Lua and GNU timeout required")
class WallpaperUiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna wallpaper ' # % ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        module = self.root / "src/qml/Luna"
        module.mkdir(parents=True)
        client = self.root / "src/wallpaper/src/shell/Wallpaper.qml"
        client.parent.mkdir(parents=True)
        shutil.copy(REPO / "src/wallpaper/src/shell/Wallpaper.qml", client)
        # Only these private copies override startup/deadline conditions for failure tests.
        if self._testMethodName == "test_failed_process_start_releases_queue_and_allows_retry":
            self.process_wrapper = self.root / "timeout-wrapper"
            client.write_text(client.read_text().replace('command: ["/usr/bin/timeout",',
                                                        'command: [' + json.dumps(str(self.process_wrapper)) + ','))
        if self._testMethodName.startswith("test_timeout_"):
            client.write_text(client.read_text().replace('"90s"', '"0.1s"'))
        # Keep the real wallpaper registration without unrelated singleton dependencies.
        registration = (REPO / "src/qml/Luna/qmldir").read_text().splitlines()
        (module / "qmldir").write_text("\n".join(line for line in registration
                                                if line == "module Luna" or line.startswith("singleton Wallpaper ")) + "\n")
        (self.root / "shell.qml").write_text('''import QtQuick
import Quickshell
import Quickshell.Io
import Luna as Luna
ShellRoot {
    id: shell
    property var events: []
    property var chain: []
    function invoke(request) {
        switch (request.method) {
        case "getConfig": Luna.Wallpaper.getConfig(request.argument); break;
        case "updateConfig": Luna.Wallpaper.updateConfig(request.argument); break;
        case "getConfigFile": Luna.Wallpaper.getConfigFile(); break;
        case "reload": Luna.Wallpaper.reload(); break;
        case "status": Luna.Wallpaper.status(); break;
        case "start": Luna.Wallpaper.start(); break;
        case "stop": Luna.Wallpaper.stop(); break;
        case "restart": Luna.Wallpaper.restart(); break;
        }
    }
    Connections {
        target: Luna.Wallpaper
        function onCompleted(method, result) {
            shell.events = shell.events.concat([{method: method, result: result}]);
            if (shell.chain.length) {
                const next = shell.chain[0];
                shell.chain = shell.chain.slice(1);
                shell.invoke(next);
            }
        }
        function onFailed(method, message) {
            shell.events = shell.events.concat([{method: method, error: message}]);
        }
    }
    IpcHandler {
        target: "test"
        function state(): string {
            return JSON.stringify({busy: Luna.Wallpaper.busy, error: Luna.Wallpaper.error,
                config: Luna.Wallpaper.config,
                state: Luna.Wallpaper.state, configPath: Luna.Wallpaper.configPath,
                events: shell.events});
        }
        function run(requests: string): void {
            const parsed = JSON.parse(requests).items;
            for (let index = 0; index < parsed.length; index++) {
                const request = parsed[index];
                shell.invoke(request);
                if (request.mutate) request.argument.wallpaper.fit = "fill";
            }
        }
        function chain(requests: string): void {
            shell.chain = JSON.parse(requests).items;
        }
        function destroyRequest(): void {
            Luna.Wallpaper.activeRequest.destroy();
        }
    }
}
''')

        # Copy the codec only. Every API method below is fake and cannot launch wallpaper.
        codec = self.root / "lib/json.lua"
        codec.parent.mkdir(parents=True)
        shutil.copy(REPO / "lib/json.lua", codec)
        self.bridge = self.root / "src/wallpaper/src/bridge.lua"
        self.bridge.parent.mkdir(parents=True, exist_ok=True)
        self.bridge.write_text(textwrap.dedent('''\
            local root = os.getenv("LUNA_WALLPAPER_UI_TEST_ROOT")
            local json = dofile(root .. "/lib/json.lua")
            local function read(name)
                local handle = assert(io.open(root .. "/" .. name, "r"))
                local value = json.decode(handle:read("*a"))
                handle:close()
                return value
            end
            local request = json.decode(arg[1])
            local log = assert(io.open(root .. "/calls", "a"))
            log:write(arg[1], "\\n")
            log:close()
            local options = read("options")
            options = options.methods and options.methods[request.method] or options
            if options.delay then os.execute("sleep " .. tonumber(options.delay)) end
            if options.child then
                local pipe = assert(io.popen('/usr/bin/python3 -I "$LUNA_WALLPAPER_UI_TEST_ROOT/child.py"'))
                pipe:read("*a")
                pipe:close()
            end
            if options.output then
                print(options.output)
            else
                local result = json.null
                if request.method == "getConfig" then
                    result = { wallpaper = { source = "/saved.png", fit = "fill" },
                        playback = { pause_when_output_inactive = false }, transition = { duration_ms = 0 },
                        custom = { values = json.decode("[[],{}]") } }
                    if request.argument then
                        for key in request.argument:gmatch("[^.]+") do
                            if type(result) == "table" then result = result[key] else result = nil end
                        end
                        if result == nil then result = json.null end
                    end
                elseif request.method == "updateConfig" then
                    result = request.argument
                elseif request.method == "getConfigFile" then
                    result = root .. "/config/wallpaper.toml"
                elseif request.method == "status" then
                    result = "ready"
                end
                print(json.encode({ok = true, result = result,
                    configPath = root .. "/config/wallpaper.toml"}))
            end
            if options.error then io.stderr:write(options.error, "\\n") end
            os.exit(options.exit or 0)
        '''))
        self.options()

        # Use a separate home, runtime directory and D-Bus session; no live Wayland endpoint.
        runtime = self.root / "runtime"
        runtime.mkdir(mode=0o700)
        home = self.root / "home"
        home.mkdir()
        self.environment = dict(os.environ, HOME=str(home), QT_QPA_PLATFORM="offscreen",
                                XDG_RUNTIME_DIR=str(runtime), XDG_CONFIG_HOME=str(self.root / "config"),
                                XDG_CACHE_HOME=str(self.root / "cache"),
                                QML_IMPORT_PATH=str(self.root / "src/qml"), QS_NO_RELOAD_POPUP="1",
                                LUNA_WALLPAPER_UI_TEST_ROOT=str(self.root),
                                DBUS_SYSTEM_BUS_ADDRESS="unix:path=/nonexistent-luna-test-system-bus")
        # A user config must be outside the copied checkout, just as in an installation.
        personal = tempfile.TemporaryDirectory(prefix="luna-wallpaper-user-")
        self.addCleanup(personal.cleanup)
        self.user_config = Path(personal.name) / "wallpaper.toml"
        self.environment["LUNA_WALLPAPER_CONFIG"] = str(self.user_config)
        for name in ("WAYLAND_DISPLAY", "DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE", "DBUS_SESSION_BUS_ADDRESS",
                     "QML2_IMPORT_PATH"):
            self.environment.pop(name, None)
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
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if predicate():
                return
            if self.process.poll() is not None:
                break
            time.sleep(0.02)
        self.fail("Wallpaper API condition failed: " + (self.root / "shell.log").read_text())

    def submit(self, *requests):
        # Quickshell's argument parser treats a leading JSON array as an argument list.
        self.ipc("run", json.dumps({"items": list(requests)}))

    def run_action(self, method, argument=None):
        request = {"method": method}
        if argument is not None:
            request["argument"] = argument
        self.submit(request)
        self.until(lambda: not self.state()["busy"])
        return self.state()

    def test_import_is_idle_and_has_no_renderer_side_effects(self):
        self.assertEqual(self.state(), {"busy": False, "error": "", "config": None,
                                      "state": "unknown", "configPath": "", "events": []})
        self.assertEqual(self.calls(), [])

    def test_config_round_trip_and_source_arguments_are_preserved(self):
        state = self.run_action("getConfig")
        self.assertEqual(state["config"]["wallpaper"], {"source": "/saved.png", "fit": "fill"})
        self.assertEqual(state["configPath"], str(self.root / "config/wallpaper.toml"))
        changes = {"wallpaper": {"fit": "tile"}, "transition": {"duration_ms": 37}}
        self.assertEqual(self.run_action("updateConfig", changes)["config"], changes)
        source = '/tmp/雪 # % " \' $(touch should-not-exist); wallpaper.png'
        state = self.run_action("updateConfig", {"wallpaper": {"source": source}})
        self.assertEqual(state["config"]["wallpaper"]["source"], source)
        self.assertEqual(self.calls()[-1], {"method": "updateConfig", "argument": {"wallpaper": {"source": source}}})
        self.assertEqual(state["events"][-1]["result"], {"wallpaper": {"source": source}})
        self.assertFalse((self.root / "should-not-exist").exists())

    def test_keyed_gets_return_values_without_replacing_cached_document(self):
        original = self.run_action("getConfig")["config"]
        for key, expected in (("wallpaper.source", "/saved.png"),
                              ("playback.pause_when_output_inactive", False),
                              ("transition.duration_ms", 0), ("custom.values", [[], {}]),
                              ("missing.key", None)):
            state = self.run_action("getConfig", key)
            self.assertEqual(state["events"][-1], {"method": "getConfig", "result": expected})
            self.assertEqual(state["config"], original)
        state = self.run_action("getConfigFile")
        self.assertEqual(state["events"][-1]["result"], str(self.root / "config/wallpaper.toml"))

    def test_all_runtime_methods_forward_and_update_observable_state(self):
        self.assertEqual(self.run_action("status")["state"], "ready")
        self.assertEqual(self.run_action("start")["state"], "unknown")
        self.assertEqual(self.run_action("reload")["state"], "ready")
        self.assertEqual(self.run_action("restart")["state"], "unknown")
        self.assertEqual(self.run_action("stop")["state"], "stopped")
        self.assertEqual(self.calls(), [{"method": method} for method in ("status", "start", "reload", "restart", "stop")])

    def test_failed_stop_does_not_report_stopped_or_clear_config(self):
        original = self.run_action("getConfig")["config"]
        self.run_action("status")
        self.options(output=json.dumps({"ok": False, "error": "Could not stop renderer"}), exit=1)
        state = self.run_action("stop")
        self.assertEqual(state["state"], "ready")
        self.assertEqual(state["config"], original)
        self.assertEqual(state["events"][-1], {"method": "stop", "error": "Could not stop renderer"})

    def test_queue_preserves_order_and_snapshots_mutable_arguments(self):
        self.options(delay=0.08)
        self.submit({"method": "getConfig"},
                    {"method": "updateConfig", "argument": {"wallpaper": {"fit": "tile"}}, "mutate": True},
                    {"method": "getConfig", "argument": "wallpaper.source"}, {"method": "status"})
        self.assertTrue(self.state()["busy"])
        self.until(lambda: not self.state()["busy"])
        calls = self.calls()
        self.assertEqual([request["method"] for request in calls], ["getConfig", "updateConfig", "getConfig", "status"])
        self.assertEqual(calls[1]["argument"], {"wallpaper": {"fit": "tile"}})
        state = self.state()
        self.assertEqual([event["method"] for event in state["events"]], [request["method"] for request in calls])
        self.assertEqual(state["config"], {"wallpaper": {"fit": "tile"}})
        self.assertEqual(state["events"][2]["result"], "/saved.png")

    def test_completion_handlers_can_chain_more_work(self):
        self.ipc("chain", json.dumps({"items": [{"method": "updateConfig", "argument": {"wallpaper": {"fit": "fit"}}},
                                                {"method": "reload"}, {"method": "status"}]}))
        self.run_action("getConfig")
        self.assertEqual([request["method"] for request in self.calls()],
                         ["getConfig", "updateConfig", "reload", "status"])
        self.assertEqual(self.state()["state"], "ready")

    def test_errors_preserve_last_good_values_and_allow_retry(self):
        self.run_action("getConfig")
        before = self.run_action("updateConfig", {"wallpaper": {"source": "/good.png"}})
        outputs = [("not JSON", 0), ("null", 0), ("{}", 0),
                   ('{"ok":true,"result":"/bad.png","configPath":"/bad.toml"}', 1),
                   ('{"ok":false,"error":"Session unavailable"}', 1)]
        for output, code in outputs:
            with self.subTest(output=output):
                self.options(output=output, exit=code)
                state = self.run_action("updateConfig", {"wallpaper": {"source": "/bad.png"}})
                for key in ("config", "state", "configPath"):
                    self.assertEqual(state[key], before[key])
                self.assertTrue(state["error"])
                self.assertEqual(state["events"][-1]["error"], state["error"])
        self.assertEqual(self.state()["error"], "Session unavailable")
        self.options()
        state = self.run_action("updateConfig", {"wallpaper": {"source": "/recovered.png"}})
        self.assertEqual(state["error"], "")
        self.assertEqual(state["config"]["wallpaper"]["source"], "/recovered.png")

    def test_missing_bridge_reports_failure_and_allows_retry(self):
        saved = self.bridge.with_suffix(".saved")
        self.bridge.rename(saved)
        state = self.run_action("status")
        self.assertTrue(state["error"])
        self.assertEqual(state["state"], "unknown")
        saved.rename(self.bridge)
        self.assertEqual(self.run_action("status")["state"], "ready")

    def test_failed_process_start_releases_queue_and_allows_retry(self):
        self.submit({"method": "status"}, {"method": "getConfigFile"})
        self.until(lambda: not self.state()["busy"])
        events = self.state()["events"]
        self.assertEqual([event["method"] for event in events], ["status", "getConfigFile"])
        self.assertTrue(all("Could not start" in event["error"] for event in events))
        self.process_wrapper.write_text('#!/bin/sh\nexec /usr/bin/timeout "$@"\n')
        self.process_wrapper.chmod(0o755)
        self.assertEqual(self.run_action("status")["state"], "ready")

    def test_bad_result_shapes_fail_without_blocking_queued_requests(self):
        for method, result in (("getConfig", []), ("updateConfig", None), ("getConfigFile", {}), ("status", "unexpected"), ("reload", "ready")):
            with self.subTest(method=method):
                self.options(methods={method: {"output": json.dumps({"ok": True, "result": result,
                                                                    "configPath": "/bad.toml"})}})
                self.submit({"method": method}, {"method": "start"})
                self.until(lambda: not self.state()["busy"])
                events = self.state()["events"]
                self.assertIn("error", events[-2])
                self.assertEqual(events[-1], {"method": "start", "result": None})

    def test_timeout_releases_queue_and_allows_retry(self):
        self.options(methods={"status": {"delay": 0.5}})
        self.submit({"method": "status"}, {"method": "getConfigFile"})
        self.until(lambda: not self.state()["busy"])
        state = self.state()
        self.assertIn("timed out", state["events"][0]["error"])
        self.assertEqual(state["events"][1], {"method": "getConfigFile", "result": str(self.root / "config/wallpaper.toml")})
        self.options()
        self.assertEqual(self.run_action("status")["state"], "ready")

    def write_child_fixture(self, detached=False):
        # Model io.popen's writer and an independently sessioned renderer with harmless
        # delayed files. Neither process imports Luna or touches the user's desktop.
        (self.root / "child.py").write_text(textwrap.dedent('''\
            import os, pathlib, subprocess, sys, time
            root = pathlib.Path(os.environ["LUNA_WALLPAPER_UI_TEST_ROOT"])
            if DETACHED:
                subprocess.Popen([sys.executable, "-I", "-c",
                    "import pathlib,sys,time; time.sleep(0.4); pathlib.Path(sys.argv[1]).write_text('alive')",
                    str(root / "renderer-survived")], start_new_session=True,
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            (root / "child-started").write_text("started")
            time.sleep(0.6)
            (root / "late-write").write_text("old request")
        ''').replace("DETACHED", repr(detached)))

    def test_timeout_kills_child_writer_before_queue_advances_but_keeps_detached_renderer(self):
        self.write_child_fixture(detached=True)
        self.options(methods={"updateConfig": {"child": True}})
        self.submit({"method": "updateConfig", "argument": {"wallpaper": {"fit": "tile"}}},
                    {"method": "getConfigFile"})
        self.until(lambda: not self.state()["busy"])
        state = self.state()
        self.assertTrue((self.root / "child-started").exists())
        self.assertIn("timed out", state["events"][0]["error"])
        self.assertEqual(state["events"][1], {"method": "getConfigFile", "result": str(self.root / "config/wallpaper.toml")})
        time.sleep(0.7)
        self.assertFalse((self.root / "late-write").exists())
        self.assertEqual((self.root / "renderer-survived").read_text(), "alive")

    def test_unloading_request_cancels_its_child_writer(self):
        self.write_child_fixture()
        self.options(methods={"updateConfig": {"child": True}})
        self.submit({"method": "updateConfig", "argument": {"wallpaper": {"fit": "tile"}}})
        self.until(lambda: (self.root / "child-started").exists())
        self.ipc("destroyRequest")
        time.sleep(0.7)
        self.assertFalse((self.root / "late-write").exists())

    def test_production_bridge_reads_and_updates_private_toml_without_renderer(self):
        dependency = subprocess.run(["/usr/bin/python3", "-I", "-c", "import tomlkit"], capture_output=True)
        if dependency.returncode:
            self.skipTest("system TOMLKit required for config integration")
        for name in ("bridge.lua", "api.lua", "config.lua", "runtime.lua", "read.lua"):
            shutil.copy(REPO / "src/wallpaper/src" / name, self.bridge.parent / name)
        shutil.copy(REPO / "lib/common.lua", self.root / "lib/common.lua")
        shutil.copy(REPO / "lib/quickshell.lua", self.root / "lib/quickshell.lua")
        shutil.copy(REPO / "lib/toml.lua", self.root / "lib/toml.lua")
        shutil.copy(REPO / "lib/config.lua", self.root / "lib/config.lua")
        shutil.copy(REPO / "lib/validation.lua", self.root / "lib/validation.lua")
        shutil.copytree(REPO / "lib/vendor", self.root / "lib/vendor")
        defaults = self.root / "apps/luna-wallpaper/config/wallpaper.toml"
        defaults.parent.mkdir(parents=True)
        shutil.copy(REPO / "apps/luna-wallpaper/config/wallpaper.toml", defaults)
        self.user_config.write_text('# Keep my preferences\n[wallpaper]\nsource = "/saved.png"\n'
                                    'fit = "center" # Original note\n[future]\nvalues = [[], {}]\n')
        state = self.run_action("getConfig")
        self.assertEqual(state["error"], "")
        self.assertEqual(state["config"]["future"]["values"], [[], {}])
        state = self.run_action("updateConfig", {"wallpaper": {"fit": "tile"}})
        self.assertEqual(state["error"], "")
        self.assertEqual(state["config"]["wallpaper"]["fit"], "tile")
        self.assertEqual(state["configPath"], str(self.user_config))
        saved = self.user_config.read_text()
        self.assertIn('# Keep my preferences', saved)
        self.assertIn('fit = "tile" # Original note', saved)
        self.assertIn('values = [[], {}]', saved)
        state = self.run_action("updateConfig", {"wallpaper": {"fit": "invalid"}})
        self.assertIn("fit", state["error"])
        self.assertEqual(self.user_config.read_text(), saved)
        self.assertFalse((self.bridge.parent / "shell/shell.qml").exists())


if __name__ == "__main__":
    unittest.main()
