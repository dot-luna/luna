"""Exercise theme storage and validation in isolated XDG directories."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest


REPO = Path(__file__).resolve().parents[4]
SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10" fill="red"/></svg>'


class ThemeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luna themes '")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        mock = self.root / 'bin'
        mock.mkdir()
        # Never change the host desktop: persist mock GSettings inside the test folder.
        gsettings = mock / 'gsettings'
        gsettings.write_text('''#!/usr/bin/python3
import json, os, pathlib, sys
root = pathlib.Path(os.environ['TEST_THEME_ROOT'])
args = sys.argv[1:]
with (root / 'gsettings-log').open('a') as out:
    out.write(json.dumps(args) + '\\n')
state = root / 'gsettings-value'
if args[0] == 'get':
    print(repr(state.read_text() if state.exists() else 'default'))
elif args[0] == 'writable':
    print('true')
elif args[0] == 'set':
    if (root / 'fail-dark').exists() and args[-1] == 'prefer-dark':
        sys.exit(1)
    state.write_text(args[-1])
else:
    sys.exit(1)
''')
        gsettings.chmod(0o755)
        home = self.root / 'home'
        home.mkdir()
        runtime = self.root / 'runtime'
        runtime.mkdir(mode=0o700)
        self.env = {
            'HOME': str(home), 'XDG_DATA_HOME': str(self.root / 'data'),
            'XDG_CONFIG_HOME': str(self.root / 'config'), 'XDG_CACHE_HOME': str(self.root / 'cache'),
            'XDG_STATE_HOME': str(self.root / 'state'), 'XDG_RUNTIME_DIR': str(runtime),
            'DBUS_SESSION_BUS_ADDRESS': 'unix:path=' + str(runtime / 'unavailable-bus'),
            'TEST_THEME_ROOT': str(self.root), 'PATH': str(mock) + ':/usr/bin:/bin', 'NO_COLOR': '1',
        }
        self.library = self.root / 'data/luna/themes'
        self.source = self.root / 'tokyo-night'
        shutil.copytree(REPO / 'themes/bundled/tokyo-night', self.source)

    def cli(self, *args, ok=True, answer='', prelude=''):
        command = [str(REPO / 'bin/luna'), 'theme', *map(str, args)]
        if prelude:
            # Inject filesystem failures inside this child while preserving the real CLI flow.
            command = ['/usr/bin/lua', '-E', '-', str(REPO / 'src/luna-cli/main.lua'),
                       'theme', *map(str, args)]
            answer = prelude + '\narg[0] = table.remove(arg, 1)\ndofile(arg[0])\n'
        result = subprocess.run(command, env=self.env, cwd=self.root, capture_output=True,
                                text=True, input=answer, timeout=20)
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
        self.assertEqual(json.loads((self.root / 'config/luna/theme.json').read_text())['name'], 'tokyo-night')
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

    def test_base_colors_optional_exports_and_force(self):
        for name in ('hyprland.lua', 'fonts.lua', 'wallpaper.lua'):
            (self.source / name).unlink()
        # A theme may still explicitly supply all base colors.
        script = '''local c = dofile(arg[1]); local required = {
            "mode", "accent", "accent_foreground", "selection", "selection_foreground", "muted",
            "background", "dark_background", "darker_background", "lighter_background",
            "foreground", "dark_foreground", "light_foreground", "bright_foreground" }
            print("return {")
            for _, key in ipairs(required) do print(key .. " = " .. string.format("%q", c[key]) .. ",") end
            print("}")'''
        result = subprocess.run(['/usr/bin/lua', '-E', '-', str(self.source / 'colors.lua')],
                                input=script, env=self.env, cwd=self.root,
                                capture_output=True, text=True, check=True, timeout=10)
        colors = result.stdout
        (self.source / 'colors.lua').write_text(colors)
        self.cli('install', self.source)
        self.cli('install', self.source, ok=False)
        original = (self.library / 'tokyo-night/colors.lua').read_text()
        (self.source / 'colors.lua').write_text('return { mode = "invalid" }')
        self.cli('install', '--force', self.source, ok=False)
        self.assertEqual((self.library / 'tokyo-night/colors.lua').read_text(), original)
        (self.source / 'colors.lua').write_text(original.replace('#7aa2f7', '#82aaff'))
        self.cli('install', '--force', self.source)
        self.assertIn('#82aaff', (self.library / 'tokyo-night/colors.lua').read_text())
        self.assertFalse(list(self.library.glob('.install-*')))

    def test_partial_theme_defaults_and_regeneration(self):
        for name in ('hyprland.lua', 'fonts.lua', 'wallpaper.lua'):
            (self.source / name).unlink()
        (self.source / 'colors.lua').write_text('return { accent = "#ffffff" }')
        (self.source / 'hyprland.lua').write_text(
            'return { decoration = { rounding = 8, blur = { enabled = false } } }')
        self.cli('install', self.source)
        self.cli('set', 'tokyo-night')
        output = self.root / 'config/luna/theme.json'
        theme = json.loads(output.read_text())
        self.assertEqual(theme['colors']['background'], '#1a1b26')
        self.assertEqual(theme['colors']['accent_foreground'], '#000000')
        self.assertEqual(theme['fonts'], {'ui': 'Outfit', 'mono': 'Iosevka Nerd Font'})
        self.assertEqual(theme['wallpaper']['sources'], [])
        self.assertEqual(theme['hyprland']['decoration']['rounding'], 8)
        self.assertEqual(theme['hyprland']['decoration']['blur'], {'enabled': False, 'size': 10, 'passes': 3})
        installed = self.library / 'tokyo-night/colors.lua'
        installed.write_text('return { mode = "light", accent = "#000000" }')
        self.cli('set', 'tokyo-night')
        theme = json.loads(output.read_text())
        self.assertEqual(theme['colors']['background'], '#e1e2e7')
        self.assertEqual(theme['colors']['accent_foreground'], '#ffffff')
        self.assertEqual(theme['colors']['mode'], 'light')
        self.assertEqual(self.cli('mode').strip(), 'light')
        output.unlink()
        self.cli('set', 'tokyo-night')
        self.assertTrue(output.exists())
        installed.write_text('return { accent = "invalid" }')
        previous = output.read_bytes()
        self.cli('set', 'tokyo-night', ok=False)
        self.assertEqual(output.read_bytes(), previous)

    def test_existing_staging_directory_is_preserved(self):
        self.cli('install', self.source)
        self.cli('set', 'tokyo-night')
        output = self.root / 'config/luna/theme.json'
        staged = output.with_name('theme.json.tmp')
        staged.mkdir()
        (staged / 'keep').touch()
        (self.library / 'tokyo-night/colors.lua').write_text('return { mode = "light" }')
        self.cli('set', 'tokyo-night')
        self.assertEqual(json.loads(output.read_text())['colors']['mode'], 'light')
        self.assertEqual(self.cli('current').strip(), 'tokyo-night')
        self.assertEqual(self.cli('mode').strip(), 'light')
        self.assertTrue((staged / 'keep').is_file())

    def test_existing_staging_symlinks_are_not_followed_or_removed(self):
        self.cli('install', self.source)
        links = []
        for index, name in enumerate(('luna/theme.json.tmp', 'luna/theme.tmp',
                                      'gtk-3.0/settings.ini.luna-tmp',
                                      'gtk-4.0/settings.ini.luna-tmp', 'luna/theme-mode.luna-tmp')):
            target = self.root / f'personal-{index}'
            if index % 2 == 0:
                target.write_text('Keep this personal content\n')
            link = self.root / 'config' / name
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(target)
            links.append((link, target, index % 2 == 0))

        self.cli('set', 'tokyo-night', '--force')

        for link, target, existed in links:
            self.assertTrue(link.is_symlink())
            self.assertEqual(target.exists(), existed)
            if existed:
                self.assertEqual(target.read_text(), 'Keep this personal content\n')
        self.assertFalse((self.root / 'config/luna/theme.json').is_symlink())
        self.assertEqual(self.cli('current').strip(), 'tokyo-night')

    def test_staging_failure_preserves_selection_and_cleans_own_files(self):
        self.cli('install', self.source)
        self.cli('set', 'tokyo-night')
        output = self.root / 'config/luna/theme.json'
        original = output.read_bytes()
        (self.library / 'tokyo-night/colors.lua').write_text('return { mode = "light" }')
        self.cli('set', 'tokyo-night', ok=False, prelude='''
local original_open = io.open
io.open = function(path, mode)
    local prefix = os.getenv('XDG_CONFIG_HOME') .. '/luna/theme.luna-'
    if mode == 'w' and path:sub(1, #prefix) == prefix then
        return nil, 'Fixture staging failure'
    end
    return original_open(path, mode)
end
''')
        self.assertEqual(output.read_bytes(), original)
        self.assertEqual(self.cli('current').strip(), 'tokyo-night')
        self.assertEqual(self.cli('mode').strip(), 'dark')
        self.assertFalse(list((self.root / 'config').rglob('*.luna-*')))

    def test_selection_publish_failure_restores_theme_and_appearance(self):
        self.cli('install', self.source)
        self.cli('set', 'tokyo-night')
        config = self.root / 'config'
        files = [config / name for name in ('luna/theme.json', 'luna/theme', 'luna/theme-mode',
                                            'gtk-3.0/settings.ini', 'gtk-4.0/settings.ini')]
        originals = {path: path.read_bytes() for path in files}
        personal = self.root / 'personal-file'
        personal.write_text('Keep this personal content\n')
        for name in ('luna/theme.json.tmp', 'luna/theme-mode.luna-tmp',
                     'gtk-3.0/settings.ini.luna-tmp', 'gtk-4.0/settings.ini.luna-tmp'):
            (config / name).symlink_to(personal)
        (self.library / 'tokyo-night/colors.lua').write_text('return { mode = "light" }')
        self.cli('set', 'tokyo-night', '--force', ok=False, prelude='''
local original_rename = os.rename
os.rename = function(source, target)
    if target == os.getenv('XDG_CONFIG_HOME') .. '/luna/theme' then
        return nil, 'Fixture selection publish failure'
    end
    return original_rename(source, target)
end
''')
        for path, original in originals.items():
            self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.cli('mode').strip(), 'dark')
        self.assertEqual(personal.read_text(), 'Keep this personal content\n')
        staged = list(config.rglob('*.luna-*'))
        self.assertEqual(len(staged), 3)
        self.assertTrue(all(path.is_symlink() for path in staged))

    def test_resolved_json_round_trip(self):
        family = 'Font "Quoted" \u2013 Unicode'
        (self.source / 'fonts.lua').write_text('return { ui = [[%s]] }' % family)
        self.cli('install', self.source)
        self.cli('set', 'tokyo-night')
        script = """
