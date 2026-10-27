"""Check screensaver schema and comment-preserving offline TOML edits."""

import json
import tomllib
import unittest

from test_runtime import ScreensaverFixture


class ScreensaverConfigTests(ScreensaverFixture, unittest.TestCase):
    def test_defaults_do_not_create_files_and_settings_keep_shapes(self):
        self.lua('''
local value = screensaver.getConfig()
assert(value.idle.screensaver_seconds == 300 and value.idle.lock_seconds == 600)
assert(value.idle.display_off_seconds == 0 and value.renderer.shell == "")
assert(next(value.settings) == nil)
''')
        self.assertFalse(self.config.exists())
        self.lua('screensaver.updateConfig({settings = {clock = false, interval = 0, '
                 'colors = dofile(arg[1] .. "/lib/json.lua").array({"red", "blue"})}})')
        self.assertEqual(tomllib.loads(self.config.read_text()),
                         {"settings": {"clock": False, "interval": 0, "colors": ["red", "blue"]}})
        self.assertFalse(self.calls())

    def test_partial_update_preserves_comments_and_custom_settings(self):
        self.config.write_text('# Personal\n[idle]\nlock_seconds = 900 # Work\n[settings]\nlabel = "hello"\n')
        self.lua('screensaver.updateConfig({idle = {display_off_seconds = 1200}})')
        self.assertIn("# Personal", self.config.read_text())
        self.assertIn("# Work", self.config.read_text())
        saved = tomllib.loads(self.config.read_text())
        self.assertEqual(saved["idle"], {"lock_seconds": 900, "display_off_seconds": 1200})
        self.assertEqual(saved["settings"], {"label": "hello"})

    def test_invalid_updates_do_not_touch_existing_file(self):
        self.config.write_text('[idle]\nlock_seconds = 900\n')
        original = self.config.read_bytes(), self.config.stat().st_mtime_ns
        patches = ['{idle = {lock_seconds = -1}}', '{idle = {screensaver_seconds = 1.2}}',
                   '{idle = {display_off_seconds = 86401}}', '{idle = {lock_seconds = false}}',
                   '{renderer = {shell = "relative.qml"}}', '{renderer = {shell = "/script.sh"}}',
                   '{renderer = {shell = "/bad\\nfile.qml"}}', '{settings = false}',
                   '{settings = dofile(arg[1] .. "/lib/json.lua").array({})}', 'false']
        for patch in patches:
            with self.subTest(patch=patch):
                self.lua(f'screensaver.updateConfig({patch})', ok=False)
                self.assertEqual((self.config.read_bytes(), self.config.stat().st_mtime_ns), original)
        self.assertFalse(self.calls())

    def test_quoted_custom_shell_paths_roundtrip_without_execution(self):
        for path in ("~/my shell.qml", "/tmp/custom ' $(touch INJECTED); `touch ALSO`.qml", ""):
            # Lua receives the path through JSON, preserving all literal characters.
            self.env["TEST_SHELL_PATH"] = json.dumps({"renderer": {"shell": path}})
            self.lua('screensaver.updateConfig(dofile(arg[1] .. "/lib/json.lua").decode(os.getenv("TEST_SHELL_PATH")))')
            self.assertEqual(tomllib.loads(self.config.read_text())["renderer"]["shell"], path)
        self.assertFalse((self.root / "INJECTED").exists())
        self.assertFalse((self.root / "ALSO").exists())
        self.assertFalse(self.calls())

    def test_override_path_and_file_getter_work_without_parsing(self):
        path = self.root / "custom config/screensaver.toml"
        self.env["LUNA_SCREENSAVER_CONFIG"] = str(path)
        self.lua('screensaver.updateConfig({idle = {lock_seconds = 0}}); '
                 'assert(screensaver.getConfigFile() == os.getenv("LUNA_SCREENSAVER_CONFIG"))')
        self.assertEqual(tomllib.loads(path.read_text())["idle"]["lock_seconds"], 0)
        path.write_text("[broken")
        self.lua('assert(screensaver.getConfigFile() == os.getenv("LUNA_SCREENSAVER_CONFIG"))')
        self.lua('screensaver.getConfig()', ok=False)
        self.assertFalse(self.calls())

    def test_invalid_existing_config_must_be_repaired_before_unrelated_edits(self):
        self.config.write_text('[idle]\nlock_seconds = -1\n[settings]\nclock = true\n')
        original = self.config.read_bytes()
        self.lua('screensaver.updateConfig({settings = {clock = false}})', ok=False)
        self.assertEqual(self.config.read_bytes(), original)
        self.lua('screensaver.updateConfig({idle = {lock_seconds = 600}})')
        self.assertEqual(tomllib.loads(self.config.read_text())["idle"]["lock_seconds"], 600)


if __name__ == "__main__":
    unittest.main()
