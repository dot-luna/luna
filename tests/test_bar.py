"""Check bar lifecycle and theme snapshots without starting a desktop shell."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]


class BarTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luna bar '")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        tools = self.root / 'bin'
        tools.mkdir()
        self.env = dict(os.environ, PATH=str(tools) + ':' + os.environ['PATH'],
                        XDG_CONFIG_HOME=str(self.root / 'config'),
                        XDG_DATA_HOME=str(self.root / 'data'), WAYLAND_DISPLAY='test',
                        TEST_ROOT=str(self.root))
        mock = tools / 'qs'
        mock.write_text('''#!/usr/bin/python3
import json, os, pathlib, sys
root = pathlib.Path(os.environ['TEST_ROOT'])
args = sys.argv[1:]
with (root / 'commands').open('a') as out:
    out.write(json.dumps({'args': args, 'theme': os.getenv('LUNA_UI_THEME'), 'bar': os.getenv('LUNA_BAR_CONFIG')}) + '\\n')
running = root / 'running'
if args[0] == 'ipc':
    if not running.exists():
        sys.exit(1)
    if args[-1] == 'stop':
        running.unlink()
    print('ready')
else:
    running.touch()
''')
        mock.chmod(0o755)
        gsettings = tools / 'gsettings'
        gsettings.write_text("#!/bin/sh\nprintf \"'24h'\\n\"\n")
        gsettings.chmod(0o755)

    def cli(self, *args, ok=True):
        result = subprocess.run([str(REPO / 'bin/luna'), 'bar', *args], env=self.env,
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return result

    def commands(self):
        return [json.loads(line) for line in (self.root / 'commands').read_text().splitlines()]

    def selected_theme(self):
        theme = self.root / 'data/luna/themes/custom'
        shutil.copytree(REPO / 'themes/bundled/tokyo-night', theme)
        selection = self.root / 'config/luna/theme'
        selection.parent.mkdir(parents=True, exist_ok=True)
        selection.write_text('custom\n')
        self.publish(theme)
        return theme

    def publish(self, theme):
        script = """
