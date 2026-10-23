"""Generate Kitty settings from isolated Luna theme and font state."""

import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[4]
GENERATOR = REPO / 'apps/kitty/scripts/generate-theme.lua'


class GenerateThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Use the complete shared schema while choosing test-specific values below.
        result = subprocess.run(
            ['/usr/bin/lua', '-E', '-', str(REPO)],
            input='local root = arg[1]; print(dofile(root .. "/lib/theme/json.lua").encode('
                  'dofile(root .. "/lib/theme/defaults.lua")))',
            capture_output=True, text=True, check=True,
        )
        cls.defaults = json.loads(result.stdout)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luna kitty '")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        self.config = self.root / 'config/luna'
        self.config.mkdir(parents=True)
        self.env = dict(os.environ, HOME=str(self.home),
                        XDG_CONFIG_HOME=str(self.config.parent),
                        XDG_DATA_HOME=str(self.root / 'data'))

    def generate(self, *args, script=GENERATOR, env=None, ok=True):
        result = subprocess.run(
            ['/usr/bin/lua', '-E', str(script), *args],
            cwd=self.root, env=env or self.env, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        if not ok:
            self.assertEqual(result.stdout, '')
            self.assertIn('Cannot generate Kitty theme:', result.stderr)
            return result.stderr
        self.assertEqual(result.stderr, '')
        return dict(line.split(maxsplit=1) for line in result.stdout.splitlines()
                    if line.strip() and not line.startswith('#'))

    def select(self, theme):
        (self.config / 'theme').write_text('custom\n')
        (self.config / 'theme.json').write_text(json.dumps(
            dict(theme, version=1, name='custom')))

    def test_defaults_and_extra_arguments_from_another_directory(self):
        options = self.generate('ignored', '--unused')
        self.assertEqual(options['font_family'], 'Iosevka Nerd Font')
        self.assertEqual(options['background'], '#1a1b26')
        self.assertEqual(options['foreground'], '#a9b1d6')
        self.assertEqual(options['selection_background'], '#292e42')
        for name in ('bold_font', 'italic_font', 'bold_italic_font'):
            self.assertEqual(options[name], 'auto')
        self.assertTrue(all(f'color{index}' in options for index in range(16)))
        self.assertEqual(list(self.config.iterdir()), [])

    def test_selected_snapshot_controls_colors_and_fonts(self):
        theme = copy.deepcopy(self.defaults)
        theme['fonts']['mono'] = 'Selected Mono'
        for index, role in enumerate(theme['colors']):
            if role != 'mode':
                theme['colors'][role] = f'#{index:02x}1234'
        self.select(theme)

        # The selected JSON is authoritative, even when raw installed exports change.
        installed = self.root / 'data/luna/themes/custom'
        installed.mkdir(parents=True)
        (installed / 'colors.lua').write_text('error("Do not load theme exports")')
        options = self.generate()
        self.assertEqual(options['font_family'], 'Selected Mono')
        colors = theme['colors']
        for option, role in {
            'background': 'background', 'foreground': 'foreground',
            'cursor': 'accent', 'cursor_text_color': 'accent_foreground',
            'selection_background': 'selection', 'selection_foreground': 'selection_foreground',
        }.items():
            self.assertEqual(options[option], colors[role])
        for index, role in enumerate((
            'dark_background', 'error', 'success', 'warning',
            'link', 'secondary_accent', 'info', 'light_foreground',
            'dark_foreground', 'error_emphasis', 'success_emphasis', 'warning_emphasis',
            'link_emphasis', 'secondary_accent_emphasis', 'info_emphasis', 'bright_foreground',
        )):
            self.assertEqual(options[f'color{index}'], colors[role])

    def test_personal_font_overrides_default_and_selected_theme(self):
        (self.config / 'fonts.json').write_text(json.dumps({'mono': 'Personal Mono'}))
        self.assertEqual(self.generate()['font_family'], 'Personal Mono')
        theme = copy.deepcopy(self.defaults)
        theme['fonts']['mono'] = 'Selected Mono'
        self.select(theme)
        self.assertEqual(self.generate()['font_family'], 'Personal Mono')

    def test_empty_and_unset_xdg_config_use_home(self):
        config = self.home / '.config/luna'
        config.mkdir(parents=True)
        theme = copy.deepcopy(self.defaults)
        theme['colors']['background'] = '#123456'
        (config / 'theme').write_text('custom\n')
        (config / 'theme.json').write_text(json.dumps(dict(theme, version=1, name='custom')))
        (config / 'fonts.json').write_text(json.dumps({'mono': 'Home Mono'}))
        for value in ('', None):
            with self.subTest(XDG_CONFIG_HOME=value):
                env = self.env.copy()
                if value is None:
                    env.pop('XDG_CONFIG_HOME')
                else:
                    env['XDG_CONFIG_HOME'] = value
                options = self.generate(env=env)
                self.assertEqual(options['background'], '#123456')
                self.assertEqual(options['font_family'], 'Home Mono')

    def test_script_symlink_resolves_the_checkout(self):
        link = self.root / "generator's link.lua"
        link.symlink_to(GENERATOR)
        self.assertEqual(self.generate(script=link), self.generate())

    def test_broken_selection_never_emits_partial_configuration(self):
        for contents in (None, '{bad json', '{"version":1,"name":"custom"}'):
            with self.subTest(contents=contents):
                (self.config / 'theme').write_text('custom\n')
                snapshot = self.config / 'theme.json'
                if contents is not None:
                    snapshot.write_text(contents)
                self.generate(ok=False)
                snapshot.unlink(missing_ok=True)

    def test_invalid_color_and_font_preference_fail(self):
        theme = copy.deepcopy(self.defaults)
        theme['colors']['background'] = 'not a color'
        self.select(theme)
        self.assertIn('Invalid color: background', self.generate(ok=False))
        self.select(self.defaults)
        (self.config / 'fonts.json').write_text(json.dumps({'mono': 'Mono\nbackground #ffffff'}))
        self.assertIn('Invalid font family', self.generate(ok=False))


if __name__ == '__main__':
    unittest.main()
