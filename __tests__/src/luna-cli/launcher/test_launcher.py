"""Verify launcher command routing without opening desktop windows."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[4]


class LauncherTests(unittest.TestCase):
    def test_default_open_toggle_and_reload(self):
        with tempfile.TemporaryDirectory(prefix="luna launcher '") as directory:
            root = Path(directory)
            tool = root / 'qs'
            tool.write_text('''#!/usr/bin/python3
import json, os, pathlib, sys
root = pathlib.Path(os.environ['TEST_ROOT'])
with (root / 'commands').open('a') as out:
    out.write(json.dumps(sys.argv[1:]) + '\\n')
running = root / 'running'
if sys.argv[1] == 'ipc':
    if not running.exists():
        sys.exit(1)
    if sys.argv[-1] == 'stop':
        running.unlink()
else:
    running.touch()
''')
            tool.chmod(0o755)
            env = dict(os.environ, PATH=str(root) + ':' + os.environ['PATH'],
                       TEST_ROOT=str(root), WAYLAND_DISPLAY='test',
                       XDG_CONFIG_HOME=str(root / 'config'), XDG_DATA_HOME=str(root / 'data'))

            for action, expected in [(None, 'open'), ('toggle', 'toggle'), ('reload', 'ping'), ('stop', 'ping')]:
                args = [str(REPO / 'bin/luna'), 'launcher']
                if action:
                    args.append(action)
                result = subprocess.run(args, env=env, text=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                calls = [json.loads(line) for line in (root / 'commands').read_text().splitlines()]
                self.assertEqual(calls[-1][-1], expected)
                self.assertEqual(calls[-1][-2], 'launcher')
            self.assertFalse((root / 'running').exists())


if __name__ == '__main__':
    unittest.main()