local root, directory, path = arg[1], arg[2], arg[3]
local resolved = dofile(root .. '/lib/theme/resolved.lua')(root)
local validate = dofile(root .. '/lib/theme/validate.lua')()
local file = assert(io.open(path, 'w'))
file:write(resolved.encode(resolved.resolve(validate.load(directory), 'custom')))
file:close()
"""
        subprocess.run(['lua', '-E', '-', str(REPO), str(theme),
                        str(self.root / 'config/luna/theme.json')], input=script,
                       env=self.env, text=True, capture_output=True, check=True)

    def test_fallback_and_keyboard_entry(self):
        self.cli('focus')
        calls = self.commands()
        launch = next(call for call in calls if call['args'][0] == '-p')
        self.assertEqual(json.loads(launch['theme'])['colors']['accent'], '#7aa2f7')
        self.assertEqual(Path(launch['args'][1]).resolve(), REPO / 'src/luna-bar')
        self.assertTrue((Path(launch['args'][1]) / 'shell.qml').is_file())
        self.assertEqual(calls[-1]['args'][-1], 'focus')
        self.cli('controls')
        self.assertEqual(self.commands()[-1]['args'][-1], 'controls')

    def test_service_entry_runs_foreground(self):
        self.cli('serve')
        launch = self.commands()[-1]
        self.assertEqual(launch['args'][0], '-p')
        self.assertIn('--no-duplicate', launch['args'])
        self.assertNotIn('--daemonize', launch['args'])

    def test_managed_reload_and_stop_use_service(self):
        unit = self.root / 'config/systemd/user/luna-notifications.service'
        unit.parent.mkdir(parents=True)
        unit.write_text('[Service]\n')
        systemctl = self.root / 'bin/systemctl'
        systemctl.write_text('''#!/usr/bin/python3
import os, pathlib, sys
root = pathlib.Path(os.environ['TEST_ROOT'])
with (root / 'service-commands').open('a') as log:
    log.write(' '.join(sys.argv[1:]) + '\\n')
if sys.argv[2] == 'restart':
    (root / 'running').touch()
elif sys.argv[2] == 'stop':
    (root / 'running').unlink(missing_ok=True)
''')
        systemctl.chmod(0o755)
        self.cli('reload')
        self.cli('stop')
        self.assertEqual((self.root / 'service-commands').read_text().splitlines(),
                         ['--user restart luna-notifications.service', '--user stop luna-notifications.service'])
        self.assertFalse(any(call['args'][0] == '-p' for call in self.commands()))

    def test_invalid_theme_preserves_managed_service(self):
        self.selected_theme()
        unit = self.root / 'config/systemd/user/luna-notifications.service'
        unit.parent.mkdir(parents=True)
        unit.write_text('[Service]\n')
        systemctl = self.root / 'bin/systemctl'
        systemctl.write_text('''#!/usr/bin/python3
import os, pathlib
(pathlib.Path(os.environ['TEST_ROOT']) / 'service-called').touch()
''')
        systemctl.chmod(0o755)
        (self.root / 'config/luna/theme.json').write_text('invalid theme')
        self.cli('reload', ok=False)
        self.assertFalse((self.root / 'service-called').exists())

    def test_reload_fresh_snapshot_and_stop(self):
        theme = self.selected_theme()
        (theme / 'hyprland.lua').write_text('return { decoration = { rounding = 8, active_opacity = 0.9 } }')
        self.cli()
        colors = theme / 'colors.lua'
        colors.write_text(colors.read_text().replace('#7aa2f7', '#82aaff'))
        self.cli('reload')
        unchanged = next(call for call in reversed(self.commands()) if call['args'][0] == '-p')
        self.assertEqual(json.loads(unchanged['theme'])['colors']['accent'], '#7aa2f7')
        self.publish(theme)
        self.cli('reload')
        calls = self.commands()
        launch = next(call for call in reversed(calls) if call['args'][0] == '-p')
        payload = json.loads(launch['theme'])
        self.assertEqual(payload['colors']['accent'], '#82aaff')
        self.assertEqual(payload['hyprland']['decoration']['rounding'], 8)
        self.assertEqual(payload['hyprland']['decoration']['active_opacity'], 0.9)
        self.assertTrue(any(call['args'][-1] == 'stop' for call in calls))
        self.cli('stop')
        self.cli('stop')
        self.assertFalse((self.root / 'running').exists())
        self.assertEqual({p.name for p in (self.root / 'config/luna').iterdir()}, {'theme', 'theme.json', 'bar.json'})

    def test_workspace_preferences_and_svg_paths(self):
        self.cli()
        config = self.root / 'config/luna/bar.json'
        self.assertEqual(json.loads(config.read_text())['workspaces']['inactive'], {'type': 'dot', 'size': 5})
        icon = config.parent / 'active #1.svg'
        icon.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12"><circle cx="6" cy="6" r="5"/></svg>')
        preferences = {'workspaces': {'active': {'type': 'icon', 'path': icon.name},
                                      'inactive': {'type': 'label', 'label': '◆ {number} 🌙'}}}
        config.write_text(json.dumps(preferences))
        self.cli('reload')
        launch = next(call for call in reversed(self.commands()) if call['args'][0] == '-p')
        result = json.loads(launch['bar'])['workspaces']
        self.assertEqual(result['active']['source'], icon.as_uri())
        self.assertEqual(result['active']['size'], 14)
        self.assertEqual(result['inactive']['label'], '◆ {number} 🌙')
        self.assertEqual(json.loads(config.read_text()), preferences)

    def test_per_workspace_bundled_icons(self):
        self.cli()
        launch = next(call for call in self.commands() if call['args'][0] == '-p')
        overrides = json.loads(launch['bar'])['workspaces']['overrides']
        self.assertEqual(set(overrides), {'1', '2', '3', '0'})
        for workspace, icon in {'1': 'code-xml', '2': 'terminal', '3': 'globe', '0': 'bot'}.items():
            self.assertEqual(overrides[workspace]['source'], (REPO / 'src/qml/Luna/icons' / (icon + '.svg')).as_uri())
        config = self.root / 'config/luna/bar.json'
        config.write_text('{"workspaces":{"overrides":{"0":{"type":"icon","icon":"missing"}}}}')
        count = len(self.commands())
        self.cli('reload', ok=False)
        self.assertEqual(len(self.commands()), count)
        self.assertTrue((self.root / 'running').exists())

    def test_invalid_preferences_preserve_bar(self):
        self.cli()
        count = len(self.commands())
        config = self.root / 'config/luna/bar.json'
        for invalid in ('not json', '{"workspaces":{"active":{"type":"unknown"}}}',
                        '{"workspaces":{"inactive":{"type":"icon","path":"missing.svg"}}}',
                        '{"workspaces":{"active":{"size":0}}}',
                        '{"workspaces":{"active":{"type":"label"}}}'):
            config.write_text(invalid)
            self.cli('reload', ok=False)
            self.assertEqual(len(self.commands()), count)
            self.assertTrue((self.root / 'running').exists())
        self.cli('stop')
        self.assertFalse((self.root / 'running').exists())

    def test_clock_configuration(self):
        self.cli()
        config = self.root / 'config/luna/bar.json'
        preferences = {'clock': {'use_24_hour': False, 'week_start': 0,
                                 'world_clocks': [{'label': 'Kathmandu', 'timezone': 'Asia/Kathmandu'}]}}
        config.write_text(json.dumps(preferences))
        self.cli('reload')
        launch = next(call for call in reversed(self.commands()) if call['args'][0] == '-p')
        clock = json.loads(launch['bar'])['clock']
        self.assertFalse(clock['use_24_hour'])
        self.assertEqual(clock['week_start'], 0)
        self.assertIn('AP', clock['format'])
        self.assertEqual(clock['world_clocks'], preferences['clock']['world_clocks'])
        count = len(self.commands())
        preferences['clock']['world_clocks'][0]['timezone'] = 'Invalid/Zone'
        config.write_text(json.dumps(preferences))
        self.cli('reload', ok=False)
        self.assertEqual(len(self.commands()), count)
        config.write_text('{"clock":{"world_clocks":[]}}')
        self.cli('reload')
        launch = next(call for call in reversed(self.commands()) if call['args'][0] == '-p')
        self.assertEqual(json.loads(launch['bar'])['clock']['world_clocks'], [])

    def test_secondary_calendar_configuration(self):
        self.cli()
        config = self.root / 'config/luna/bar.json'
        launch = next(call for call in reversed(self.commands()) if call['args'][0] == '-p')
        self.assertEqual(json.loads(launch['bar'])['clock']['secondary_calendar'], 'bs')
        config.write_text('{"clock":{"secondary_calendar":"none"}}')
        self.cli('reload')
        launch = next(call for call in reversed(self.commands()) if call['args'][0] == '-p')
        self.assertEqual(json.loads(launch['bar'])['clock']['secondary_calendar'], 'none')
        for invalid in ('unknown', False, []):
            config.write_text(json.dumps({'clock': {'secondary_calendar': invalid}}))
            count = len(self.commands())
            self.cli('reload', ok=False)
            self.assertEqual(len(self.commands()), count)

    def test_system_clock_format(self):
        gsettings = self.root / 'bin/gsettings'
        for preference, expected in [('12h', False), ('24h', True)]:
            gsettings.write_text("#!/bin/sh\nprintf \"'%s'\\n\"\n" % preference)
            self.cli('reload')
            launch = next(call for call in reversed(self.commands()) if call['args'][0] == '-p')
            clock = json.loads(launch['bar'])['clock']
            self.assertEqual(clock['use_24_hour'], expected)
            self.assertEqual('AP' in clock['format'], not expected)
            self.assertNotIn('Europe/London', [city['timezone'] for city in clock['world_clocks']])

    def test_invalid_theme_preserves_running_bar(self):
        theme = self.selected_theme()
        self.cli()
        count = len(self.commands())
        output = self.root / 'config/luna/theme.json'
        original = output.read_text()
        for invalid in ('not json', '{}', original.replace('"rounding":0', '"rounding":-1')):
            output.write_text(invalid)
            self.cli('reload', ok=False)
            self.assertEqual(len(self.commands()), count)
            self.assertTrue((self.root / 'running').exists())
        (self.root / 'config/luna/theme').write_text('../escape\n')
        self.cli('reload', ok=False)
        self.assertEqual(len(self.commands()), count)


if __name__ == '__main__':
    unittest.main()
