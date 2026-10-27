"""Exercise screensaver config installation only inside disposable homes."""

import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest

from __tests__.scripts.setup.app_fixture import copy_app_setup


@unittest.skipUnless(Path("/usr/bin/lua").is_file(), "App setup requires /usr/bin/lua")
class SetupScreensaverTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna screensaver '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.checkout = self.root / "checkout"
        copy_app_setup(self.checkout)
        self.config_home = self.home / ".config"
        self.active = self.config_home / "luna/screensaver.toml"
        self.destination = self.config_home / "luna/luna-screensaver"
        self.env = {"HOME": str(self.home), "PATH": os.environ["PATH"], "NO_COLOR": "1",
                    "XDG_CONFIG_HOME": str(self.config_home), "LUNA_SETUP_APP": "luna-screensaver"}

    def setup(self):
        return subprocess.run(
            ["/usr/bin/lua", "-E", str(self.checkout / "scripts/setup/10-setup-app-configs.lua")],
            cwd=self.root, env=self.env, input="", capture_output=True, text=True, timeout=10,
        )

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_first_install_seeds_defaults_without_a_selected_theme(self):
        self.assert_success(self.setup())
        self.assertEqual(tomllib.loads(self.active.read_text()), {
            "idle": {"screensaver_seconds": 300, "lock_seconds": 600, "display_off_seconds": 0},
            "renderer": {"shell": ""}, "settings": {},
        })
        self.assertEqual(self.active.read_bytes(), (self.destination / "screensaver.toml").read_bytes())
        self.assertEqual(self.active.stat().st_mode & 0o777, 0o600)
        self.assertFalse(self.active.is_symlink())
        self.assertEqual({path.name for path in self.destination.iterdir()}, {"screensaver.toml"})

    def test_reruns_preserve_personal_bytes_permissions_and_timestamp(self):
        self.active.parent.mkdir(parents=True)
        for content in (b'# Personal\r\n[idle]\r\nlock_seconds = 120', b"[unfinished TOML\xff"):
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

    def test_runtime_override_is_independent_of_installed_app_store(self):
        active = self.root / "my settings/screensaver.toml"
        store = self.root / "app store"
        self.env.update(LUNA_CONFIG_DIR=str(store), LUNA_SCREENSAVER_CONFIG=str(active))
        self.assert_success(self.setup())
        self.assertTrue(active.is_file())
        self.assertTrue((store / "luna-screensaver/screensaver.toml").is_file())
        self.assertFalse(self.active.exists())
        self.assertFalse((store / "screensaver.toml").exists())

    def test_empty_or_unset_overrides_use_home_defaults(self):
        for value in ("", None):
            with self.subTest(value=value):
                for name in ("XDG_CONFIG_HOME", "LUNA_SCREENSAVER_CONFIG"):
                    if value is None:
                        self.env.pop(name, None)
                    else:
                        self.env[name] = value
                self.active.unlink(missing_ok=True)
                self.assert_success(self.setup())
                self.assertTrue(self.active.is_file())

    def test_personal_symlinks_keep_links_and_seed_only_missing_targets(self):
        self.active.parent.mkdir(parents=True)
        target = self.root / "personal/screensaver.toml"
        self.active.symlink_to(target)
        self.assert_success(self.setup())
        self.assertTrue(self.active.is_symlink())
        self.assertTrue(target.is_file())
        content = b"Keep unfinished personal edits\r\n"
        target.write_bytes(content)
        target.chmod(0o640)
        self.assert_success(self.setup())
        self.assertTrue(self.active.is_symlink())
        self.assertEqual(target.read_bytes(), content)
        self.assertEqual(target.stat().st_mode & 0o777, 0o640)

    def test_old_idle_file_is_untouched_and_not_imported(self):
        self.active.parent.mkdir(parents=True)
        old = self.active.parent / "idle.json"
        content = b'{"screensaver_seconds":17,"lock_seconds":31}'
        old.write_bytes(content)
        self.assert_success(self.setup())
        self.assertEqual(old.read_bytes(), content)
        self.assertEqual(tomllib.loads(self.active.read_text())["idle"]["screensaver_seconds"], 300)

    def test_source_and_installed_aliases_fail_before_publication(self):
        self.active.parent.mkdir(parents=True)
        source = self.checkout / "apps/luna-screensaver/config/screensaver.toml"
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
        installed = self.destination / "screensaver.toml"
        installed.symlink_to(personal)
        self.active.symlink_to(installed)
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(installed.is_symlink())
        self.assertEqual(personal.read_text(), "# Keep personal\n")

    def test_invalid_targets_fail_without_publishing_defaults(self):
        self.env["LUNA_SCREENSAVER_CONFIG"] = "relative.toml"
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.destination.exists())
        self.env.pop("LUNA_SCREENSAVER_CONFIG")
        self.active.mkdir(parents=True)
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.destination.exists())
        self.assertTrue(self.active.is_dir())
        self.active.rmdir()
        self.active.symlink_to(self.active)
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
