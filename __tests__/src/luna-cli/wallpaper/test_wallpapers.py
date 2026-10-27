"""Check wallpaper files and selection persistence without touching the desktop."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import tomllib
import unittest


REPO = Path(__file__).resolve().parents[4]
SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10" fill="red"/></svg>'


class WallpaperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luna wallpaper '")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.library = self.root / 'data/luna/wallpapers'
        self.selection = self.root / 'config/luna/wallpaper.toml'
        self.env = dict(os.environ, PATH=str(self.bin) + ':' + os.environ['PATH'],
                        HOME=str(self.root / 'home'), LUNA_WALLPAPER_CONFIG='',
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
elif sys.argv[1:4] == ['list', '-a', '-j']:
    print((root / 'instances').read_text() if (root / 'instances').exists() else '[]')
elif sys.argv[1:3] == ['kill', '--pid']:
    path = root / 'instances'
    remaining = [item for item in json.loads(path.read_text()) if str(item['pid']) != sys.argv[3]]
    path.write_text(json.dumps(remaining))
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

    def saved_source(self, path=None):
        return tomllib.loads((path or self.selection).read_text())['wallpaper']['source']

    def commands(self):
        return [json.loads(line) for line in (self.root / 'commands').read_text().splitlines()]

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

    def test_config_commands_print_resolved_values_and_deep_merge_without_renderer(self):
        resolved = json.loads(self.cli('get-config'))
        self.assertEqual(resolved['wallpaper']['fit'], 'fill')
        self.assertEqual(self.cli('get-config', 'missing'), '')
        self.assertEqual(self.cli('getConfig', 'wallpaper.source'), '')
        self.assertEqual(self.cli('get-config-file'), str(self.selection) + '\n')
        self.assertFalse(self.selection.exists())
        self.cli('update-config', json.dumps({'playback': {'pause_when_output_inactive': False},
                                             'transition': {'duration_ms': 0},
                                             'custom': {'nested': {'first': 1, 'second': 2}, 'values': [[], {}]}}))
        self.cli('updateConfig', json.dumps({'custom': {'nested': {'second': 3}, 'values': [4]}}))
        self.assertEqual(self.cli('get-config', 'playback.pause_when_output_inactive'), 'false\n')
        self.assertEqual(self.cli('get-config', 'transition.duration_ms'), '0\n')
        self.assertEqual(json.loads(self.cli('get-config', 'custom')), {'nested': {'first': 1, 'second': 3}, 'values': [4]})
        self.assertNotIn('wallpaper', tomllib.loads(self.selection.read_text()))
        self.assertFalse((self.root / 'commands').exists())
        self.selection.write_text('[broken')
        self.assertEqual(self.cli('getConfigFile'), str(self.selection) + '\n')
        self.cli('get-config', ok=False)

    def test_invalid_config_updates_fail_without_writing_or_reloading(self):
        self.cli('update-config', '{"wallpaper":{"fit":"invalid"}}', ok=False)
        self.assertFalse(self.selection.exists())
        self.cli('update-config', '{"wallpaper":{"fit":"fit"}}')
        before = self.selection.read_bytes()
        self.cli('update-config', '{"wallpaper":{"fit":"invalid","background_color":"#123456"}}', ok=False)
        self.assertEqual(self.selection.read_bytes(), before)
        self.assertFalse((self.root / 'commands').exists())

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
        self.assertEqual(self.cli('get-config', 'wallpaper.source'), '')
        self.cli('add', self.a, self.b)
        self.cli('set', self.a.name)
        saved = str(self.library / self.a.name)
        self.assertEqual(self.cli('get-config', 'wallpaper.source').strip(), saved)
        self.assertIn('* ' + saved, self.cli('list'))
        self.cli('remove', self.a.name, ok=False, answer='y\n')
        self.cli('random')
        self.assertEqual(self.saved_source(), str(self.library / self.b.name))
        before = self.selection.read_bytes()
        (self.root / 'fail').touch()
        self.cli('set', self.a, ok=False)
        self.assertEqual(self.selection.read_bytes(), before)
        self.assertEqual(self.commands()[-1][-1], 'status')
        (self.root / 'fail').unlink()
        self.cli('set', self.a)
        self.assertEqual(self.saved_source(), str(self.a))
        self.cli('start')

    def test_toml_comments_options_and_symlink_are_preserved(self):
        target = self.root / "user settings 'quoted'.toml"
        original = '''# My wallpaper settings
[wallpaper]
source = "/old.svg" # Current image
fit = "fit"
background_color = "#123456"

[outputs."DP-1".wallpaper]
source = "/reserved.png"

[custom]
future = true # Keep unknown options
'''
        target.write_text(original)
        target.chmod(0o640)
        self.selection.parent.mkdir(parents=True)
        self.selection.symlink_to(target)
        self.cli('set', self.a)
        self.assertTrue(self.selection.is_symlink())
        self.assertEqual(self.saved_source(), str(self.a))
        self.assertEqual(target.stat().st_mode & 0o777, 0o640)
        after = target.read_text()
        for text in ('# My wallpaper settings', '# Current image', 'fit = "fit"',
                     'background_color = "#123456"', '[outputs."DP-1".wallpaper]',
                     'source = "/reserved.png"', 'future = true # Keep unknown options'):
            self.assertIn(text, after)
        self.assertEqual(list(target.parent.glob('.luna-toml-*')), [])

    def test_explicit_config_and_empty_environment_fallbacks(self):
        explicit = self.root / "config with ' quotes/wallpaper.toml"
        self.env['LUNA_WALLPAPER_CONFIG'] = str(explicit)
        self.cli('set', self.a)
        self.assertEqual(self.saved_source(explicit), str(self.a))
        self.assertFalse(self.selection.exists())
        self.assertEqual(self.cli('get-config', 'wallpaper.source').strip(), str(self.a))

        self.env.update(LUNA_WALLPAPER_CONFIG='', XDG_CONFIG_HOME='', XDG_DATA_HOME='')
        self.cli('set', self.b)
        default = self.root / 'home/.config/luna/wallpaper.toml'
        self.assertEqual(self.saved_source(default), str(self.b))
        self.assertEqual(self.cli('dir').strip(), str(self.root / 'home/.local/share/luna/wallpapers'))

    def test_bad_config_or_failed_media_never_replaces_user_data(self):
        self.selection.parent.mkdir(parents=True)
        self.selection.write_text('[wallpaper\nsource = broken')
        before = self.selection.read_bytes()
        self.cli('set', self.a, ok=False)
        self.assertEqual(self.selection.read_bytes(), before)
        self.assertFalse((self.root / 'commands').exists())

        # Start still lets the shell report malformed TOML and show its dark fallback.
        self.cli('start')
        self.assertIn('--daemonize', self.commands()[-1])
        self.assertEqual(self.selection.read_bytes(), before)

        self.selection.unlink()
        (self.root / 'fail').touch()
        self.cli('set', self.a, ok=False)
        self.assertEqual(self.saved_source(), '')
        self.assertEqual(self.commands()[-1][-1], 'status')

    def test_repo_reference_is_not_rewritten_through_symlink(self):
        reference = REPO / 'src/wallpaper/config.toml'
        before = reference.read_bytes()
        self.selection.parent.mkdir(parents=True)
        self.selection.symlink_to(reference)
        self.cli('set', self.a, ok=False)
        self.assertEqual(reference.read_bytes(), before)
        self.assertTrue(self.selection.is_symlink())
        self.assertFalse((self.root / 'commands').exists())

    def test_restart_stops_only_exact_wallpaper_instances(self):
        instances = [
            {'id': 'current-wallpaper', 'pid': 301, 'config_path': str(REPO / 'src/wallpaper/src/shell/shell.qml')},
            {'id': 'bar', 'pid': 203, 'config_path': str(REPO / 'src/luna-bar/shell.qml')},
            {'id': 'other-wallpaper', 'pid': 302, 'config_path': '/other/checkout/src/wallpaper/src/shell/shell.qml'},
        ]
        (self.root / 'instances').write_text(json.dumps(instances))
        self.cli('restart')
        commands = self.commands()
        self.assertEqual([c for c in commands if c[0] == 'kill'],
                         [['kill', '--pid', '301']])
        self.assertEqual(json.loads((self.root / 'instances').read_text()), instances[1:])
        self.assertEqual(commands[-1][0], '-p')
        self.assertEqual(Path(commands[-1][1]).resolve(), REPO / 'src/wallpaper/src/shell/shell.qml')
        self.assertIn('--no-duplicate', commands[-1])

    def test_reload_calls_the_app_api_without_restarting_or_saving(self):
        self.selection.parent.mkdir(parents=True)
        original = '[wallpaper]\nsource = ""\nfit = "tile"\n'
        self.selection.write_text(original)
        self.assertIn('reloaded', self.cli('reload'))
        self.assertTrue(any(command[-1] == 'reload' for command in self.commands()))
        self.assertFalse(any(command[0] in ('kill', 'list') for command in self.commands()))
        self.assertEqual(self.selection.read_text(), original)
        (self.root / 'fail').touch()
        self.cli('reload', ok=False)
        self.assertEqual(self.selection.read_text(), original)

    def test_stop_command_never_launches_or_changes_config(self):
        self.selection.parent.mkdir(parents=True)
        original = '# Preserve even unfinished edits\n[wallpaper\n'
        self.selection.write_text(original)
        self.env['WAYLAND_DISPLAY'] = ''
        instances = [
            {'id': 'wallpaper', 'pid': 201, 'config_path': str(REPO / 'src/wallpaper/src/shell/shell.qml')},
            {'id': 'bar', 'pid': 203, 'config_path': str(REPO / 'src/luna-bar/shell.qml')},
        ]
        state = self.root / 'instances'
        state.write_text(json.dumps(instances))
        self.cli('stop')
        self.cli('stop')
        self.assertEqual(json.loads(state.read_text()), instances[1:])
        self.assertEqual(self.selection.read_text(), original)
        self.assertEqual([call for call in self.commands() if call[0] == 'kill'], [['kill', '--pid', '201']])
        self.assertTrue(all(call[0] in ('list', 'kill') for call in self.commands()))

    def test_local_animations_videos_and_mislabeled_images(self):
        gif = self.root / 'animation.gif'
        gif.write_bytes(b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff'
                        b',\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;')
        video = self.root / 'movie.mp4'
        video.write_bytes(b'\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom')
        mislabeled = self.root / 'image.blob'
        mislabeled.write_text(SVG)
        self.cli('add', gif, video)
        for media in (gif, video, mislabeled):
            self.cli('set', media)
            self.assertEqual(self.saved_source(), str(media))

    def test_imported_media_stays_accessible_without_a_known_extension(self):
        media = [self.root / 'extensionless', self.root / 'image.blob']
        for path in media:
            path.write_text(SVG)
        self.cli('add', *media)

        # MIME-validated imports must remain addressable by every library command.
        listing = self.cli('list')
        for path in media:
            self.assertIn(path.name, listing)
            self.cli('set', path.name)
            self.assertEqual(self.saved_source(), str(self.library / path.name))
        self.cli('random')
        self.assertEqual(self.saved_source(), str(self.library / media[0].name))
        self.cli('set', self.a)
        self.cli('remove', *(path.name for path in media), answer='y\n')
        self.assertEqual(list(self.library.iterdir()), [])

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


if __name__ == '__main__':
    unittest.main()
