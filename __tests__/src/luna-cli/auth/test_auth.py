"""Exercise polkit ownership and CLI dispatch without changing the host's services."""
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[4]
SPEC = importlib.util.spec_from_file_location("luna_auth_service", REPO / "src/luna-cli/auth/service.py")
SERVICE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVICE)
UNIT, KDE = SERVICE.UNIT, SERVICE.KDE_UNIT


class AuthLifecycleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="luna auth '")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.root = self.home / 'checkout $HOME %u "quoted" \\ path'
        (self.root / "bin").mkdir(parents=True)
        (self.root / "bin/luna").touch()
        (self.root / "src/luna-polkit/src/shell").mkdir(parents=True)
        (self.root / "src/luna-polkit/src/shell/shell.qml").touch()
        self.unit = self.home / "config/systemd/user" / UNIT
        environment = {
            "HOME": str(self.home), "XDG_CONFIG_HOME": str(self.home / "config"),
            "XDG_RUNTIME_DIR": str(self.home / "runtime"), "WAYLAND_DISPLAY": "wayland-test",
            "XDG_SESSION_ID": "42", "LUNA_UI_THEME": '{"mode":"dark"}', "PATH": "/usr/bin",
        }
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, environment, clear=True).start()
        patch.object(SERVICE.shutil, "which", return_value="/usr/bin/mock").start()
        self.clock = 0
        patch.object(SERVICE.time, "sleep", side_effect=self.advance_clock).start()
        patch.object(SERVICE.time, "monotonic", side_effect=lambda: self.clock).start()
        patch.object(SERVICE, "run", side_effect=self.run_command).start()
        self.calls = []
        self.processes = {7: "/unrelated/shell.qml"}
        self.running = {UNIT: False, KDE: True}
        self.kde_state = "static"
        self.kde_loaded = "loaded"
        self.registered = True
        self.validation_error = False
        self.start_error = False
        self.import_error = False
        self.kill_error = False
        self.status_output = None
        self.skip_ipc = False
        self.stop_timeout = False

    def advance_clock(self, duration):
        self.clock += duration

    def run_command(self, arguments, check=True, environment=None, timeout=15):
        self.calls.append(arguments)
        code, output = 0, ""
        if arguments[0] == "systemctl":
            self.assertEqual(arguments[1], "--user")
            action, unit = arguments[2], arguments[-1]
            if action == "is-active":
                code = 0 if self.running[unit] else 3
            elif action == "show":
                if unit == "--value":
                    unit = arguments[3]
                if arguments[-2] == "--property=UnitFileState":
                    output = self.kde_state
                else:
                    output = self.kde_loaded if unit == KDE else ("loaded" if self.unit.exists() else "not-found")
            elif action == "mask":
                self.assertIn("--runtime", arguments)
                self.kde_state = "masked-runtime"
                self.running[KDE] = False
            elif action == "unmask":
                self.assertIn("--runtime", arguments)
                self.kde_state = "static"
            elif action == "import-environment" and self.import_error:
                code = 1
                output = "environment import failed"
            elif action == "start":
                if unit == UNIT and self.start_error:
                    code = 1
                    output = "agent startup failed"
                else:
                    self.running[unit] = True
                    if unit == UNIT:
                        self.processes[100] = str(SERVICE.shell_path(self.root))
            elif action == "stop":
                if unit == UNIT and self.stop_timeout:
                    raise subprocess.TimeoutExpired(arguments, timeout)
                self.running[unit] = False
                if unit == UNIT:
                    self.processes.pop(100, None)
        elif arguments[0] == "qs":
            if arguments[1] == "-p":
                self.assertEqual(arguments[2], str(SERVICE.shell_path(self.root)))
                if environment.get("LUNA_POLKIT_VALIDATE") == "1":
                    self.assertEqual(environment["LUNA_UI_THEME"], '{"mode":"dark"}')
                    self.assertEqual(environment["QML_IMPORT_PATH"], str(self.root / "src/qml"))
                    if self.validation_error:
                        code, output = 1, "Cannot load PolkitAgent"
                    else:
                        output = "Luna polkit validation passed"
                else:
                    self.processes[101] = str(SERVICE.shell_path(self.root))
            elif arguments[1] == "list":
                output = json.dumps([{"pid": pid, "config_path": path}
                                     for pid, path in self.processes.items()])
            elif arguments[1] == "kill":
                if self.kill_error:
                    code = 1
                else:
                    self.processes.pop(int(arguments[-1]), None)
            elif arguments[1] == "ipc":
                self.assertEqual(arguments[-3:], ["call", "auth", "status"])
                if self.skip_ipc or not any(Path(path).resolve() == SERVICE.shell_path(self.root)
                                           for path in self.processes.values()):
                    code = 1
                else:
                    output = self.status_output or ("running" if self.registered else "unavailable")
            else:
                self.fail(f"Unexpected Quickshell command: {arguments}")
        else:
            self.fail(f"Unexpected command: {arguments}")
        if code and check:
            raise RuntimeError(output or "command failed")
        return subprocess.CompletedProcess(arguments, code, stdout=output, stderr="")

    def call(self, *arguments):
        return ["systemctl", "--user", *arguments]

    def test_start_validates_then_transfers_and_waits_for_registration(self):
        SERVICE.activate(self.root)
        self.assertTrue(self.running[UNIT])
        self.assertFalse(self.running[KDE])
        self.assertEqual(self.kde_state, "masked-runtime")
        contents = self.unit.read_text()
        self.assertIn(" auth serve\n", contents)
        self.assertIn("Restart=on-failure", contents)
        self.assertIn("UnsetEnvironment=LUNA_INSTALL_DIR LUNA_POLKIT_VALIDATE LUNA_UI_THEME", contents)
        self.assertNotIn("--daemonize", contents)
        self.assertIn("$$HOME %%u", contents)
        self.assertIn('\\"quoted\\"', contents)
        self.assertIn("\\\\ path", contents)
        validation = next(index for index, call in enumerate(self.calls) if call[0] == "qs" and call[1] == "-p")
        mask = self.calls.index(self.call("mask", "--runtime", "--now", KDE))
        start = self.calls.index(self.call("start", UNIT))
        self.assertLess(validation, mask)
        self.assertLess(mask, start)
        self.assertIn("XDG_SESSION_ID", next(call for call in self.calls if "import-environment" in call))
        self.assertEqual(self.calls[-1][-1], "status")

    def test_repeated_start_preserves_process_and_unit_inode(self):
        SERVICE.activate(self.root)
        inode = self.unit.stat().st_ino
        self.calls.clear()
        SERVICE.activate(self.root)
        self.assertEqual(self.unit.stat().st_ino, inode)
        self.assertNotIn(self.call("start", UNIT), self.calls)
        self.assertNotIn(self.call("stop", UNIT), self.calls)
        self.assertNotIn(self.call("daemon-reload"), self.calls)
        self.assertEqual(set(self.processes), {7, 100})

    def test_restart_renews_only_luna_agent(self):
        SERVICE.activate(self.root)
        self.calls.clear()
        SERVICE.activate(self.root, restart=True)
        self.assertLess(self.calls.index(self.call("stop", UNIT)), self.calls.index(self.call("start", UNIT)))
        self.assertNotIn(self.call("start", KDE), self.calls)
        self.assertEqual(set(self.processes), {7, 100})

    def test_validation_failure_leaves_kde_and_unit_untouched(self):
        self.validation_error = True
        with self.assertRaisesRegex(RuntimeError, "Cannot load"):
            SERVICE.activate(self.root)
        self.assertTrue(self.running[KDE])
        self.assertEqual(self.kde_state, "static")
        self.assertFalse(self.unit.exists())
        self.assertFalse(any(call[0] == "systemctl" for call in self.calls))

    def test_missing_wayland_session_does_not_touch_providers(self):
        with patch.dict(os.environ, {"WAYLAND_DISPLAY": ""}):
            with self.assertRaisesRegex(RuntimeError, "Wayland login session"):
                SERVICE.activate(self.root)
            self.assertEqual(self.calls, [])

    def test_missing_session_id_leaves_session_resolution_to_polkit(self):
        os.environ.pop("XDG_SESSION_ID")
        SERVICE.activate(self.root)
        self.assertTrue(self.running[UNIT])

    def test_failed_takeover_restores_previous_unit_and_kde(self):
        self.unit.parent.mkdir(parents=True)
        self.unit.write_text("previous service\n")
        self.start_error = True
        with self.assertRaisesRegex(RuntimeError, "agent startup failed"):
            SERVICE.activate(self.root)
        self.assertEqual(self.unit.read_text(), "previous service\n")
        self.assertTrue(self.running[KDE])
        self.assertFalse(self.running[UNIT])
        self.assertEqual(self.kde_state, "static")

    def test_registration_failure_is_not_mistaken_for_service_success(self):
        self.registered = False
        with self.assertRaisesRegex(RuntimeError, "could not register"):
            SERVICE.activate(self.root)
        self.assertTrue(self.running[KDE])
        self.assertFalse(self.running[UNIT])
        self.assertFalse(self.unit.exists())
        self.assertEqual(self.kde_state, "static")
        self.assertAlmostEqual(self.clock, 12)

    def test_timed_out_cleanup_does_not_prevent_restoring_kde(self):
        self.unit.parent.mkdir(parents=True)
        self.unit.write_text("previous service\n")
        self.start_error = True
        self.stop_timeout = True
        warning = io.StringIO()
        with patch("sys.stderr", warning), self.assertRaisesRegex(RuntimeError, "agent startup failed"):
            SERVICE.activate(self.root)
        self.assertEqual(self.unit.read_text(), "previous service\n")
        self.assertTrue(self.running[KDE])
        self.assertEqual(self.kde_state, "static")
        self.assertIn("recovery could not stop Luna authentication", warning.getvalue())
        self.assertIn(self.call("start", KDE), self.calls)

    def test_unresponsive_ipc_cannot_extend_the_registration_deadline(self):
        def unresponsive(root, timeout):
            self.advance_clock(timeout)
            raise subprocess.TimeoutExpired("qs", timeout)

        with patch.object(SERVICE, "ipc_status", side_effect=unresponsive):
            with self.assertRaisesRegex(RuntimeError, "could not register"):
                SERVICE.wait_registered(self.root)
        self.assertAlmostEqual(self.clock, 12)

    def test_existing_kde_mask_survives_failed_start(self):
        self.kde_state = "masked"
        self.kde_loaded = "masked"
        self.running[KDE] = False
        self.start_error = True
        with self.assertRaises(RuntimeError):
            SERVICE.activate(self.root)
        self.assertEqual(self.kde_state, "masked")
        self.assertFalse(any("unmask" in call or "mask" in call for call in self.calls))

    def test_missing_kde_service_does_not_create_a_mask(self):
        self.kde_loaded, self.kde_state = "not-found", ""
        self.running[KDE] = False
        SERVICE.activate(self.root)
        self.assertFalse(any("mask" in call for call in self.calls))
        self.assertTrue(self.running[UNIT])

    def test_import_failure_does_not_stop_an_existing_luna_service(self):
        SERVICE.activate(self.root)
        self.calls.clear()
        self.import_error = True
        with self.assertRaisesRegex(RuntimeError, "environment import failed"):
            SERVICE.activate(self.root, restart=True)
        self.assertTrue(self.running[UNIT])
        self.assertNotIn(self.call("stop", UNIT), self.calls)
        self.assertIn(100, self.processes)

    def test_duplicate_and_symlink_instances_are_scoped_and_stopped(self):
        alias = self.home / "linked-checkout"
        alias.symlink_to(self.root)
        self.processes.update({20: str(SERVICE.shell_path(self.root)),
                               21: str(alias / "src/luna-polkit/src/shell/shell.qml")})
        SERVICE.activate(self.root)
        self.assertIn(["qs", "kill", "--pid", "20"], self.calls)
        self.assertIn(["qs", "kill", "--pid", "21"], self.calls)
        self.assertEqual(set(self.processes), {7, 100})

    def test_failed_takeover_restores_standalone_luna(self):
        self.processes[20] = str(SERVICE.shell_path(self.root))
        self.start_error = True
        with self.assertRaises(RuntimeError):
            SERVICE.activate(self.root)
        self.assertIn(101, self.processes)
        self.assertTrue(self.running[KDE])
        self.assertFalse(self.unit.exists())

    def test_stop_is_repeatable_and_requires_neither_theme_nor_session(self):
        SERVICE.activate(self.root)
        self.processes[20] = str(SERVICE.shell_path(self.root))
        with patch.dict(os.environ, {"WAYLAND_DISPLAY": "", "XDG_SESSION_ID": "", "LUNA_UI_THEME": "invalid"}):
            SERVICE.stop(self.root)
            SERVICE.stop(self.root)
        self.assertEqual(set(self.processes), {7})
        self.assertFalse(self.running[UNIT])
        self.assertEqual(self.kde_state, "masked-runtime")

    def test_failed_instance_shutdown_aborts_takeover(self):
        self.processes[20] = str(SERVICE.shell_path(self.root))
        self.kill_error = True
        with self.assertRaisesRegex(RuntimeError, "Could not stop"):
            SERVICE.activate(self.root)
        self.assertTrue(self.running[KDE])
        self.assertEqual(self.kde_state, "static")
        self.assertNotIn(self.call("start", UNIT), self.calls)

    def test_status_uses_registration_and_never_changes_services(self):
        self.assertEqual(SERVICE.status(self.root), "stopped")
        self.running[UNIT] = True
        self.assertEqual(SERVICE.status(self.root), "unavailable")
        self.processes[100] = str(SERVICE.shell_path(self.root))
        self.registered = False
        self.assertEqual(SERVICE.status(self.root), "unavailable")
        self.status_output = "false"
        self.assertEqual(SERVICE.status(self.root), "unavailable")
        self.status_output = "running"
        self.assertEqual(SERVICE.status(self.root), "running")
        self.assertFalse(any(call[0] == "systemctl" and call[2] != "is-active" for call in self.calls))
        self.assertFalse(self.unit.exists())