local resolved = dofile(arg[1] .. '/lib/theme/resolved.lua')(arg[1])
io.write(resolved.encode(resolved.active()))
"""
        result = subprocess.run(['lua', '-E', '-', str(REPO)], input=script,
                                env=self.env, cwd=self.root, text=True,
                                capture_output=True, check=True, timeout=10)
        self.assertEqual(json.loads(result.stdout)['fonts']['ui'], family)
        self.assertEqual(json.loads(result.stdout),
                         json.loads((self.root / 'config/luna/theme.json').read_text()))

    def test_invalid_exports_and_sandbox(self):
        self.cli('install', '--name', '../escape', self.source, ok=False)
        self.cli('install', '--name', '-bad', self.source, ok=False)
        (self.source / 'fonts.lua').write_text('return { ui = "" }')
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

    def test_mode_persistence_toggle_skip_and_force(self):
        gtk = self.root / 'config/gtk-3.0/settings.ini'
        gtk.parent.mkdir(parents=True)
        gtk.write_text('# keep this\n[Settings]\ngtk-font-name=Custom 12\n'
                       'gtk-application-prefer-dark-theme=0\n[Other]\nkeep=value\n')
        self.cli('install', self.source)
        self.cli('set', 'tokyo-night')
        self.assertEqual(self.cli('mode').strip(), 'dark')
        self.assertIn('gtk-font-name=Custom 12', gtk.read_text())
        self.assertIn('[Other]\nkeep=value', gtk.read_text())
        self.assertIn('gtk-application-prefer-dark-theme=1', gtk.read_text())
        selection = self.root / 'config/luna/theme'
        saved = self.root / 'config/luna/theme-mode'
        stamp = (gtk.stat().st_mtime_ns, saved.stat().st_mtime_ns, selection.stat().st_mtime_ns)
        def sets():
            return [row for row in map(json.loads, (self.root / 'gsettings-log').read_text().splitlines()) if row[0] == 'set']
        before = len(sets())
        self.cli('mode', 'dark')
        self.cli('set', 'tokyo-night')
        self.assertEqual(len(sets()), before)
        self.assertEqual(stamp, (gtk.stat().st_mtime_ns, saved.stat().st_mtime_ns, selection.stat().st_mtime_ns))
        self.cli('mode', 'dark', '--force')
        self.assertEqual(len(sets()), before + 1)
        self.cli('toggle')
        self.assertEqual(self.cli('mode').strip(), 'light')
        self.assertEqual(saved.read_text(), 'light\n')
        self.assertIn('gtk-application-prefer-dark-theme=0', gtk.read_text())
        self.cli('mode', 'toggle')
        self.assertEqual(self.cli('mode').strip(), 'dark')
        self.cli('mode', 'light')
        self.cli('set', 'tokyo-night')
        self.assertEqual(self.cli('mode').strip(), 'dark')

    def test_mode_failure_preserves_selection_and_settings(self):
        self.cli('install', self.source)
        colors = self.source / 'colors.lua'
        colors.write_text(colors.read_text().replace('mode = "dark"', 'mode = "light"'))
        self.cli('install', self.source, '--name', 'light-theme')
        self.cli('set', 'light-theme')
        gtk = self.root / 'config/gtk-3.0/settings.ini'
        original = gtk.read_text()
        output = self.root / 'config/luna/theme.json'
        original_output = output.read_bytes()
        (self.root / 'fail-dark').touch()
        self.cli('set', 'tokyo-night', ok=False)
        self.assertEqual(self.cli('current').strip(), 'light-theme')
        self.assertEqual(self.cli('mode').strip(), 'light')
        self.assertEqual(gtk.read_text(), original)
        self.assertEqual(output.read_bytes(), original_output)
        self.assertFalse(list((self.root / 'config').rglob('*.luna-*')))
        self.assertFalse((self.root / 'config/luna/theme.tmp').exists())


if __name__ == '__main__':
    unittest.main()
