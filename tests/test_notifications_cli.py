"""Verify notification activation using isolated files and fake session commands."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
SERVICE = REPO / "src/luna-cli/notifications/service.py"
UNIT = "luna-notifications.service"


class NotificationCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luna notifications '")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tools = self.root / "bin"
        self.tools.mkdir()
        self.env = dict(os.environ, HOME=str(self.root), TEST_ROOT=str(self.root),
                        XDG_CONFIG_HOME=str(self.root / "config"),
                        XDG_DATA_HOME=str(self.root / "data"),
                        XDG_RUNTIME_DIR=str(self.root / "runtime"),
                        WAYLAND_DISPLAY="wayland-test", HYPRLAND_INSTANCE_SIGNATURE="hypr-test",
                        PATH=str(self.tools) + ":" + os.environ["PATH"])
        self.env.pop("LUNA_PATH", None)
        self.unit = self.root / "config/systemd/user" / UNIT
        self.activation = self.root / "data/dbus-1/services/org.freedesktop.Notifications.service"
        mock = '''#!/usr/bin/python3
import json, os, pathlib, sys
root = pathlib.Path(os.environ['TEST_ROOT'])
name, args = pathlib.Path(sys.argv[0]).name, sys.argv[1:]
with (root / 'commands').open('a') as file:
    file.write(json.dumps([name, *args]) + '\\n')
active, dunst, mask, bar = [root / name for name in ('active', 'dunst', 'mask', 'bar')]
if name == 'systemctl':
    assert args[0] == '--user'
    action, values = args[1], args[2:]
    if action == 'is-active':
        sys.exit(0 if (active if values[-1] == 'luna-notifications.service' else dunst).exists() else 3)
    if action == 'show':
        print('masked' if mask.exists() else 'static')
    elif action == 'mask':
        mask.touch()
        dunst.unlink(missing_ok=True)
    elif action == 'unmask':
        mask.unlink(missing_ok=True)
    elif action in ('start', 'restart'):
        if values[-1] == 'dunst.service':
            dunst.touch()
        else:
            if os.getenv('FAIL_START'):
                print('Mock notification startup failed', file=sys.stderr)
                sys.exit(1)
            active.touch()
            bar.touch()
    elif action == 'stop' and values[-1] == 'luna-notifications.service':
        active.unlink(missing_ok=True)
        bar.unlink(missing_ok=True)
elif name == 'qs':
    if args[0] == 'ipc':
        if not bar.exists(): sys.exit(1)
        if args[-1] == 'stop': bar.unlink()
        print('{"running":true,"count":2,"dnd":false}' if args[-1] == 'notificationStatus' else 'ready')
    else:
        bar.touch()
elif name == 'luna':
    assert args == ['bar', 'start']
    bar.touch()
elif name == 'gsettings':
    print("'24h'")
'''
        for name in ("systemctl", "busctl", "qs", "luna", "gsettings"):
            path = self.tools / name
            path.write_text(mock)
            path.chmod(0o755)

    def commands(self):
        path = self.root / "commands"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def setup(self, root=REPO, ok=True):
        result = subprocess.run(["python", str(SERVICE), str(root)], env=self.env,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return result

    def cli(self, action=None, ok=True):
        # Load only this module so unrelated CLI registration changes cannot affect the test.
        script = '''
local common = dofile(arg[1] .. '/lib/common.lua')
local module = dofile(arg[1] .. '/src/luna-cli/notifications/init.lua')(common, arg[1] .. '/src/luna-cli/notifications')
local parser = require('argparse')('luna')
module.register(parser)
local arguments = {'notifications'}
if arg[2] then table.insert(arguments, arg[2]) end
module.run(parser:parse(arguments))
'''
        args = ["lua", "-E", "-", str(REPO)] + ([action] if action else [])
        result = subprocess.run(args, env=self.env, input=script, capture_output=True,
                                text=True, timeout=15)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return result

    def test_setup_installs_foreground_activation_and_transfers_ownership(self):
        (self.root / "dunst").touch()
        (self.root / "bar").touch()
        self.setup()
        self.assertIn("Type=dbus", self.unit.read_text())
        self.assertIn("BusName=org.freedesktop.Notifications", self.unit.read_text())
        self.assertIn(f'ExecStart="{REPO}/bin/luna" bar serve', self.unit.read_text())
        self.assertIn("Restart=on-failure", self.unit.read_text())
        self.assertIn("SystemdService=" + UNIT, self.activation.read_text())
        self.assertNotIn("--daemonize", self.unit.read_text())
        self.assertTrue((self.root / "active").exists())
        self.assertFalse((self.root / "dunst").exists())
        calls = self.commands()
        stop_bar = next(i for i, call in enumerate(calls) if call[0] == "qs" and call[-1] == "stop")
        mask = calls.index(["systemctl", "--user", "mask", "--now", "dunst.service"])
        start = calls.index(["systemctl", "--user", "start", UNIT])
        self.assertLess(stop_bar, mask)
        self.assertLess(mask, start)
        self.assertTrue(any(call[0] == "busctl" and call[-1] == "ReloadConfig" for call in calls))
        environment = next(call for call in calls if "import-environment" in call)
        self.assertIn("WAYLAND_DISPLAY", environment)
        self.assertIn("HYPRLAND_INSTANCE_SIGNATURE", environment)

    def test_repeated_setup_preserves_active_bar_and_unit_files(self):
        self.setup()
        inode = self.unit.stat().st_ino
        count = len(self.commands())
        self.setup()
        calls = self.commands()[count:]
        self.assertEqual(self.unit.stat().st_ino, inode)
        self.assertFalse(any(call[0] == "qs" for call in calls))
        self.assertNotIn(["systemctl", "--user", "daemon-reload"], calls)
        self.assertNotIn(["systemctl", "--user", "restart", UNIT], calls)

    def test_failed_takeover_restores_previous_files_and_dunst(self):
        self.unit.parent.mkdir(parents=True)
        self.unit.write_text("previous service\n")
        self.activation.parent.mkdir(parents=True)
        self.activation.write_text("previous activation\n")
        (self.root / "dunst").touch()
        self.env["FAIL_START"] = "1"
        result = self.setup(ok=False)
        self.assertIn("Mock notification startup failed", result.stderr)
        self.assertEqual(self.unit.read_text(), "previous service\n")
        self.assertEqual(self.activation.read_text(), "previous activation\n")
        self.assertTrue((self.root / "dunst").exists())
        self.assertFalse((self.root / "mask").exists())

    def test_failed_initial_setup_removes_generated_files_and_preserves_existing_mask(self):
        (self.root / "mask").touch()
        self.env["FAIL_START"] = "1"
        self.setup(ok=False)
        self.assertFalse(self.unit.exists())
        self.assertFalse(self.activation.exists())
        self.assertTrue((self.root / "mask").exists())
        self.assertNotIn(["systemctl", "--user", "unmask", "dunst.service"], self.commands())

    def test_exec_paths_escape_systemd_expansion_without_shell_execution(self):
        checkout = self.root / 'checkout $HOME %u "quoted" \\ path'
        (checkout / "bin").mkdir(parents=True)
        shutil.copy2(self.tools / "luna", checkout / "bin/luna")
        self.setup(root=checkout)
        unit = self.unit.read_text()
        self.assertIn("$$HOME %%u", unit)
        self.assertIn('\\"quoted\\"', unit)
        self.assertIn("\\\\ path", unit)
        self.assertIn("$HOME %u", self.activation.read_text())

    def test_status_does_not_install_or_start_any_service(self):
        result = self.cli("status")
        self.assertEqual(json.loads(result.stdout), {"running": False})
        self.assertEqual({call[0] for call in self.commands()}, {"qs"})
        self.assertFalse(self.unit.exists())
        (self.root / "bar").touch()
        self.assertEqual(json.loads(self.cli("status").stdout)["count"], 2)

    def test_ui_commands_start_provider_then_route_to_bar_ipc(self):
        for action, method in ((None, "notifications"), ("dnd", "dnd"), ("clear", "clearNotifications")):
            with self.subTest(action=action):
                self.cli(action)
                self.assertEqual(self.commands()[-1][-1], method)
        self.assertTrue(self.unit.exists())

    def test_invalid_preferences_and_missing_session_preserve_existing_provider(self):
        self.env.pop("WAYLAND_DISPLAY")
        self.setup(ok=False)
        self.assertFalse(self.commands())
        self.env["WAYLAND_DISPLAY"] = "wayland-test"
        preferences = self.root / "config/luna/bar.json"
        preferences.parent.mkdir(parents=True)
        preferences.write_text("invalid JSON")
        self.cli("setup", ok=False)
        self.assertFalse(self.commands())
        self.assertFalse(self.unit.exists())


if __name__ == "__main__":
    unittest.main()
