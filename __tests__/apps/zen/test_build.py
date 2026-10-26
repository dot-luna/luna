"""Build Zen CSS and font defaults without accessing profiles or launching Zen."""

import copy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]
DRIVER = REPO / 'scripts/setup/build-app.lua'


class BuildThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(
            ['/usr/bin/lua', '-E', '-', str(REPO)],
            input='local root = arg[1]; print(dofile(root .. "/lib/theme/json.lua").encode('
                  'dofile(root .. "/lib/theme/defaults.lua")))',
            capture_output=True, text=True, check=True,
        )
        cls.defaults = json.loads(result.stdout)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luna zen '")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        self.config = self.root / 'config/luna'
        self.config.mkdir(parents=True)
        self.env = dict(os.environ, HOME=str(self.home),
                        XDG_CONFIG_HOME=str(self.config.parent),
                        XDG_DATA_HOME=str(self.root / 'data'))

    def generate(self, *args, driver=DRIVER, env=None, ok=True):
        output = self.root / 'built'
        shutil.rmtree(output, ignore_errors=True)
        output.mkdir()
        source = driver.resolve().parents[2] / 'apps/zen'
        result = subprocess.run(
            ['/usr/bin/lua', '-E', str(driver), str(source), str(output),
             str(self.config / 'zen'), str(self.config), *args],
            cwd=self.root, env=env or self.env, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        if not ok:
            self.assertFalse((output / 'generated/userChrome.css').exists())
            return result.stderr
        self.assertEqual(result.stderr, '')
        styles = {
            'chrome': (output / 'generated/userChrome.css').read_text(),
            'content': (output / 'generated/userContent.css').read_text(),
            'fonts': json.loads((output / 'generated/fonts.json').read_text()),
        }
        self.assertTrue(all(styles[key].startswith('@charset "UTF-8";\n')
                            for key in ('chrome', 'content')))
        self.assertEqual(set(styles['fonts']), {'ui', 'mono'})
        return styles

    def select(self, theme):
        (self.config / 'theme').write_text('custom\n')
        (self.config / 'theme.json').write_text(json.dumps(
            dict(theme, version=1, name='custom')))

    def test_defaults_are_browser_scoped_and_extra_arguments_are_ignored(self):
        styles = self.generate('ignored', '--unused')
        chrome = styles['chrome']
        self.assertIn('@-moz-document url("chrome://browser/content/browser.xhtml") {', chrome)
        self.assertIn('--zen-main-browser-background: #1a1b26 !important;', chrome)
        self.assertIn('--zen-primary-color: #7aa2f7 !important;', chrome)
        self.assertIn('--luna-ui-font: "Outfit", sans-serif !important;', chrome)
        self.assertIn('color-scheme: dark !important;', chrome)
        self.assertIn(':root, .zen-browser-generic-background {', chrome)
        self.assertEqual(styles['fonts'], {'ui': 'Outfit', 'mono': 'Iosevka Nerd Font'})
        self.assertEqual(list(self.config.iterdir()), [])
        self.assertEqual(list(self.home.iterdir()), [])

    def test_zero_rounding_covers_browser_corners_and_only_web_page_content(self):
        styles = self.generate()
        for name in ('--zen-border-radius', '--zen-webview-border-radius',
                     '--zen-native-inner-radius', '--button-border-radius'):
            self.assertIn(f'{name}: 0px !important;', styles['chrome'])
        for css in (styles['chrome'], styles['content']):
            self.assertIn('*, *::before, *::after {\n        border-radius: 0 !important;', css)
            self.assertNotRegex(css, r'\b(?:clip-path|mask|display|visibility)\s*:')
        content = re.sub(r'/\*.*?\*/', '', styles['content'], flags=re.S).strip()
        content = content.removeprefix('@charset "UTF-8";').strip()
        self.assertEqual(content, '@-moz-document url-prefix("http://"), url-prefix("https://") {\n'
                         '    *, *::before, *::after {\n'
                         '        border-radius: 0 !important;\n'
                         '    }\n}')

    def test_zero_to_positive_rerun_contains_no_radius_overrides(self):
        theme = copy.deepcopy(self.defaults)
        self.select(theme)
        square = self.generate()
        self.assertIn('border-radius:', square['content'])
        for rounding in (1, 12, 100):
            with self.subTest(rounding=rounding):
                theme['hyprland']['decoration']['rounding'] = rounding
                self.select(theme)
                rounded = self.generate()
                self.assertNotIn('radius', rounded['chrome'])
                self.assertNotIn('radius', rounded['content'])
                self.assertNotIn('corner-shape', rounded['chrome'])
                self.assertEqual(re.sub(r'/\*.*?\*/', '', rounded['content'], flags=re.S).strip(),
                                 '@charset "UTF-8";')
                self.assertIn('--zen-primary-color:', rounded['chrome'])
        theme['hyprland']['decoration']['rounding'] = 0
        self.select(theme)
        self.assertEqual(self.generate(), square)

    def test_selected_dark_and_light_snapshots_supply_palette_and_font_defaults(self):
        for mode in ('dark', 'light'):
            with self.subTest(mode=mode):
                theme = copy.deepcopy(self.defaults)
                theme['colors']['mode'] = mode
                for index, role in enumerate(theme['colors']):
                    if role != 'mode':
                        theme['colors'][role] = f'#{index:02x}1234'
                theme['fonts']['ui'] = 'Selected UI'
                theme['fonts']['mono'] = 'Selected Monospace'
                self.select(theme)
                styles = self.generate()
                chrome = styles['chrome']
                for name, role in {
                    '--zen-primary-color': 'accent',
                    '--zen-main-browser-background': 'background',
                    '--zen-colors-border': 'muted',
                    '--toolbox-textcolor': 'foreground',
                    '--tab-background-color-selected': 'selection',
                    '--in-content-primary-button-text-color': 'accent_foreground',
                }.items():
                    self.assertIn(f'{name}: {theme["colors"][role]} !important;', chrome)
                self.assertIn(f'color-scheme: {mode} !important;', chrome)
                self.assertIn('--luna-ui-font: "Selected UI", sans-serif !important;', chrome)
                self.assertEqual(styles['fonts'], {'ui': 'Selected UI', 'mono': 'Selected Monospace'})
                self.assertNotIn('Selected Monospace', chrome)
                self.assertNotRegex(styles['content'], r'(?:color|font|#[0-9a-f]{6})')

    def test_font_preference_is_escaped_as_one_css_string(self):
        font = 'My "UI" \\ face; } /* harmless */ Ω'
        mono = 'My "Mono" \\ font Ω'
        (self.config / 'fonts.json').write_text(json.dumps({'ui': font, 'mono': mono}))
        theme = copy.deepcopy(self.defaults)
        theme['fonts']['ui'] = 'Replaced UI'
        self.select(theme)
        styles = self.generate()
        escaped = font.replace('\\', '\\\\').replace('"', '\\"')
        self.assertIn(f'--luna-ui-font: "{escaped}", sans-serif !important;', styles['chrome'])
        self.assertNotIn('Replaced UI', styles['chrome'])
        self.assertNotIn(font, styles['content'])
        self.assertEqual(styles['fonts'], {'ui': font, 'mono': mono})
        self.assertNotIn(mono, styles['content'])

    def test_changed_personal_fonts_refresh_payload_and_keep_sites_in_control(self):
        theme = copy.deepcopy(self.defaults)
        theme['fonts'] = {'ui': 'Theme UI', 'mono': 'Theme Mono'}
        self.select(theme)
        preferences = self.config / 'fonts.json'
        preferences.write_text(json.dumps({'ui': 'Personal UI', 'mono': 'Personal Mono'}))
        first = self.generate()
        self.assertEqual(first['fonts'], {'ui': 'Personal UI', 'mono': 'Personal Mono'})

        # Removing an override restores the selected theme's family on the next
        # generation; a monospace-only change must not add website font rules.
        preferences.write_text(json.dumps({'mono': 'Next Mono'}))
        second = self.generate()
        self.assertEqual(second['fonts'], {'ui': 'Theme UI', 'mono': 'Next Mono'})
        self.assertIn('--luna-ui-font: "Theme UI", sans-serif !important;', second['chrome'])
        self.assertNotIn('Personal UI', second['chrome'])
        self.assertEqual(first['content'], second['content'])
        self.assertNotIn('font', second['content'])

    def test_checkout_and_driver_symlink_paths_are_shell_quoted(self):
        checkout = self.root / "checkout ' $(touch injected)"
        driver = checkout / 'scripts/setup/build-app.lua'
        driver.parent.mkdir(parents=True)
        shutil.copyfile(DRIVER, driver)
        shutil.copytree(REPO / 'apps/zen', checkout / 'apps/zen')
        shutil.copytree(REPO / 'lib', checkout / 'lib')
        link = self.root / "builder's link.lua"
        link.symlink_to(driver)
        self.assertEqual(self.generate(driver=link), self.generate())
        self.assertFalse((self.root / 'injected').exists())

    def test_empty_and_unset_xdg_config_use_home(self):
        config = self.home / '.config/luna'
        config.mkdir(parents=True)
        (config / 'fonts.json').write_text(json.dumps({'ui': 'Home UI', 'mono': 'Home Mono'}))
        for value in ('', None):
            with self.subTest(XDG_CONFIG_HOME=value):
                env = self.env.copy()
                if value is None:
                    env.pop('XDG_CONFIG_HOME')
                else:
                    env['XDG_CONFIG_HOME'] = value
                styles = self.generate(env=env)
                self.assertIn('--luna-ui-font: "Home UI", sans-serif !important;', styles['chrome'])
                self.assertEqual(styles['fonts'], {'ui': 'Home UI', 'mono': 'Home Mono'})

    def test_missing_malformed_or_incomplete_selection_writes_no_partial_styles(self):
        for contents in (None, '{bad json', '{"version":1,"name":"custom"}'):
            with self.subTest(contents=contents):
                (self.config / 'theme').write_text('custom\n')
                snapshot = self.config / 'theme.json'
                if contents is not None:
                    snapshot.write_text(contents)
                self.generate(ok=False)
                snapshot.unlink(missing_ok=True)

    def test_invalid_colors_rounding_and_fonts_write_no_partial_styles(self):
        for section, key, value in (
            ('colors', 'background', '#fff; color:red'),
            ('fonts', 'ui', 'Invalid\nFont'),
            ('fonts', 'mono', 'Invalid\nMonospace'),
        ):
            with self.subTest(section=section):
                theme = copy.deepcopy(self.defaults)
                theme[section][key] = value
                self.select(theme)
                self.generate(ok=False)
        theme = copy.deepcopy(self.defaults)
        theme['hyprland']['decoration']['rounding'] = -1
        self.select(theme)
        self.assertIn('Invalid decoration.rounding', self.generate(ok=False))
        self.select(self.defaults)
        for role in ('ui', 'mono'):
            with self.subTest(font_preference=role):
                (self.config / 'fonts.json').write_text(json.dumps({role: 'Invalid\nFont'}))
                self.assertIn('Invalid font family', self.generate(ok=False))


if __name__ == '__main__':
    unittest.main()
