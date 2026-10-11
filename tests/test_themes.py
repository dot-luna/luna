"""Exercise theme storage and validation in isolated XDG directories."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest


REPO = Path(__file__).resolve().parents[1]
SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10" fill="red"/></svg>'


class ThemeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luna themes '")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = dict(os.environ, XDG_DATA_HOME=str(self.root / 'data'),
                        XDG_CONFIG_HOME=str(self.root / 'config'))
        self.library = self.root / 'data/luna/themes'
        self.source = self.root / 'tokyo-night'
        shutil.copytree(REPO / 'themes/bundled/tokyo-night', self.source)

    def cli(self, *args, ok=True, answer=''):
        result = subprocess.run([str(REPO / 'bin/luna'), 'theme', *map(str, args)],
                                env=self.env, capture_output=True, text=True, input=answer)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return result.stdout

    def test_install_select_and_remove(self):
        self.assertEqual(self.cli('path').strip(), str(self.library))
        self.cli('current', ok=False)
        self.cli('install', self.source)
        self.assertEqual((self.library / 'tokyo-night/colors.lua').read_text(),
                         (self.source / 'colors.lua').read_text())
        self.cli('set', 'tokyo-night')
        self.assertEqual(self.cli('current').strip(), 'tokyo-night')
        self.assertIn('* tokyo-night', self.cli('list'))
        self.assertEqual(self.cli('path', 'tokyo-night').strip(), str(self.library / 'tokyo-night'))
        self.assertFalse((self.root / 'config/luna/generated').exists())
        self.cli('remove', 'tokyo-night', ok=False, answer='y\n')
        self.cli('install', '--name', 'other', self.source)
        self.cli('set', 'other')
        self.cli('remove', 'tokyo-night', 'missing', ok=False, answer='y\n')
        self.assertTrue((self.library / 'tokyo-night').exists())
        self.cli('remove', 'tokyo-night', answer='n\n')
        self.assertTrue((self.library / 'tokyo-night').exists())
        self.cli('remove', 'tokyo-night', answer='y\n')
        self.assertFalse((self.library / 'tokyo-night').exists())
        self.assertTrue(self.source.exists())

    def test_required_colors_optional_exports_and_force(self):
        for name in ('hyprland.lua', 'fonts.lua', 'wallpaper.lua'):
            (self.source / name).unlink()
        # Only the documented base fields are required.
        script = '''local c = dofile(arg[1]); local required = {
            "mode", "accent", "accent_foreground", "selection", "selection_foreground", "muted",
            "background", "dark_background", "darker_background", "lighter_background",
            "foreground", "dark_foreground", "light_foreground", "bright_foreground" }
            print("return {")
            for _, key in ipairs(required) do print(key .. " = " .. string.format("%q", c[key]) .. ",") end
            print("}")'''
        result = subprocess.run(['/usr/bin/lua', '-E', '-', str(self.source / 'colors.lua')],
                                input=script, capture_output=True, text=True, check=True)
        colors = result.stdout
        (self.source / 'colors.lua').write_text(colors)
        self.cli('install', self.source)
        self.cli('install', self.source, ok=False)
        original = (self.library / 'tokyo-night/colors.lua').read_text()
        (self.source / 'colors.lua').write_text('return { mode = "dark" }')
        self.cli('install', '--force', self.source, ok=False)
        self.assertEqual((self.library / 'tokyo-night/colors.lua').read_text(), original)
        (self.source / 'colors.lua').write_text(original.replace('#7aa2f7', '#82aaff'))
        self.cli('install', '--force', self.source)
        self.assertIn('#82aaff', (self.library / 'tokyo-night/colors.lua').read_text())
        self.assertFalse(list(self.library.glob('.install-*')))

    def test_invalid_exports_and_sandbox(self):
        self.cli('install', '--name', '../escape', self.source, ok=False)
        self.cli('install', '--name', '-bad', self.source, ok=False)
        (self.source / 'fonts.lua').write_text('return { size = -1 }')
        self.cli('install', self.source, ok=False)
        (self.source / 'fonts.lua').unlink()
        (self.source / 'hyprland.lua').write_text('return { decoration = { blur = { passes = 20 } } }')
        self.cli('install', self.source, ok=False)
        (self.source / 'hyprland.lua').unlink()
        (self.source / 'colors.lua').write_text('os.execute("touch /should-never-run"); return {}')
        self.cli('install', self.source, ok=False)
        (self.source / 'colors.lua').write_text('while true do end')
        self.cli('install', self.source, ok=False)
        self.assertFalse((self.library / 'tokyo-night').exists())

    def test_local_and_url_wallpaper_import(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(SVG.encode())

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        images = self.source / 'images'
        images.mkdir()
        (images / 'local.svg').write_text(SVG)
        (self.source / 'wallpaper.lua').write_text(
            'return { sources = { "images", "http://127.0.0.1:' + str(server.server_port) + '/remote.svg" } }')
        self.cli('install', self.source)
        wallpapers = self.root / 'data/luna/wallpapers'
        self.assertTrue((wallpapers / 'local.svg').exists())
        self.assertTrue((wallpapers / 'remote.svg').exists())
        shutil.rmtree(self.source)
        self.cli('set', 'tokyo-night')
        self.assertTrue((self.library / 'tokyo-night/images/local.svg').exists())

    def test_wallpaper_escape_and_missing_sources(self):
        outside = self.root / 'outside.svg'
        outside.write_text(SVG)
        for source in ('../outside.svg', 'missing.svg', str(outside)):
            (self.source / 'wallpaper.lua').write_text('return { sources = { "' + source + '" } }')
            self.cli('install', self.source, ok=False)
            self.assertFalse((self.library / 'tokyo-night').exists())
            self.assertFalse(list(self.library.glob('.install-*')))
        self.assertTrue(outside.exists())


if __name__ == '__main__':
    unittest.main()
