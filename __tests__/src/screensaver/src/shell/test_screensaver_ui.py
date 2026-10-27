"""Exercise the QML screensaver API with a private bridge and no desktop renderer.

Run from the repository root:
    python3 -m unittest discover -s __tests__/src/screensaver/src/shell -p test_screensaver_ui.py -v
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
class ScreensaverUiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna screensaver ' # % ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        module = self.root / "src/qml/Luna"
        module.mkdir(parents=True)
        client = self.root / "src/screensaver/src/shell/Screensaver.qml"
        client.parent.mkdir(parents=True)
        shutil.copy(REPO / "src/screensaver/src/shell/Screensaver.qml", client)
        # Only these private copies override startup/deadline conditions for failure tests.
        if self._testMethodName == "test_failed_process_start_releases_queue_and_allows_retry":
            self.process_wrapper = self.root / "timeout-wrapper"
            client.write_text(client.read_text().replace('command: ["/usr/bin/timeout",',
                                                        'command: [' + json.dumps(str(self.process_wrapper)) + ','))
        if self._testMethodName.startswith("test_timeout_"):
            client.write_text(client.read_text().replace('"90s"', '"0.1s"'))
        # Keep the real screensaver registration without unrelated singleton dependencies.
        registration = (REPO / "src/qml/Luna/qmldir").read_text().splitlines()
        (module / "qmldir").write_text("\n".join(line for line in registration
                                                if line == "module Luna" or line.startswith("singleton Screensaver ")) + "\n")
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
        case "getConfig": Luna.Screensaver.getConfig(request.argument); break;
        case "updateConfig": Luna.Screensaver.updateConfig(request.argument); break;
        case "getConfigFile": Luna.Screensaver.getConfigFile(); break;
        case "reload": Luna.Screensaver.reload(); break;
        case "status": Luna.Screensaver.status(); break;
        case "start": Luna.Screensaver.start(); break;
        case "stop": Luna.Screensaver.stop(); break;
        case "restart": Luna.Screensaver.restart(); break;
        case "getState": Luna.Screensaver.getState(); break;
        case "show": Luna.Screensaver.show(); break;
        case "hide": Luna.Screensaver.hide(); break;
        case "setStayAwake": Luna.Screensaver.setStayAwake(request.argument); break;
        case "toggleStayAwake": Luna.Screensaver.toggleStayAwake(); break;
        case "list": Luna.Screensaver.list(); break;
        case "getDirectory": Luna.Screensaver.getDirectory(); break;
        case "install": Luna.Screensaver.install(request.argument.source, request.argument.options); break;
        case "set": Luna.Screensaver.set(request.argument); break;
        case "removalPlan": Luna.Screensaver.removalPlan(request.argument); break;
        case "remove": Luna.Screensaver.remove(request.argument); break;
        }
    }
    Connections {
        target: Luna.Screensaver
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
            return JSON.stringify({busy: Luna.Screensaver.busy, error: Luna.Screensaver.error,
                config: Luna.Screensaver.config,
                library: Luna.Screensaver.library, libraryPath: Luna.Screensaver.libraryPath,
                stateData: Luna.Screensaver.stateData,
                active: Luna.Screensaver.active, stayAwake: Luna.Screensaver.stayAwake,
                state: Luna.Screensaver.state, configPath: Luna.Screensaver.configPath,
                events: shell.events});
        }
        function run(requests: string): void {
            const parsed = JSON.parse(requests).items;
            for (let index = 0; index < parsed.length; index++) {
                const request = parsed[index];
                shell.invoke(request);
                if (request.mutate) request.argument.screensaver.fit = "fill";
                if (request.mutateInstall) request.argument.options.name = "changed";
                if (request.mutateNames) request.argument.push("changed");
            }
        }
        function chain(requests: string): void {
            shell.chain = JSON.parse(requests).items;
        }
        function destroyRequest(): void {
            Luna.Screensaver.activeRequest.destroy();
        }
    }
}
''')

        # Copy the codec only. Every API method below is fake and cannot launch screensaver.
        codec = self.root / "lib/json.lua"
        codec.parent.mkdir(parents=True)
        shutil.copy(REPO / "lib/json.lua", codec)
        self.bridge = self.root / "src/screensaver/src/bridge.lua"
        self.bridge.parent.mkdir(parents=True, exist_ok=True)
        self.bridge.write_text(textwrap.dedent('''\
            local root = os.getenv("LUNA_SCREENSAVER_UI_TEST_ROOT")
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
                local pipe = assert(io.popen('/usr/bin/python3 -I "$LUNA_SCREENSAVER_UI_TEST_ROOT/child.py"'))
                pipe:read("*a")
                pipe:close()
            end
            if options.output then
                print(options.output)
            else
                local result = json.null
                if request.method == "getConfig" then
                    result = { screensaver = { source = "/saved.png", fit = "fill" },
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
                    result = root .. "/config/screensaver.toml"
                elseif request.method == "getDirectory" then
                    result = root .. "/data/luna/screensavers"
                elseif request.method == "list" then
                    result = json.array({{name = "clock", path = "/bundled/shell.qml", bundled = true, current = true},
                        {name = "aurora", path = "/library/aurora/shell.qml", bundled = false, current = false}})
                elseif request.method == "install" then
                    local name = request.argument.options and request.argument.options.name or "aurora"
                    result = {name = name, path = "/library/" .. name .. "/shell.qml", bundled = false}
                elseif request.method == "set" then
                    result = {name = request.argument, path = "/library/" .. request.argument .. "/shell.qml",
                        bundled = false, current = true, selection = "/library/" .. request.argument .. "/shell.qml"}
                elseif request.method == "removalPlan" then
                    result = json.array()
                    for _, name in ipairs(request.argument) do
                        table.insert(result, {name = name, path = "/library/" .. name .. "/shell.qml", bundled = false})
                    end
                elseif request.method == "remove" then
                    result = request.argument
                elseif request.method == "status" then
                    result = "idle"
                elseif request.method == "getState" or request.method == "setStayAwake" or request.method == "toggleStayAwake" then
                    result = {running = true, active = true, stayAwake = request.argument == true or request.method == "toggleStayAwake",
                        outputsOff = false, rendererState = "ready", error = ""}
                end
                print(json.encode({ok = true, result = result,
                    configPath = root .. "/config/screensaver.toml"}))
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
                                LUNA_SCREENSAVER_UI_TEST_ROOT=str(self.root),
                                DBUS_SYSTEM_BUS_ADDRESS="unix:path=/nonexistent-luna-test-system-bus")
        # A user config must be outside the copied checkout, just as in an installation.
        personal = tempfile.TemporaryDirectory(prefix="luna-screensaver-user-")
        self.addCleanup(personal.cleanup)
        self.user_config = Path(personal.name) / "screensaver.toml"
        self.environment["LUNA_SCREENSAVER_CONFIG"] = str(self.user_config)
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
        self.fail("Screensaver API condition failed: " + (self.root / "shell.log").read_text())

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
                                      "library": None, "libraryPath": "",
                                      "state": "unknown", "configPath": "", "stateData": None,
                                      "active": False, "stayAwake": False, "events": []})
        self.assertEqual(self.calls(), [])

    def test_config_round_trip_and_source_arguments_are_preserved(self):
        state = self.run_action("getConfig")
        self.assertEqual(state["config"]["screensaver"], {"source": "/saved.png", "fit": "fill"})
        self.assertEqual(state["configPath"], str(self.root / "config/screensaver.toml"))
        changes = {"screensaver": {"fit": "tile"}, "transition": {"duration_ms": 37}}
        self.assertEqual(self.run_action("updateConfig", changes)["config"], changes)
        source = '/tmp/雪 # % " \' $(touch should-not-exist); screensaver.png'
        state = self.run_action("updateConfig", {"screensaver": {"source": source}})
        self.assertEqual(state["config"]["screensaver"]["source"], source)
        self.assertEqual(self.calls()[-1], {"method": "updateConfig", "argument": {"screensaver": {"source": source}}})
        self.assertEqual(state["events"][-1]["result"], {"screensaver": {"source": source}})
        self.assertFalse((self.root / "should-not-exist").exists())

    def test_keyed_gets_return_values_without_replacing_cached_document(self):
        original = self.run_action("getConfig")["config"]
        for key, expected in (("screensaver.source", "/saved.png"),
                              ("playback.pause_when_output_inactive", False),
                              ("transition.duration_ms", 0), ("custom.values", [[], {}]),
                              ("missing.key", None)):
            state = self.run_action("getConfig", key)
            self.assertEqual(state["events"][-1], {"method": "getConfig", "result": expected})
            self.assertEqual(state["config"], original)
        state = self.run_action("getConfigFile")
        self.assertEqual(state["events"][-1]["result"], str(self.root / "config/screensaver.toml"))

    def test_library_reads_cache_results_and_plan_does_not_change_the_snapshot(self):
        state = self.run_action("list")
        library = state["library"]
        self.assertEqual([entry["name"] for entry in library], ["clock", "aurora"])
        self.assertTrue(library[0]["current"])
        self.assertEqual(state["events"][-1]["result"], library)
        self.assertEqual(self.run_action("getDirectory")["libraryPath"],
                         str(self.root / "data/luna/screensavers"))
        state = self.run_action("removalPlan", ["aurora"])
        self.assertEqual(state["events"][-1]["result"],
                         [{"name": "aurora", "path": "/library/aurora/shell.qml", "bundled": False}])
        self.assertEqual(state["library"], library)
        self.assertEqual(state["state"], "unknown")
        self.options(output=json.dumps({"ok": True, "result": [], "configPath": "/private/config.toml"}))
        self.assertEqual(self.run_action("list")["library"], [])

    def test_library_mutations_invalidate_only_affected_snapshots(self):
        config = self.run_action("getConfig")["config"]
        snapshot = self.run_action("getState")["stateData"]
        path = self.run_action("getDirectory")["libraryPath"]
        for method, argument in (("install", {"source": "/source/aurora.qml"}), ("remove", ["aurora"])):
            self.run_action("list")
            state = self.run_action(method, argument)
            self.assertIsNone(state["library"])
            self.assertEqual(state["config"], config)
            self.assertEqual(state["stateData"], snapshot)
            self.assertEqual(state["libraryPath"], path)
        self.run_action("list")
        changes = {"renderer": {"shell": "/direct/shell.qml"}}
        state = self.run_action("updateConfig", changes)
        self.assertIsNone(state["library"])
        self.assertEqual(state["config"], changes)
        self.assertEqual(state["stateData"], snapshot)
        self.run_action("list")
        state = self.run_action("set", "aurora")
        self.assertEqual(state["events"][-1]["result"]["name"], "aurora")
        self.assertIsNone(state["library"])
        self.assertIsNone(state["config"])
        self.assertIsNone(state["stateData"])
        self.assertEqual(state["state"], "unknown")
        self.assertEqual(state["libraryPath"], path)

    def test_library_arguments_are_serialized_before_caller_mutates_them(self):
        self.options(delay=0.05)
        source = '/tmp/雪 # % " \' $(touch should-not-exist); shell.qml'
        options = {"name": "aurora", "force": True}
        self.submit({"method": "list"},
                    {"method": "install", "argument": {"source": source, "options": options}, "mutateInstall": True},
                    {"method": "removalPlan", "argument": ["aurora"], "mutateNames": True},
                    {"method": "remove", "argument": ["aurora"], "mutateNames": True})
        self.until(lambda: not self.state()["busy"])
        self.assertEqual(self.calls(), [
            {"method": "list"},
            {"method": "install", "argument": {"source": source, "options": options}},
            {"method": "removalPlan", "argument": ["aurora"]},
            {"method": "remove", "argument": ["aurora"]},
        ])
        self.assertTrue(all("result" in event for event in self.state()["events"]))
        self.assertFalse((self.root / "should-not-exist").exists())

    def test_bad_library_result_shapes_preserve_cached_values(self):
        self.run_action("getConfig")
        self.run_action("getState")
        self.run_action("getDirectory")
        before = self.run_action("list")
        entry = {"name": "aurora", "path": "/library/aurora/shell.qml", "bundled": False}
        invalid = (("list", {}), ("list", [entry]), ("list", [{**entry, "current": "false"}]),
                   ("install", []), ("install", {**entry, "path": None}),
                   ("set", entry), ("set", {**entry, "current": False, "selection": entry["path"]}),
                   ("removalPlan", [None]), ("removalPlan", [{**entry, "bundled": "false"}]),
                   ("remove", [entry]), ("getDirectory", []))
        for method, result in invalid:
            with self.subTest(method=method, result=result):
                self.options(output=json.dumps({"ok": True, "result": result, "configPath": "/bad.toml"}))
                argument = {"source": "/source/aurora.qml"} if method == "install" else "aurora" if method == "set" else ["aurora"]
                state = self.run_action(method, argument)
                self.assertTrue(state["error"])
                for key in ("library", "libraryPath", "config", "stateData", "state", "configPath"):
                    self.assertEqual(state[key], before[key])
        self.options()
        self.assertEqual(self.run_action("list")["error"], "")

    def test_failed_library_mutations_keep_snapshots_and_allow_retry(self):
        self.run_action("getConfig")
        self.run_action("getState")
        before = self.run_action("list")
        for method, argument in (("install", {"source": "/source/aurora.qml"}),
                                 ("set", "aurora"), ("remove", ["aurora"])):
            self.options(output=json.dumps({"ok": False, "error": "Shell is selected"}), exit=1)
            state = self.run_action(method, argument)
            self.assertEqual(state["events"][-1], {"method": method, "error": "Shell is selected"})
            for key in ("library", "config", "stateData", "state"):
                self.assertEqual(state[key], before[key])
        self.options()
        state = self.run_action("set", "aurora")
        self.assertEqual(state["error"], "")
        self.assertIsNone(state["library"])

    def test_all_runtime_methods_forward_and_update_observable_state(self):
        self.assertEqual(self.run_action("status")["state"], "idle")
        self.assertEqual(self.run_action("start")["state"], "unknown")
        self.assertEqual(self.run_action("reload")["state"], "unknown")
        self.assertEqual(self.run_action("restart")["state"], "unknown")
        self.assertEqual(self.run_action("stop")["state"], "stopped")
        self.assertEqual(self.calls(), [{"method": method} for method in ("status", "start", "reload", "restart", "stop")])

    def test_controller_snapshots_and_stay_awake_boolean_arguments(self):
        state = self.run_action("getState")
        self.assertEqual(state["state"], "showing")
        self.assertTrue(state["active"])
        self.assertFalse(state["stayAwake"])
        self.assertTrue(self.run_action("setStayAwake", True)["stayAwake"])
        self.assertFalse(self.run_action("setStayAwake", False)["stayAwake"])
        self.assertTrue(self.run_action("toggleStayAwake")["stayAwake"])
        self.assertEqual(self.calls()[1:3], [{"method": "setStayAwake", "argument": True},
                                           {"method": "setStayAwake", "argument": False}])

    def test_lifecycle_does_not_guess_readiness_from_acknowledgement(self):
        for method in ("start", "restart", "reload", "show", "hide"):
            self.run_action("getState")
            state = self.run_action(method)
            self.assertEqual(state["state"], "unknown")
            self.assertIsNone(state["stateData"])
        stopped = self.run_action("stop")
        self.assertEqual(stopped["state"], "stopped")
        self.assertFalse(stopped["active"])
        self.assertFalse(stopped["stateData"]["running"])

    def test_bad_state_snapshots_preserve_cached_state(self):
        good = self.run_action("getState")
        for result in (None, [], {}, {**good["stateData"], "stayAwake": "false"},
                       {**good["stateData"], "rendererState": "unexpected"}):
            self.options(output=json.dumps({"ok": True, "result": result, "configPath": "/bad.toml"}))
            state = self.run_action("getState")
            self.assertTrue(state["error"])
            self.assertEqual(state["stateData"], good["stateData"])
            self.assertEqual(state["state"], "showing")

    def test_controller_errors_are_not_hidden_by_idle_renderer_state(self):
        result = {"running": True, "active": False, "stayAwake": False, "outputsOff": False,
                  "rendererState": "hidden", "error": "The compositor did not confirm automatic locking."}
        self.options(output=json.dumps({"ok": True, "result": result, "configPath": "/private/screensaver.toml"}))
        state = self.run_action("getState")
        self.assertEqual(state["state"], "error")
        self.assertEqual(state["stateData"]["error"], result["error"])

    def test_failed_stop_does_not_report_stopped_or_clear_config(self):
        original = self.run_action("getConfig")["config"]
        self.run_action("status")
        self.options(output=json.dumps({"ok": False, "error": "Could not stop renderer"}), exit=1)
        state = self.run_action("stop")
        self.assertEqual(state["state"], "idle")
        self.assertEqual(state["config"], original)
        self.assertEqual(state["events"][-1], {"method": "stop", "error": "Could not stop renderer"})

    def test_queue_preserves_order_and_snapshots_mutable_arguments(self):
        self.options(delay=0.08)
        self.submit({"method": "getConfig"},
                    {"method": "updateConfig", "argument": {"screensaver": {"fit": "tile"}}, "mutate": True},
                    {"method": "getConfig", "argument": "screensaver.source"}, {"method": "status"})
        self.assertTrue(self.state()["busy"])
        self.until(lambda: not self.state()["busy"])
        calls = self.calls()
        self.assertEqual([request["method"] for request in calls], ["getConfig", "updateConfig", "getConfig", "status"])
        self.assertEqual(calls[1]["argument"], {"screensaver": {"fit": "tile"}})
        state = self.state()
        self.assertEqual([event["method"] for event in state["events"]], [request["method"] for request in calls])
        self.assertEqual(state["config"], {"screensaver": {"fit": "tile"}})
        self.assertEqual(state["events"][2]["result"], "/saved.png")

    def test_completion_handlers_can_chain_more_work(self):
        self.ipc("chain", json.dumps({"items": [{"method": "updateConfig", "argument": {"screensaver": {"fit": "fit"}}},
                                                {"method": "reload"}, {"method": "status"}]}))
        self.run_action("getConfig")
        self.assertEqual([request["method"] for request in self.calls()],
                         ["getConfig", "updateConfig", "reload", "status"])
        self.assertEqual(self.state()["state"], "idle")

    def test_errors_preserve_last_good_values_and_allow_retry(self):
        self.run_action("getConfig")
        before = self.run_action("updateConfig", {"screensaver": {"source": "/good.png"}})
        outputs = [("not JSON", 0), ("null", 0), ("{}", 0),
                   ('{"ok":true,"result":"/bad.png","configPath":"/bad.toml"}', 1),
                   ('{"ok":false,"error":"Session unavailable"}', 1)]
        for output, code in outputs:
            with self.subTest(output=output):
                self.options(output=output, exit=code)
                state = self.run_action("updateConfig", {"screensaver": {"source": "/bad.png"}})
                for key in ("config", "state", "configPath"):
                    self.assertEqual(state[key], before[key])
                self.assertTrue(state["error"])
                self.assertEqual(state["events"][-1]["error"], state["error"])
        self.assertEqual(self.state()["error"], "Session unavailable")
        self.options()
        state = self.run_action("updateConfig", {"screensaver": {"source": "/recovered.png"}})
        self.assertEqual(state["error"], "")
        self.assertEqual(state["config"]["screensaver"]["source"], "/recovered.png")

    def test_missing_bridge_reports_failure_and_allows_retry(self):
        saved = self.bridge.with_suffix(".saved")
        self.bridge.rename(saved)
        state = self.run_action("status")
        self.assertTrue(state["error"])
        self.assertEqual(state["state"], "unknown")
        saved.rename(self.bridge)
        self.assertEqual(self.run_action("status")["state"], "idle")

    def test_failed_process_start_releases_queue_and_allows_retry(self):
        self.submit({"method": "status"}, {"method": "getConfigFile"})
        self.until(lambda: not self.state()["busy"])
        events = self.state()["events"]
        self.assertEqual([event["method"] for event in events], ["status", "getConfigFile"])
        self.assertTrue(all("Could not start" in event["error"] for event in events))
        self.process_wrapper.write_text('#!/bin/sh\nexec /usr/bin/timeout "$@"\n')
        self.process_wrapper.chmod(0o755)
        self.assertEqual(self.run_action("status")["state"], "idle")

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
        self.assertEqual(state["events"][1], {"method": "getConfigFile", "result": str(self.root / "config/screensaver.toml")})
        self.options()
        self.assertEqual(self.run_action("status")["state"], "idle")

    def write_child_fixture(self, detached=False):
        # Model io.popen's writer and an independently sessioned renderer with harmless
        # delayed files. Neither process imports Luna or touches the user's desktop.
        (self.root / "child.py").write_text(textwrap.dedent('''\
            import os, pathlib, subprocess, sys, time
            root = pathlib.Path(os.environ["LUNA_SCREENSAVER_UI_TEST_ROOT"])
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
        self.submit({"method": "updateConfig", "argument": {"screensaver": {"fit": "tile"}}},
                    {"method": "getConfigFile"})
        self.until(lambda: not self.state()["busy"])
        state = self.state()
        self.assertTrue((self.root / "child-started").exists())
        self.assertIn("timed out", state["events"][0]["error"])
        self.assertEqual(state["events"][1], {"method": "getConfigFile", "result": str(self.root / "config/screensaver.toml")})
        time.sleep(0.7)
        self.assertFalse((self.root / "late-write").exists())
        self.assertEqual((self.root / "renderer-survived").read_text(), "alive")

    def test_unloading_request_cancels_its_child_writer(self):
        self.write_child_fixture()
        self.options(methods={"updateConfig": {"child": True}})
        self.submit({"method": "updateConfig", "argument": {"screensaver": {"fit": "tile"}}})
        self.until(lambda: (self.root / "child-started").exists())
        self.ipc("destroyRequest")
        time.sleep(0.7)
        self.assertFalse((self.root / "late-write").exists())



if __name__ == "__main__":
    unittest.main()
