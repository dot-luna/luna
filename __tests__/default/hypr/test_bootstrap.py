"""Capture Hyprland startup through Lua stubs and exercise only mocked Keyring tools."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]
BOOTSTRAP = REPO / 'default/hypr/bootstrap.lua'


@unittest.skipUnless(Path('/usr/bin/lua').is_file(), 'The bootstrap requires Lua')
class BootstrapKeyringTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna bootstrap '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.calls_file = self.root / 'calls.jsonl'
        self.env = {
            'PATH': str(self.bin), 'HOME': str(self.root / 'home'), 'ENV': '',
            'BASH_ENV': '', 'TEST_KEYRING_CALLS': str(self.calls_file),
            'DISPLAY': ':73', 'WAYLAND_DISPLAY': 'wayland-test',
            'XDG_CURRENT_DESKTOP': 'Hyprland',
        }

        # Load only the real bootstrap. Its dependencies and Hyprland API are
        # inert handlers; registering or dispatching a command never executes it.
        capture = '''
local bootstrap = dofile(arg[1])
local json = dofile(arg[2] .. "/lib/theme/json.lua")
local root = arg[3]
local callbacks, commands = {}, {}
dofile = function(path)
    if path == root .. "/lib/theme/resolved.lua" then
        return function() return {} end
    elseif path == root .. "/default/hypr/theme.lua" then
        return function() return { apply = function() end } end
    elseif path == root .. "/default/hypr/bindings.lua" then
        return function() end
    elseif path == root .. "/default/hypr/monitors.lua"
        or path == root .. "/default/hypr/workspaces.lua"
        or path == root .. "/default/hypr/animations.lua" then
        return
    end
    error("Unexpected bootstrap dependency: " .. path)
end
hl = {
    layer_rule = function() end,
    window_rule = function() end,
    on = function(event, callback) callbacks[event] = callback end,
    dsp = { exec_cmd = function(command) return command end },
    dispatch = function(command) commands[#commands + 1] = command end,
}
bootstrap(root)
assert(#commands == 0, "Startup ran before the Hyprland start event")
assert(callbacks["hyprland.start"], "Missing Hyprland startup callback")()
print(json.encode(commands, true))
'''
        result = subprocess.run(
            ['/usr/bin/lua', '-E', '-', str(BOOTSTRAP), str(REPO), str(self.root / "Luna's checkout")],
            input=capture, cwd=self.root, env=self.env, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.commands = json.loads(result.stdout)
        keyring_commands = [command for command in self.commands if 'gnome-keyring-daemon' in command]
        self.assertEqual(len(keyring_commands), 1)
        self.keyring_command = keyring_commands[0]

        backend = f'#!{sys.executable}\n' + '''
import json, os, pathlib, sys
tool = pathlib.Path(sys.argv[0]).name
with open(os.environ['TEST_KEYRING_CALLS'], 'a') as output:
    output.write(json.dumps([tool, *sys.argv[1:]]) + '\\n')
if tool == 'dbus-update-activation-environment':
    sys.exit(int(os.environ.get('TEST_IMPORT_FAILURE', '0')))
if tool == 'gnome-keyring-daemon':
    if sys.argv[1:] != ['--start', '--components=secrets,pkcs11']:
        sys.exit('Startup must not replace the daemon or supply an unlock password')
'''
        for name in ('gnome-keyring-daemon', 'dbus-update-activation-environment'):
            tool = self.bin / name
            tool.write_text(backend)
            tool.chmod(0o755)

    def run_keyring_startup(self):
        # The closed PATH contains just the two mocks; no Luna command or real
        # service manager is reachable, even when a tool is intentionally absent.
        return subprocess.run(['/bin/sh', '-c', self.keyring_command],
                              cwd=self.root, env=self.env, input='', capture_output=True,
                              text=True, timeout=10)

    def calls(self):
        if not self.calls_file.exists():
            return []
        return [json.loads(line) for line in self.calls_file.read_text().splitlines()]

    def test_imports_graphical_environment_before_starting_secret_and_pkcs11_components(self):
        self.assertEqual(self.commands[0], self.keyring_command)
        self.assertTrue(any(command.endswith(' auth start') for command in self.commands[1:]))
        result = self.run_keyring_startup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.calls(), [
            ['dbus-update-activation-environment', '--systemd', 'DISPLAY',
             'WAYLAND_DISPLAY', 'XDG_CURRENT_DESKTOP'],
            ['gnome-keyring-daemon', '--start', '--components=secrets,pkcs11'],
        ])

    def test_missing_daemon_skips_environment_import_and_startup(self):
        (self.bin / 'gnome-keyring-daemon').unlink()
        result = self.run_keyring_startup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.calls(), [])

    def test_missing_environment_import_tool_still_starts_daemon(self):
        (self.bin / 'dbus-update-activation-environment').unlink()
        result = self.run_keyring_startup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.calls(), [
            ['gnome-keyring-daemon', '--start', '--components=secrets,pkcs11'],
        ])

    def test_environment_import_failure_does_not_prevent_daemon_initialization(self):
        self.env['TEST_IMPORT_FAILURE'] = '19'
        result = self.run_keyring_startup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([call[0] for call in self.calls()],
                         ['dbus-update-activation-environment', 'gnome-keyring-daemon'])
        self.assertEqual(self.calls()[-1],
                         ['gnome-keyring-daemon', '--start', '--components=secrets,pkcs11'])


if __name__ == '__main__':
    unittest.main()
