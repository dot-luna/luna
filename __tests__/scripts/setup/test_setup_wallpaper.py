"""Exercise wallpaper config generation and preservation inside disposable homes."""

import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest

from __tests__.scripts.setup.app_fixture import copy_app_setup


REPO = Path(__file__).resolve().parents[3]


@unittest.skipUnless(Path("/usr/bin/lua").is_file(), "The builder requires /usr/bin/lua")
class SetupWallpaperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Reuse the complete theme schema; the tests only customize its sources.
        result = subprocess.run(
            ["/usr/bin/lua", "-E", "-", str(REPO)],
            input='local root = arg[1]; print(dofile(root .. "/lib/json.lua").encode('
                  'dofile(root .. "/lib/theme/defaults.lua")))',
            capture_output=True, text=True, check=True,
        )
        cls.defaults = json.loads(result.stdout)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna wallpaper '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.checkout = self.root / "checkout"
        copy_app_setup(self.checkout)
        self.config_home = self.home / ".config"
        self.data_home = self.home / ".local/share"
        self.active = self.config_home / "luna/wallpaper.toml"
        self.destination = self.config_home / "luna/luna-wallpaper"
        self.installed_theme = self.data_home / "luna/themes/custom"
        self.env = {"HOME": str(self.home), "PATH": os.environ["PATH"], "NO_COLOR": "1",
                    "XDG_CONFIG_HOME": str(self.config_home), "XDG_DATA_HOME": str(self.data_home),
                    "LUNA_SETUP_APP": "luna-wallpaper"}

    def setup(self):
        return subprocess.run(
            ["/usr/bin/lua", "-E", str(self.checkout / "scripts/setup/10-setup-app-configs.lua")],
            cwd=self.root, env=self.env, input="", capture_output=True, text=True, timeout=10,
        )

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def select(self, sources=(), background="#123456"):
        theme = copy.deepcopy(self.defaults)
        theme.update(version=1, name="custom")
        theme["colors"]["background"] = background
        theme["wallpaper"]["sources"] = list(sources)
        directory = self.config_home / "luna"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "theme").write_text("custom\n")
        (directory / "theme.json").write_text(json.dumps(theme))

    def image(self, name):
        path = self.installed_theme / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"Fixture media; config setup never decodes or launches it.")
        return path

    def test_theme_source_and_color_create_editable_native_config(self):
        source = self.image('wallpapers/café "quoted" $HOME $(touch INJECTED) \\ image.png')
        self.select(["https://example.invalid/no-download.png", "/outside.png", "../outside.png",
                     "missing.png", "wallpapers", str(source.relative_to(self.installed_theme)),
                     str(self.image("second.png").relative_to(self.installed_theme))])
        self.assert_success(self.setup())
        settings = tomllib.loads(self.active.read_text())
        self.assertEqual(settings["wallpaper"], {
            "source": str(source), "fit": "fill", "background_color": "#123456",
        })
        self.assertEqual(settings["playback"], {"pause_when_output_inactive": True})
        self.assertEqual(settings["transition"], {"type": "fade", "duration_ms": 200})
        self.assertEqual(self.active.read_bytes(), (self.destination / "wallpaper.toml").read_bytes())
        self.assertEqual(self.active.stat().st_mode & 0o777, 0o600)
        self.assertFalse(self.active.is_symlink())
        self.assertEqual({path.name for path in self.destination.iterdir()}, {"wallpaper.toml"})
        self.assertFalse((self.root / "INJECTED").exists())

    def test_no_source_keeps_theme_background(self):
        self.select(["missing.png", "https://example.invalid/wallpaper.png"])
        self.assert_success(self.setup())
        wallpaper = tomllib.loads(self.active.read_text())["wallpaper"]
        self.assertEqual(wallpaper["source"], "")
        self.assertEqual(wallpaper["background_color"], "#123456")

    def test_existing_valid_and_malformed_files_are_preserved_byte_for_byte(self):
        self.select()
        for content in (b'# Personal\r\n[wallpaper]\r\nsource = ""\r\nfit = "fit"', b"[invalid TOML\xff"):
            with self.subTest(content=content):
                self.active.write_bytes(content)
                self.active.chmod(0o640)
                before = self.active.stat().st_mtime_ns
                self.assert_success(self.setup())
                self.assert_success(self.setup())
                self.assertEqual(self.active.read_bytes(), content)
                self.assertEqual(self.active.stat().st_mtime_ns, before)
                self.assertEqual(self.active.stat().st_mode & 0o777, 0o640)
        self.assertEqual(list(self.home.rglob("*.luna-backup*")), [])

    def test_rerun_refreshes_store_but_preserves_original_personal_theme(self):
        self.select([str(self.image("first.png").relative_to(self.installed_theme))])
        self.assert_success(self.setup())
        original = self.active.read_bytes()
        self.select([str(self.image("second.png").relative_to(self.installed_theme))], "#654321")
        self.assert_success(self.setup())
        self.assertEqual(self.active.read_bytes(), original)
        stored = tomllib.loads((self.destination / "wallpaper.toml").read_text())
        self.assertEqual(stored["wallpaper"]["background_color"], "#654321")
        self.assertTrue(stored["wallpaper"]["source"].endswith("/second.png"))

    def test_empty_xdg_and_config_override_use_home_defaults(self):
        self.select([str(self.image("default.png").relative_to(self.installed_theme))])
        for value in ("", None):
            with self.subTest(value=value):
                for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "LUNA_WALLPAPER_CONFIG"):
                    if value is None:
                        self.env.pop(name, None)
                    else:
                        self.env[name] = value
                self.active.unlink(missing_ok=True)
                self.assert_success(self.setup())
                self.assertEqual(tomllib.loads(self.active.read_text())["wallpaper"]["source"],
                                 str(self.installed_theme / "default.png"))

    def test_runtime_override_and_app_store_are_independent(self):
        self.select()
        active = self.root / "my settings/wallpaper.toml"
        store = self.root / "app store"
        self.env["LUNA_CONFIG_DIR"] = str(store)
        self.assert_success(self.setup())
        self.assertTrue(self.active.is_file())
        self.assertFalse((store / "wallpaper.toml").exists())
        self.active.unlink()

        self.env["LUNA_WALLPAPER_CONFIG"] = str(active)
        self.assert_success(self.setup())
        self.assertTrue(active.is_file())
        self.assertTrue((store / "luna-wallpaper/wallpaper.toml").is_file())
        self.assertFalse(self.active.exists())
        self.assertFalse((store / "wallpaper.toml").exists())

    def test_personal_symlinks_preserve_existing_and_seed_missing_targets(self):
        self.select()
        target = self.root / "personal/wallpaper.toml"
        target.parent.mkdir()
        self.active.symlink_to(target)
        self.assert_success(self.setup())
        self.assertTrue(self.active.is_symlink())
        self.assertTrue(target.is_file())
        original = b"Keep even unfinished personal edits\r\n"
        target.write_bytes(original)
        target.chmod(0o640)
        self.assert_success(self.setup())
        self.assertTrue(self.active.is_symlink())
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(target.stat().st_mode & 0o777, 0o640)

    def test_source_and_installed_aliases_are_rejected_before_publication(self):
        self.select()
        source = self.checkout / "apps/luna-wallpaper/config/wallpaper.toml"
        original = source.read_bytes()
        self.active.symlink_to(source)
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(source.read_bytes(), original)
        self.assertFalse(self.destination.exists())
        self.active.unlink()
        self.destination.mkdir()
        personal = self.root / "personal.toml"
        personal.write_text("# Keep personal\n")
        installed = self.destination / "wallpaper.toml"
        installed.symlink_to(personal)
        self.active.symlink_to(installed)
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(installed.is_symlink())
        self.assertEqual(personal.read_text(), "# Keep personal\n")

    def test_relative_override_and_directory_conflicts_do_not_publish_defaults(self):
        self.select()
        self.env["LUNA_WALLPAPER_CONFIG"] = "relative.toml"
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.destination.exists())
        self.env.pop("LUNA_WALLPAPER_CONFIG")
        self.active.mkdir()
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.destination.exists())
        self.assertTrue(self.active.is_dir())


if __name__ == "__main__":
    unittest.main()