class AuthCliTests(unittest.TestCase):
    def test_actions_dispatch_and_validate_theme_before_mutation(self):
        script = '''
local root, action = arg[1], arg[2]
local original_dofile = dofile
local commands, snapshots, served = {}, 0, false
_G.dofile = function(path)
    if path:match("/lib/quickshell%.lua$") then
        return function(common, checkout, renderer, target)
            assert(target == "auth" and renderer:match("luna%-polkit/src/shell$"))
            return {run = function(value) assert(value == "serve"); served = true end}
        end
    elseif path:match("/lib/theme/shell%.lua$") then
        return function()
            return {snapshot = function()
                snapshots = snapshots + 1
                if arg[3] == "invalid" then error("invalid theme") end
                return "theme snapshot"
            end}
        end
    end
    return original_dofile(path)
end
local common = {run = function(command) table.insert(commands, command) end}
local auth = dofile(root .. "/src/luna-cli/auth/init.lua")(common, root .. "/src/luna-cli/auth")
local parser = require("argparse")("luna")
auth.register(parser)
local options = parser:parse(action == "default" and {"auth"} or {"auth", action})
local ok, message = pcall(auth.run, options)
local starts = action == "start" or action == "restart" or action == "default"
if arg[3] == "invalid" then
    assert(not ok and message:find("invalid theme", 1, true) and #commands == 0)
else
    assert(ok, message)
    assert(snapshots == (starts and 1 or 0))
    if action == "serve" then
        assert(served and #commands == 0)
    else
        assert(#commands == 1)
        local command = commands[1]
        assert(command[#command] == (action == "default" and "start" or action))
        if starts then
            assert(command[1] == "env" and command[2] == "LUNA_UI_THEME=theme snapshot" and command[3] == "python")
        else
            assert(command[1] == "python")
        end
    end
end
'''
        for action in ("default", "start", "restart", "status", "stop", "serve"):
            for invalid in ((False, True) if action in ("start", "restart") else (False,)):
                with self.subTest(action=action, invalid=invalid):
                    args = ["lua", "-E", "-", str(REPO), action] + (["invalid"] if invalid else [])
                    result = subprocess.run(args, input=script, capture_output=True, text=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
