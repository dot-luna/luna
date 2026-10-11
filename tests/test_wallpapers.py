"""Check wallpaper files and selection persistence without touching the desktop."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest


REPO = Path(__file__).resolve().parents[1]
SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10" fill="red"/></svg>'


class WallpaperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luna wallpaper '")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.library = self.root / 'data/luna/wallpapers'
        self.selection = self.root / 'config/luna/wallpaper'
        self.env = dict(os.environ, PATH=str(self.bin) + ':' + os.environ['PATH'],
                        XDG_DATA_HOME=str(self.root / 'data'),
                        XDG_CONFIG_HOME=str(self.root / 'config'),
                        WAYLAND_DISPLAY='test', TEST_ROOT=str(self.root))
        # Record renderer and explorer requests rather than running host applications.
        mock = '''#!/usr/bin/python3
import json, os, pathlib, sys
root = pathlib.Path(os.environ['TEST_ROOT'])
with (root / 'commands').open('a') as out:
    out.write(json.dumps(sys.argv[1:]) + '\\n')
if sys.argv[-1] == 'status':
    print('error' if (root / 'fail').exists() else 'ready')
'''
        for tool in ('qs', 'xdg-open'):
            path = self.bin / tool
            path.write_text(mock)
            path.chmod(0o755)
        self.a = self.root / 'a #.svg'
        self.a.write_text(SVG)
        self.b = self.root / 'b.svg'
        self.b.write_text(SVG.replace('red', 'blue'))

    def cli(self, *args, ok=True, answer=''):
        result = subprocess.run([str(REPO / 'bin/luna'), 'wallpaper', *map(str, args)],
                                env=self.env, input=answer, capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return result.stdout

    def test_library_and_explorer(self):
        self.assertEqual(self.cli('dir').strip(), str(self.library))
        self.cli('open')
        self.assertTrue(self.library.is_dir())
        self.assertEqual(json.loads((self.root / 'commands').read_text()), [str(self.library)])
        self.cli('add', self.a, self.b)
        self.assertIn(self.a.name, self.cli('list'))
        self.cli('add', self.a)
        self.cli('remove', self.a.name, self.b.name, answer='n\n')
        self.assertTrue((self.library / self.a.name).exists())
        self.cli('remove', self.a.name, 'unknown.svg', ok=False, answer='y\n')
        self.assertTrue((self.library / self.a.name).exists())
        self.cli('remove', self.a.name, self.b.name, answer='y\n')
        self.assertEqual(list(self.library.iterdir()), [])
        self.assertTrue(self.a.exists())

    def test_recursive_and_preflight(self):
        folder = self.root / 'images'
        (folder / 'nested').mkdir(parents=True)
        (folder / 'a.svg').write_text(SVG)
        (folder / 'nested/b.svg').write_text(SVG)
        self.cli('add', folder)
        self.assertFalse((self.library / 'b.svg').exists())
        self.cli('add', '-r', folder)
        self.assertTrue((self.library / 'b.svg').exists())
        (folder / 'a.svg').write_text(SVG.replace('red', 'blue'))
        self.cli('add', folder, ok=False)
        self.assertEqual((self.library / 'a.svg').read_text(), SVG)
        self.cli('add', '--force', folder)
        self.assertIn('blue', (self.library / 'a.svg').read_text())
        bad = self.root / 'bad.png'
        bad.write_text('invalid')
        self.cli('add', self.a, bad, ok=False)
        self.assertFalse((self.library / self.a.name).exists())

    def test_selection_random_and_failure(self):
        self.cli('current', ok=False)
        self.cli('add', self.a, self.b)
        self.cli('set', self.a.name)
        saved = str(self.library / self.a.name)
        self.assertEqual(self.cli('current').strip(), saved)
        self.assertIn('* ' + saved, self.cli('list'))
        self.cli('remove', self.a.name, ok=False, answer='y\n')
        self.cli('random')
        self.assertEqual(self.selection.read_text().strip(), str(self.library / self.b.name))
        (self.root / 'fail').touch()
        self.cli('set', self.a, ok=False)
        self.assertEqual(self.selection.read_text().strip(), str(self.library / self.b.name))
        (self.root / 'fail').unlink()
        self.cli('set', self.a)
        self.assertEqual(self.selection.read_text().strip(), str(self.a))
        self.cli('start')

    def test_url_downloads_and_cleanup(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/redirect':
                    self.send_response(302)
                    self.send_header('Location', '/image')
                    self.end_headers()
                    return
                if self.path == '/missing':
                    self.send_error(404)
                    return
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'not an image' if self.path == '/bad' else SVG.encode())

            def log_message(self, *args):
                pass

        # Real curl exercises HTTP behavior; only the loopback server is contacted.
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = 'http://127.0.0.1:' + str(server.server_port)
        temporary = self.root / 'downloads'
        temporary.mkdir()
        self.env['TMPDIR'] = str(temporary)
        self.cli('add', base + '/wall%20paper.jpg?size=full', base + '/redirect', self.b)
        self.assertTrue((self.library / 'wall paper.svg').exists())
        self.assertTrue((self.library / 'redirect.svg').exists())
        self.assertTrue((self.library / self.b.name).exists())
        self.assertEqual(list(temporary.iterdir()), [])
        self.cli('add', self.a, base + '/bad', ok=False)
        self.cli('add', self.a, base + '/missing', ok=False)
        self.assertFalse((self.library / self.a.name).exists())
        self.assertEqual(list(temporary.iterdir()), [])

    def test_missing_curl_bootstrap(self):
        # Inject availability and install calls so bootstrap never invokes host pacman.
        script = '''
local installed = false
local calls = {}
local common = {
    available = function(name)
        return name ~= "curl" or installed
    end,
    is_root = function() return false end,
    info = function() end,
    run = function(args)
        table.insert(calls, table.concat(args, " "))
        installed = true
    end,
}
local download = dofile(arg[1])(common)
download.prepare()
assert(calls[1] == "sudo pacman -Syu --needed curl")
download.prepare()
assert(#calls == 1)
'''
        result = subprocess.run(['/usr/bin/lua', '-E', '-',
                                 str(REPO / 'src/luna-cli/wallpaper/download.lua')],
                                input=script, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
