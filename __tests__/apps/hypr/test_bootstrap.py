"""Capture Hyprland startup through Lua stubs and exercise only mocked Keyring tools."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]
ENTRY = REPO / 'apps/hypr/config/hyprland.lua'


@unittest.skipUnless(Path('/usr/bin/lua').is_file(), 'The bootstrap requires Lua')
class BootstrapKeyringTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna bootstrap '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.calls_file = self.root / 'calls.jsonl'
        self.installed = self.root / "installed Hyprland's config"
        (self.installed / 'generated').mkdir(parents=True)
        shutil.copy2(ENTRY, self.installed / 'hyprland.lua')
        shutil.copy2(ENTRY.parent / 'autostart.lua', self.installed / 'autostart.lua')
        subprocess.run(
            ['/usr/bin/lua', '-E', str(REPO / 'scripts/setup/build-app.lua'),
             str(REPO / 'apps/hypr'), str(self.installed), str(self.installed),
             str(self.root / 'config/luna')],
            cwd=self.root, text=True, capture_output=True, check=True,
        )
        (self.bin / 'readlink').symlink_to(shutil.which('readlink'))
        self.env = {
            'PATH': str(self.bin), 'HOME': str(self.root / 'home'), 'ENV': '',
            'BASH_ENV': '', 'TEST_KEYRING_CALLS': str(self.calls_file),
            'DISPLAY': ':73', 'WAYLAND_DISPLAY': 'wayland-test',
            'XDG_CURRENT_DESKTOP': 'Hyprland',
        }

        # Load only the entry, startup module and generated paths. Other modules
        # are inert handlers; registering or dispatching never executes a command.
        capture = '''
local load = dofile
local json = dofile(arg[2] .. "/lib/theme/json.lua")
local root = arg[2]
local config_dir = arg[3]
local callbacks, commands = {}, {}
dofile = function(path)
    if path == root .. "/lib/theme/resolved.lua" then
        return function() return {} end
    elseif path == config_dir .. "/generated/paths.lua"
        or path == config_dir .. "/autostart.lua" then
        return load(path)
    elseif path == config_dir .. "/theme.lua" then
        return function() return { apply = function() end } end
    elseif path == config_dir .. "/bindings.lua" then
        return function() end
    elseif path == config_dir .. "/monitors.lua"
        or path == config_dir .. "/workspaces.lua"
        or path == config_dir .. "/input.lua"
        or path == config_dir .. "/rules.lua"
        or path == config_dir .. "/animations.lua" then
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
load(arg[1])
assert(#commands == 0, "Startup ran before the Hyprland start event")
assert(callbacks["hyprland.start"], "Missing Hyprland startup callback")()
print(json.encode(commands, true))
'''
        result = subprocess.run(
            ['/usr/bin/lua', '-E', '-', str(self.installed / 'hyprland.lua'), str(REPO), str(self.installed)],
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
        # PATH contains the two mocks and readlink; no Luna command or real
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
