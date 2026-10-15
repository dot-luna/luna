"""Verify Settings receives the shared theme without opening a desktop window."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luna settings '")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.commands = self.root / 'commands'
        self.running = self.root / 'running'
        self.config = self.root / 'config/luna'
        self.config.mkdir(parents=True)
        tool = self.root / 'qs'
        tool.write_text('''#!/usr/bin/python3
import json, os, pathlib, sys
root = pathlib.Path(os.environ['TEST_SETTINGS_ROOT'])
args = sys.argv[1:]
call = {'args': args}
if args[0] != 'ipc':
    call['theme'] = os.environ.get('LUNA_UI_THEME')
    call['imports'] = os.environ.get('QML_IMPORT_PATH')
with (root / 'commands').open('a') as out:
    out.write(json.dumps(call) + '\\n')
running = root / 'running'
if args[0] == 'ipc':
    if not running.exists():
        sys.exit(1)
    if args[-1] == 'stop':
        running.unlink()
else:
    running.touch()
''')
        tool.chmod(0o755)
        self.extra_import = str(self.root / 'extra qml')
        self.env = dict(os.environ, PATH=str(self.root) + ':' + os.environ['PATH'],
                        TEST_SETTINGS_ROOT=str(self.root), WAYLAND_DISPLAY='test',
                        XDG_CONFIG_HOME=str(self.root / 'config'),
                        XDG_DATA_HOME=str(self.root / 'data'),
                        QML_IMPORT_PATH=self.extra_import)
        self.env.pop('LUNA_UI_THEME', None)

    def calls(self):
        if not self.commands.exists():
            return []
        return [json.loads(line) for line in self.commands.read_text().splitlines()]

    def cli(self, *args, ok=True):
        before = len(self.calls())
        result = subprocess.run([str(REPO / 'bin/luna'), 'settings', *args],
                                env=self.env, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return self.calls()[before:]

    def snapshot(self, calls):
        launches = [call for call in calls if call['args'][0] != 'ipc']
        self.assertEqual(len(launches), 1)
        launch = launches[0]
        args = launch['args']
        self.assertEqual(Path(args[args.index('-p') + 1]).resolve(), REPO / 'src/settings')
        self.assertIn('--no-duplicate', args)
        self.assertIn('--daemonize', args)
        imports = launch['imports'].split(':')
        self.assertEqual(Path(imports[0]).resolve(), REPO / 'src/qml')
        self.assertEqual(imports[1:], [self.extra_import])
        self.assertIsNotNone(launch['theme'], 'Settings must receive the resolved theme')
        return json.loads(launch['theme'])

    def test_default_theme_and_window_actions(self):
        calls = self.cli()
        theme = self.snapshot(calls)
        self.assertEqual(theme['name'], 'tokyo-night')
        self.assertEqual(theme['colors']['background'], '#1a1b26')
        self.assertEqual(theme['fonts']['ui'], 'Outfit')
        self.assertEqual(theme['hyprland']['decoration']['rounding'], 0)
        self.assertEqual(calls[-1]['args'][-2:], ['settings', 'open'])

        for action, method in [('open', 'open'), ('start', 'ping'), ('reload', 'ping')]:
            with self.subTest(action=action):
                calls = self.cli(action)
                self.assertEqual(self.snapshot(calls), theme)
                self.assertEqual(calls[-1]['args'][-2:], ['settings', method])
                if action == 'reload':
                    stop = next(index for index, call in enumerate(calls)
                                if call['args'][-1] == 'stop')
                    launch = next(index for index, call in enumerate(calls)
                                  if call['args'][0] != 'ipc')
                    self.assertLess(stop, launch)
                self.assertTrue(self.running.exists())

        calls = self.cli('stop')
        self.assertFalse(self.running.exists())
        self.assertTrue(all(call['args'][0] == 'ipc' for call in calls))
        self.assertIn('stop', [call['args'][-1] for call in calls])

    def test_active_theme_and_personal_font_reach_reloaded_window(self):
        theme = self.snapshot(self.cli())
        # Supply a complete resolved selection without applying a theme to the host desktop.
        theme['name'] = 'personal-light'
        theme['colors'].update(mode='light', background='#f4f1e8', foreground='#202024',
                               accent='#885533', selection='#ead9c4')
        theme['fonts'] = {'ui': 'Theme UI', 'mono': 'Theme Mono'}
        theme['hyprland']['decoration']['rounding'] = 14
        (self.config / 'theme').write_text(theme['name'] + '\n')
        (self.config / 'theme.json').write_text(json.dumps(theme))
        personal_font = 'Personal "UI" Font'
        (self.config / 'fonts.json').write_text(json.dumps({'ui': personal_font}))

        actual = self.snapshot(self.cli('reload'))
        expected = dict(theme, fonts={'ui': personal_font, 'mono': 'Theme Mono'})
        self.assertEqual(actual, expected)
        self.assertTrue(self.running.exists())

    def test_invalid_theme_preserves_running_window_and_allows_stop(self):
        self.cli()
        (self.config / 'theme').write_text('broken\n')
        (self.config / 'theme.json').write_text('{invalid JSON')

        self.assertEqual(self.cli('reload', ok=False), [])
        self.assertTrue(self.running.exists())
        self.cli('stop')
        self.assertFalse(self.running.exists())


if __name__ == '__main__':
    unittest.main()
