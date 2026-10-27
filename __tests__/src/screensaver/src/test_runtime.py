"""Exercise controller lifecycle against an isolated, recording-only qs process."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[4]
CONTROLLER = REPO / "src/screensaver/src/shell/controller.qml"


class ScreensaverFixture:
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna screensaver '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config = self.root / "config/luna/screensaver.toml"
        self.config.parent.mkdir(parents=True)
        self.tools = self.root / "bin"
        self.tools.mkdir()
        self.env = dict(os.environ, HOME=str(self.root), XDG_CONFIG_HOME=str(self.root / "config"),
                        XDG_DATA_HOME=str(self.root / "data"), LUNA_SCREENSAVER_CONFIG="",
                        WAYLAND_DISPLAY="screensaver-test", HYPRLAND_INSTANCE_SIGNATURE="",
                        PATH=str(self.tools) + ":" + os.environ["PATH"], SCREENSAVER_TEST=str(self.root))
        mock = self.tools / "qs"
        mock.write_text('''#!/usr/bin/python3
import json, os, pathlib, sys, time
root = pathlib.Path(os.environ["SCREENSAVER_TEST"])
args = sys.argv[1:]
with (root / "calls").open("a") as log:
    log.write(json.dumps(args) + "\\n")
running = root / "running"
statefile = root / "state"
instances = root / "instances"
def state():
    return json.loads(statefile.read_text()) if statefile.exists() else {
        "running": True, "active": False, "stayAwake": False, "outputsOff": False,
        "rendererState": "hidden", "error": ""}
def save(value):
    statefile.write_text(json.dumps(value))
if args[0] == "-p":
    print("Mock controller startup output")
    if os.environ.get("TEST_START_FAILURE"):
        print("Mock compositor unavailable")
        sys.exit(1)
    running.touch()
    save({"running": True, "active": False, "stayAwake": False, "outputsOff": False,
          "rendererState": "hidden", "error": ""})
    (root / "environment").write_text(json.dumps({key: os.environ.get(key) for key in
        ("LUNA_SCREENSAVER_SETTINGS", "LUNA_UI_THEME", "QML_IMPORT_PATH")}))
    sys.exit(0)
if args[0] == "list":
    print(instances.read_text() if instances.exists() else "No running instances.")
    sys.exit(0)
if args[0] == "kill":
    if os.environ.get("TEST_KILL_FAILURE"):
        sys.exit(1)
    remaining = [item for item in json.loads(instances.read_text()) if str(item["pid"]) != args[-1]]
    instances.write_text(json.dumps(remaining))
    running.unlink(missing_ok=True)
    sys.exit(0)
if args[0] != "ipc" or not running.exists():
    sys.exit(1)
method = args[args.index("screensaver") + 1]
if method == os.environ.get("TEST_HOLD_METHOD"):
    (root / "held").touch()
    deadline = time.monotonic() + 10
    while not (root / "release").exists() and time.monotonic() < deadline:
        time.sleep(0.01)
if method == os.environ.get("TEST_FAIL_METHOD"):
    sys.exit(1)
value = state()
if method == "ping":
    print("ready")
elif method == "status":
    print("error" if value["error"] else "showing" if value["active"] else "idle")
elif method == "getState":
    print(os.environ.get("TEST_STATE_RESPONSE", json.dumps(value)))
elif method == "getRendererShell":
    if (root / "configured").exists():
        config = json.loads((root / "configured").read_text())["config"]
    else:
        environment = json.loads((root / "environment").read_text())
        config = json.loads(environment["LUNA_SCREENSAVER_SETTINGS"])
    path = config["renderer"]["shell"]
    if not path:
        path = str(pathlib.Path(args[args.index("-p") + 1]).parent / "shell.qml")
    print(os.environ.get("TEST_SHELL_RESPONSE", os.path.expanduser(path)))
elif method == "configure":
    (root / "configured").write_text(args[-1])
    failing = os.environ.get("TEST_FAIL_SHELL")
    if failing:
        failed = json.loads(args[-1])["config"]["renderer"]["shell"] == failing
        value["active"] = False if failed else value["active"]
        value["rendererState"] = "error" if failed else "ready" if value["active"] else "hidden"
        value["error"] = "Broken custom shell" if failed else ""
        save(value)
elif method in ("show", "hide"):
    value["active"] = method == "show" and not os.environ.get("TEST_SHOW_DISMISSED")
    value["rendererState"] = "ready" if value["active"] else "hidden"
    value["error"] = "Broken custom shell" if os.environ.get("TEST_RENDER_FAILURE") else ""
    if value["error"]:
        value["rendererState"] = "error"
    save(value)
elif method in ("setStayAwake", "toggleStayAwake"):
    value["stayAwake"] = not value["stayAwake"] if method == "toggleStayAwake" else json.loads(args[-1])
    save(value)
    print(json.dumps(value))
elif method == "shutdown":
    running.unlink(missing_ok=True)
else:
    sys.exit(1)
''')
        mock.chmod(0o755)

    def lua(self, code, ok=True):
        result = subprocess.run(
            ["/usr/bin/lua", "-E", "-", str(REPO)],
            input='local luna = dofile(arg[1] .. "/lib/luna.lua")(arg[1])\n'
                  'local screensaver = luna.screensaver\n' + code,
            cwd=self.root, env=self.env, capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "", "API operations leave output to their caller")
        return result

    def calls(self):
        path = self.root / "calls"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def starts(self):
        return [call for call in self.calls() if call[0] == "-p"]

    def cli(self, *args):
        return subprocess.run([str(REPO / "bin/luna"), *args], cwd=self.root, env=self.env,
                              text=True, capture_output=True, timeout=20)


class ScreensaverRuntimeTests(ScreensaverFixture, unittest.TestCase):
    def test_start_is_hidden_idempotent_and_uses_validated_config_theme_and_imports(self):
        self.config.write_text('[idle]\nlock_seconds = 900\n[settings]\nmessage = "hello"\n')
        self.lua('screensaver.start(); screensaver.start(); assert(screensaver.status() == "idle")')
        self.assertEqual(len(self.starts()), 1)
        self.assertEqual(self.starts()[0][1], str(CONTROLLER))
        self.assertIn("--no-duplicate", self.starts()[0])
        environment = json.loads((self.root / "environment").read_text())
        self.assertEqual(json.loads(environment["LUNA_SCREENSAVER_SETTINGS"])["idle"]["lock_seconds"], 900)
        self.assertEqual(json.loads(environment["LUNA_UI_THEME"])["version"], 1)
        self.assertTrue(environment["QML_IMPORT_PATH"].startswith(str(REPO / "src/qml")))
        self.assertFalse(json.loads((self.root / "state").read_text())["active"])

    def test_reload_reconfigures_without_restart_or_awake_reset(self):
        self.lua('screensaver.setStayAwake(true); screensaver.show()')
        self.config.write_text('[settings]\nclock = false\n')
        self.lua('screensaver.reload(); assert(screensaver.getState().stayAwake); assert(screensaver.getState().active)')
        payload = json.loads((self.root / "configured").read_text())
        self.assertIs(payload["config"]["settings"]["clock"], False)
        self.assertEqual(payload["theme"]["version"], 1)
        self.assertEqual(len(self.starts()), 1)
        self.assertFalse(any(call[0] in ("kill", "list") for call in self.calls()))

    def test_config_and_theme_errors_precede_reload_restart_or_start_mutation(self):
        self.lua('screensaver.start()')
        count = len(self.calls())
        self.config.write_text('[idle]\nlock_seconds = -1\n')
        for action in ("reload", "restart", "start"):
            self.lua(f'screensaver.{action}()', ok=False)
        self.assertEqual(len(self.calls()), count)
        self.config.unlink()
        (self.config.parent / "theme").write_text("missing-theme\n")
        for action in ("reload", "restart", "start"):
            self.lua(f'screensaver.{action}()', ok=False)
        self.assertEqual(len(self.calls()), count)

    def test_reading_state_and_hiding_never_starts(self):
        self.lua('''
assert(screensaver.status() == "stopped")
local state = screensaver.getState()
assert(not state.running and not state.active and not state.stayAwake and not state.outputsOff)
assert(state.rendererState == "hidden" and state.error == "")
screensaver.hide()
''')
        self.assertFalse(self.starts())
        self.assertFalse(self.config.exists())

    def test_show_starts_once_hide_keeps_controller_and_renderer_errors_are_reported(self):
        self.lua('screensaver.show(); assert(screensaver.getState().active); screensaver.hide(); '
                 'assert(screensaver.status() == "idle")')
        self.assertEqual(len(self.starts()), 1)
        self.env["TEST_RENDER_FAILURE"] = "1"
        result = self.lua('screensaver.show()', ok=False)
        self.assertIn("Broken custom shell", result.stderr)
        self.assertTrue((self.root / "running").exists())

    def test_restart_gracefully_stops_and_resets_awake_before_hidden_start(self):
        self.lua('screensaver.setStayAwake(true); screensaver.show(); screensaver.restart(); '
                 'assert(not screensaver.getState().stayAwake); assert(screensaver.status() == "idle")')
        self.assertEqual(len(self.starts()), 2)
        self.assertTrue(any(call[-1] == "shutdown" for call in self.calls()))
        self.assertFalse(any(call[0] == "kill" for call in self.calls()))

    def test_immediate_dismissal_or_locked_session_show_is_an_idle_noop(self):
        self.env["TEST_SHOW_DISMISSED"] = "1"
        self.lua('screensaver.show(); assert(screensaver.status() == "idle")')
        self.assertEqual(len(self.starts()), 1)

    def test_stop_cleans_only_canonical_controller_instances_without_config_or_session(self):
        alias = self.root / "controller-alias.qml"
        alias.symlink_to(CONTROLLER)
        instances = [{"pid": 101, "config_path": str(CONTROLLER)},
                     {"pid": 102, "config_path": str(alias)},
                     {"pid": 103, "config_path": str(REPO / "src/luna-bar/shell.qml")},
                     {"pid": 104, "config_path": "/other/controller.qml"}]
        (self.root / "instances").write_text(json.dumps(instances))
        self.config.write_text("[broken")
        self.env["WAYLAND_DISPLAY"] = ""
        self.lua('screensaver.stop(); screensaver.stop()')
        self.assertEqual(json.loads((self.root / "instances").read_text()), instances[2:])
        self.assertEqual([call for call in self.calls() if call[0] == "kill"],
                         [["kill", "--pid", "101"], ["kill", "--pid", "102"]])
        self.assertFalse(self.starts())

    def test_invalid_state_and_running_ipc_failure_do_not_claim_stopped(self):
        self.lua('screensaver.start()')
        for response in ("null", "{}", '{"running":true,"active":false}', "not-json"):
            self.env["TEST_STATE_RESPONSE"] = response
            self.assertIn("Invalid screensaver state", self.lua('screensaver.getState()', ok=False).stderr)
        self.env.pop("TEST_STATE_RESPONSE")
        self.env["TEST_FAIL_METHOD"] = "getState"
        self.assertIn("Could not read", self.lua('screensaver.getState()', ok=False).stderr)
        self.env["TEST_FAIL_METHOD"] = "status"
        self.assertIn("Could not read", self.lua('screensaver.status()', ok=False).stderr)

    def test_failed_start_does_not_leak_stdout(self):
        self.env["TEST_START_FAILURE"] = "1"
        result = self.lua('screensaver.show()', ok=False)
        self.assertIn("Mock compositor unavailable", result.stderr)
        self.assertFalse((self.root / "running").exists())

    def test_applied_shell_probe_is_passive_and_rejects_invalid_running_replies(self):
        setup = '''local common = dofile(arg[1] .. "/lib/common.lua")
local runtime = dofile(arg[1] .. "/src/screensaver/src/runtime.lua")(common, arg[1],
    arg[1] .. "/src/screensaver/src/shell/controller.qml")
'''
        self.lua(setup + 'assert(runtime.getRendererShell() == nil)')
        self.assertFalse(self.starts())
        self.lua(setup + 'screensaver.start(); assert(runtime.getRendererShell():match("/shell/shell.qml$"))')
        for response in ("", "relative.qml", "unexpected\\n/path.qml"):
            self.env["TEST_SHELL_RESPONSE"] = response
            self.assertIn("Invalid applied screensaver shell",
                          self.lua(setup + 'runtime.getRendererShell()', ok=False).stderr)
        self.env.pop("TEST_SHELL_RESPONSE")
        self.env["TEST_FAIL_METHOD"] = "getRendererShell"
        self.assertIn("Could not read applied screensaver shell",
                      self.lua(setup + 'runtime.getRendererShell()', ok=False).stderr)


if __name__ == "__main__":
    unittest.main()
