"""Deploy Starship's static config without touching the user's existing config."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest

from __tests__.scripts.setup.app_fixture import copy_app_setup


REPO = Path(__file__).resolve().parents[3]


class SetupStarshipTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna starship '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.checkout = self.root / "checkout"
        copy_app_setup(self.checkout)
        self.source = self.checkout / "apps/starship/config/starship.toml"
        self.config_home = self.home / ".config"
        self.destination = self.config_home / "luna/starship/starship.toml"
        self.env = dict(os.environ, HOME=str(self.home), XDG_CONFIG_HOME=str(self.config_home))
        for name in ("LUNA_CONFIG_DIR", "STARSHIP_CONFIG", "BASH_ENV", "ENV"):
            self.env.pop(name, None)

    def setup(self, *arguments, entry=None):
        script = entry or self.checkout / "scripts/setup/starship.sh"
        return subprocess.run(["bash", str(script), *arguments], env=self.env, cwd=self.root,
                              input="", capture_output=True, text=True, timeout=10)

    def assert_installed(self, result, destination=None):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        target = destination or self.destination
        self.assertFalse(target.is_symlink())
        self.assertEqual(target.read_bytes(), self.source.read_bytes())
        self.assertEqual(list(target.parent.parent.glob(".starship-*")), [])

    def test_default_deployment_preserves_personal_config_and_has_valid_toml(self):
        self.config_home.mkdir()
        personal = self.config_home / "starship.toml"
        original = b"# Personal prompt\ncommand_timeout = 321\n"
        personal.write_bytes(original)
        self.env.pop("XDG_CONFIG_HOME")
        self.assert_installed(self.setup("--help", "--unknown"))
        self.assertEqual(personal.read_bytes(), original)
        self.assertEqual(tomllib.loads(self.destination.read_text())["command_timeout"], 200)
        self.assertEqual(list(self.home.rglob("*.luna-backup*")), [])

    def test_custom_luna_destination_takes_precedence_over_xdg(self):
        custom = self.root / "configs ' $HOME $(touch INJECTED)"
        self.env["LUNA_CONFIG_DIR"] = str(custom)
        self.assert_installed(self.setup(), custom / "starship/starship.toml")
        self.assertFalse(self.config_home.exists())
        self.assertFalse((self.root / "INJECTED").exists())

    def test_xdg_override_and_empty_luna_value_use_xdg_destination(self):
        custom = self.root / "custom config"
        self.env["XDG_CONFIG_HOME"] = str(custom)
        self.env["LUNA_CONFIG_DIR"] = ""
        self.assert_installed(self.setup(), custom / "luna/starship/starship.toml")
        self.assertFalse(self.config_home.exists())

    def test_rerun_refreshes_only_the_installed_file(self):
        self.assert_installed(self.setup())
        extra = self.destination.parent / "personal.toml"
        extra.write_text("# Kept\n")
        self.source.write_text("command_timeout = 987\n")
        self.assert_installed(self.setup())
        self.assertEqual(extra.read_text(), "# Kept\n")

    def test_missing_source_does_not_corrupt_the_previous_config(self):
        self.assert_installed(self.setup())
        previous = self.destination.read_bytes()
        self.source.unlink()
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.destination.read_bytes(), previous)
        self.assertEqual(list(self.destination.parent.parent.glob(".starship-*")), [])

    def test_destination_file_symlink_is_replaced_without_touching_its_target(self):
        personal = self.root / "personal.toml"
        personal.write_text("# Preserve target\n")
        self.destination.parent.mkdir(parents=True)
        self.destination.symlink_to(personal)
        self.assert_installed(self.setup())
        self.assertEqual(personal.read_text(), "# Preserve target\n")

    def test_destination_directory_symlink_is_rejected(self):
        personal = self.root / "personal"
        personal.mkdir()
        original = personal / "starship.toml"
        original.write_text("# Preserve target\n")
        self.destination.parent.parent.mkdir(parents=True)
        self.destination.parent.symlink_to(personal)
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.destination.parent.is_symlink())
        self.assertEqual(original.read_text(), "# Preserve target\n")

    def test_destination_alias_into_checkout_is_rejected(self):
        alias = self.root / "source alias"
        alias.symlink_to(self.checkout / "apps")
        self.env["LUNA_CONFIG_DIR"] = str(alias)
        original = self.source.read_bytes()
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(list((self.checkout / "apps").glob(".starship-*")), [])

    def test_directory_in_place_of_config_is_not_removed(self):
        self.destination.mkdir(parents=True)
        personal = self.destination / "personal"
        personal.write_text("Keep\n")
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(personal.read_text(), "Keep\n")

    def test_relative_destination_is_rejected(self):
        self.env["LUNA_CONFIG_DIR"] = "relative config"
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.root / "relative config").exists())

    def test_symlink_entry_uses_its_actual_checkout(self):
        entry = self.root / "install starship"
        entry.symlink_to(self.checkout / "scripts/setup/starship.sh")
        self.assert_installed(self.setup(entry=entry))


if __name__ == "__main__":
    unittest.main()
