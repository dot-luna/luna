"""Exercise wallpaper's Lua config API with temporary files and no renderer."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest


REPO = Path(__file__).resolve().parents[4]


class WallpaperConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luna config 'quoted' ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "config/luna/wallpaper.toml"
        self.env = dict(os.environ, HOME=str(self.root / "home"),
                        XDG_CONFIG_HOME=str(self.root / "config"),
                        LUNA_WALLPAPER_CONFIG="", TEST_REPO=str(REPO),
                        WAYLAND_DISPLAY="", HYPRLAND_INSTANCE_SIGNATURE="", PATH="")

    def lua(self, source, ok=True):
        # An empty PATH and unset desktop session prevent accidental tool launches.
        # The API uses only absolute system Lua/Python and the checked-in common helper.
        prelude = '''
local root = assert(os.getenv("TEST_REPO"))
local config = dofile(root .. "/src/wallpaper/src/config.lua")(dofile(root .. "/lib/common.lua"), root)
local function set_source(source) return config.update({wallpaper = {source = source}}) end
'''
        result = subprocess.run(["/usr/bin/lua", "-E", "-"], input=prelude + source,
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return result

    def write(self, document):
        self.config.parent.mkdir(parents=True, exist_ok=True)
        self.config.write_text(document)

    def saved(self):
        return tomllib.loads(self.config.read_text())

    def test_reading_missing_config_never_creates_files(self):
        self.lua('assert(config.get().wallpaper.fit == "fill"); assert(config.get("wallpaper.source") == "")')
        self.assertFalse(self.config.exists())
        self.assertFalse(self.config.parent.exists())

    def test_get_returns_unknown_tables_arrays_and_toml_only_values(self):
        self.write('''[wallpaper]
source = "/image.png"
[custom]
names = ["first", "second"]
day = 2026-01-01
count = nan
[[outputs]]
name = "DP-1"
''')
        self.lua('''
local value = config.get()
assert(value.wallpaper.source == "/image.png")
assert(value.custom.names[2] == "second")
assert(value.outputs[1].name == "DP-1")
assert(type(value.custom.day) == "table" and value.custom.day == value.custom.count)
''')

    def test_partial_edit_preserves_comments_unknown_options_and_other_values(self):
        self.write('''# My wallpaper
[wallpaper]
source = "/old.png" # My image
fit = "center" # Image placement
background_color = "#123456"
custom = "leave this"
[playback]
pause_when_output_inactive = true
[transition]
type = "fade"
duration_ms = 200
[outputs."DP-1".wallpaper]
source = "/monitor.png"
[custom]
date = 2026-01-01 # Keep non-JSON data
''')
        self.lua('''
local result = config.update({wallpaper = {fit = "fit"},
    playback = {pause_when_output_inactive = false}, transition = {duration_ms = 0}})
assert(result.wallpaper.fit == "fit" and result.wallpaper.source == "/old.png")
assert(result.playback.pause_when_output_inactive == false)
assert(result.transition.duration_ms == 0 and result.transition.type == "fade")
''')
        for unchanged in ('# My wallpaper', '# My image', '# Image placement',
                          'background_color = "#123456"', 'custom = "leave this"',
                          '[outputs."DP-1".wallpaper]', 'source = "/monitor.png"',
                          'date = 2026-01-01 # Keep non-JSON data'):
            self.assertIn(unchanged, self.config.read_text())

    def test_invalid_updates_reject_the_whole_patch_without_touching_file(self):
        self.write('[wallpaper]\nsource = "/old.png"\nfit = "fit"\n')
        before = self.config.read_bytes(), self.config.stat().st_mtime_ns
        for patch in (
            '{wallpaper = {source = "relative.png"}}',
            '{wallpaper = {fit = "invalid", background_color = "#abcdef"}}',
            '{wallpaper = {background_color = "blue"}}',
            '{playback = {pause_when_output_inactive = "false"}}',
            '{transition = {type = "invalid"}}',
            *(f'{{transition = {{duration_ms = {value}}}}}' for value in
              ('-1', '0/0', 'math.huge', '1.5', '2147483648')),
            '{wallpaper = {source = "/bad\\nname"}}', 'false',
        ):
            with self.subTest(patch=patch):
                result = self.lua('config.update(' + patch + ')', ok=False)
                self.assertIn('config', result.stderr.lower())
                self.assertEqual((self.config.read_bytes(), self.config.stat().st_mtime_ns), before)
        self.lua('config.update({wallpaper = {fit = "fit"}})')
        self.assertEqual((self.config.read_bytes(), self.config.stat().st_mtime_ns), before)

    def test_update_creates_only_requested_options_and_write_can_clear_source(self):
        self.lua('config.update({transition = {type = "none", duration_ms = 2147483647}})')
        self.assertEqual(self.saved(), {'transition': {'type': 'none', 'duration_ms': 2147483647}})
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        self.lua('set_source("/image.png"); assert(config.get("wallpaper.source") == "/image.png"); set_source("")')
        self.assertEqual(self.saved()['wallpaper']['source'], '')
        self.lua('assert(config.get("wallpaper.source") == "")')

    def test_empty_or_invalid_update_does_not_create_file(self):
        self.lua("config.update({})")
        self.lua('config.update({wallpaper = {fit = "wrong"}})', ok=False)
        self.assertFalse(self.config.exists())

    def test_all_fit_values_and_correct_scalar_types(self):
        self.lua('''
for _, fit in ipairs({"fill", "fit", "stretch", "center", "tile"}) do
    assert(config.update({wallpaper = {fit = fit}}).wallpaper.fit == fit)
end
config.update({playback = {pause_when_output_inactive = false}, transition = {duration_ms = 1}})
''')
        self.assertIs(self.saved()['playback']['pause_when_output_inactive'], False)
        self.assertIs(type(self.saved()['transition']['duration_ms']), int)

    def test_invalid_file_fails_reads_and_unrelated_edits_but_can_be_repaired(self):
        self.write('[wallpaper]\nfit = "invalid"\n[custom]\nvalue = false\n')
        before = self.config.read_bytes()
        for code in ('config.get()', 'config.get("custom.value")',
                     'config.update({wallpaper = {background_color = "#123456"}})'):
            result = self.lua(code, ok=False)
            self.assertIn('fit', result.stderr)
            self.assertEqual(self.config.read_bytes(), before)
        self.lua('assert(config.update({wallpaper = {fit = "fill"}}).wallpaper.fit == "fill")')
        self.assertFalse(self.saved()['custom']['value'])

    def test_empty_and_null_only_patches_cannot_partially_write_invalid_config(self):
        self.write('wallpaper = "bad"\n[transition]\nduration_ms = 100\n')
        before = self.config.read_bytes(), self.config.stat().st_mtime_ns
        for patch in ('{}', '{future = dofile(root .. "/lib/json.lua").null}'):
            with self.subTest(patch=patch):
                self.lua('config.update({wallpaper = ' + patch
                         + ', transition = {duration_ms = 500}})', ok=False)
                self.assertEqual((self.config.read_bytes(), self.config.stat().st_mtime_ns), before)
        # A real replacement can repair the bad section and apply its neighboring edit.
        self.lua('config.update({wallpaper = {fit = "fill"}, transition = {duration_ms = 500}})')
        self.assertEqual(self.saved()['wallpaper'], {'fit': 'fill'})
        self.assertEqual(self.saved()['transition']['duration_ms'], 500)

    def test_runtime_defaults_come_from_the_app_config(self):
        checkout = self.root / "checkout"
        for relative in ("src/wallpaper/src/config.lua", "src/wallpaper/src/read.lua", "lib/config.lua", "lib/toml.lua",
                         "lib/common.lua", "lib/json.lua", "lib/validation.lua",
                         "lib/vendor/tableshape/init.lua", "apps/luna-wallpaper/config/wallpaper.toml"):
            target = checkout / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / relative, target)
        defaults = checkout / "apps/luna-wallpaper/config/wallpaper.toml"
        defaults.write_text(defaults.read_text().replace('fit = "fill"', 'fit = "stretch"')
                            .replace('duration_ms = 200', 'duration_ms = 77'))
        self.env["TEST_REPO"] = str(checkout)
        self.write('[wallpaper]\nsource = ""\n')
        before = self.config.read_bytes()
        self.lua('assert(config.get("wallpaper.fit") == "stretch"); '
                 'assert(config.get("transition.duration_ms") == 77)')
        self.assertEqual(self.config.read_bytes(), before)

    def test_symlink_and_target_permissions_survive_atomic_edit(self):
        target = self.root / "user settings.toml"
        target.write_text('[wallpaper]\nsource = "/old.png"\n')
        target.chmod(0o640)
        self.config.parent.mkdir(parents=True)
        self.config.symlink_to(target)
        self.env['TEST_SOURCE'] = "/a 'quote' $(unchanged) # image.png"
        self.lua('set_source(assert(os.getenv("TEST_SOURCE")))')
        self.assertTrue(self.config.is_symlink())
        self.assertEqual(self.saved()['wallpaper']['source'], self.env['TEST_SOURCE'])
        self.assertEqual(target.stat().st_mode & 0o777, 0o640)
        self.assertEqual(list(self.root.glob('.luna-toml-*')), [])

    def test_config_environment_precedence_and_empty_fallbacks(self):
        custom = self.root / "custom/config.toml"
        self.env['LUNA_WALLPAPER_CONFIG'] = str(custom)
        self.lua('assert(config.file() == os.getenv("LUNA_WALLPAPER_CONFIG")); set_source("/first.png")')
        self.assertTrue(custom.is_file())
        self.assertFalse(self.config.exists())
        self.env.update(LUNA_WALLPAPER_CONFIG='', XDG_CONFIG_HOME='')
        self.lua('set_source("/second.png")')
        home_config = self.root / 'home/.config/luna/wallpaper.toml'
        self.assertEqual(tomllib.loads(home_config.read_text())['wallpaper']['source'], '/second.png')

    def test_malformed_file_is_preserved(self):
        self.write('[wallpaper\nsource = bad')
        before = self.config.read_bytes()
        for source in ('config.get()', 'config.get("wallpaper.source")', 'set_source("/image.png")',
                       'config.update({wallpaper = {fit = "fit"}})'):
            self.lua(source, ok=False)
            self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(list(self.config.parent.glob('.luna-toml-*')), [])

    def test_checked_in_reference_is_readable_but_never_rewritten(self):
        reference = REPO / 'src/wallpaper/config.toml'
        before = reference.read_bytes()
        self.config.parent.mkdir(parents=True)
        self.config.symlink_to(reference)
        self.lua('assert(type(config.get()) == "table")')
        self.lua('set_source("/forbidden-write.png")', ok=False)
        self.assertEqual(reference.read_bytes(), before)
        self.assertTrue(self.config.is_symlink())


if __name__ == '__main__':
    unittest.main()
