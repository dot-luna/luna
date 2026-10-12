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
    out.write(json.dumps({'args': args, 'theme': os.getenv('LUNA_UI_THEME')}) + '\\n')
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
        selection.parent.mkdir(parents=True)
        selection.write_text('custom\n')
        return theme

    def test_fallback_and_keyboard_entry(self):
        self.cli('focus')
        calls = self.commands()
        launch = next(call for call in calls if call['args'][0] == '-p')
        self.assertEqual(json.loads(launch['theme'])['colors']['accent'], '#7aa2f7')
        self.assertEqual(calls[-1]['args'][-1], 'focus')
        self.cli('controls')
        self.assertEqual(self.commands()[-1]['args'][-1], 'controls')

    def test_reload_fresh_snapshot_and_stop(self):
        theme = self.selected_theme()
        (theme / 'bar.lua').write_text('return { height = 40, rounding = 8, opacity = 0.9 }')
        self.cli()
        colors = theme / 'colors.lua'
        colors.write_text(colors.read_text().replace('#7aa2f7', '#82aaff'))
        self.cli('reload')
        calls = self.commands()
        launch = next(call for call in reversed(calls) if call['args'][0] == '-p')
        payload = json.loads(launch['theme'])
        self.assertEqual(payload['colors']['accent'], '#82aaff')
        self.assertEqual(payload['bar'], {'height': 40, 'rounding': 8, 'opacity': 0.9})
        self.assertTrue(any(call['args'][-1] == 'stop' for call in calls))
        self.cli('stop')
        self.cli('stop')
        self.assertFalse((self.root / 'running').exists())
        self.assertEqual(list((self.root / 'config/luna').iterdir()), [self.root / 'config/luna/theme'])

    def test_invalid_theme_preserves_running_bar(self):
        theme = self.selected_theme()
        self.cli()
        count = len(self.commands())
        for invalid in ('return { rounding = -1 }', 'return { height = 10 }',
                        'return { opacity = 2 }', 'return { unexpected = 1 }'):
            (theme / 'bar.lua').write_text(invalid)
            self.cli('reload', ok=False)
            self.assertEqual(len(self.commands()), count)
            self.assertTrue((self.root / 'running').exists())
        (self.root / 'config/luna/theme').write_text('../escape\n')
        self.cli('reload', ok=False)
        self.assertEqual(len(self.commands()), count)


if __name__ == '__main__':
    unittest.main()
