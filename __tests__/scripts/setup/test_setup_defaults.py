"""Check default-terminal setup using isolated preferences and harmless commands."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]


class SetupDefaultsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna defaults '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.config_home = self.home / ".config"
        self.checkout = self.root / "checkout"
        for name in ("scripts/setup/defaults.sh", "lib/common.sh"):
            destination = self.checkout / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, destination)

        # A closed PATH prevents tests from launching an installed terminal.
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for name in ("bash", "readlink", "dirname"):
            (self.bin / name).symlink_to(shutil.which(name))
        (self.bin / "kitty").write_text("#!/bin/sh\nexit 99\n")
        (self.bin / "kitty").chmod(0o755)
        (self.bin / "xdg-terminal-exec").write_text(f"#!{sys.executable}\n" + '''
import os, pathlib, sys
assert sys.argv[1:] == ["--print-id"], "Setup must never launch a terminal"
assert os.environ["XTE_CACHE_ENABLED"] == "0"
pathlib.Path(os.environ["HOME"], "verified").touch()
print(os.environ.get("TEST_TERMINAL_ID", "kitty.desktop"))
sys.exit(int(os.environ.get("TEST_TERMINAL_STATUS", "0")))
''')
        (self.bin / "xdg-terminal-exec").chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.home), PATH=str(self.bin),
                        XDG_CONFIG_HOME=str(self.config_home), XDG_CURRENT_DESKTOP="Hyprland",
                        BASH_ENV="", NO_COLOR="1")
        for name in ("TEST_TERMINAL_ID", "TEST_TERMINAL_STATUS"):
            self.env.pop(name, None)

    def setup(self, *arguments):
        return subprocess.run([str(self.bin / "bash"),
                               str(self.checkout / "scripts/setup/defaults.sh"), *arguments],
                              env=self.env, cwd=self.root, input="", capture_output=True,
                              text=True, timeout=5)

    def test_new_preferences_use_default_xdg_path_and_ignore_extra_arguments(self):
        self.env.pop("XDG_CONFIG_HOME")
        self.env.pop("XDG_CURRENT_DESKTOP")
        result = self.setup("--help", "--unknown", "extra")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Default terminal set to Kitty", result.stdout)
        self.assertIn("without backups", result.stderr)
        for name in ("xdg-terminals.list", "hyprland-xdg-terminals.list"):
            self.assertEqual((self.config_home / name).read_bytes(), b"kitty.desktop\n")
        self.assertTrue((self.home / "verified").exists())
        self.assertEqual({path.name for path in self.config_home.iterdir()},
                         {"xdg-terminals.list", "hyprland-xdg-terminals.list"})

    def test_empty_xdg_config_home_uses_home(self):
        self.env["XDG_CONFIG_HOME"] = ""
        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.config_home / "xdg-terminals.list").is_file())

    def test_preserves_lists_symlinks_modes_and_other_desktops_on_rerun(self):
        self.home.mkdir()
        config = self.root / "custom config"
        config.mkdir()
        self.env.update(XDG_CONFIG_HOME=str(config), XDG_CURRENT_DESKTOP="GNOME:Hyprland:GNOME",
                        LUNA_CONFIG_DIR=str(self.root / "luna configs"))
        original = b"# Saved preferences\r\nAlacritty.desktop\r\nkitty.desktop\n# Notes: \xff"
        target = self.root / "dotfiles/terminals.list"
        target.parent.mkdir()
        target.write_bytes(original)
        target.chmod(0o640)
        (config / "xdg-terminals.list").symlink_to(target)
        gnome = config / "gnome-xdg-terminals.list"
        gnome.write_bytes(b"org.gnome.Terminal.desktop\n")
        unrelated = config / "kde-xdg-terminals.list"
        unrelated.write_bytes(b"org.kde.konsole.desktop\n")

        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((config / "xdg-terminals.list").is_symlink())
        self.assertEqual(target.read_bytes(), b"kitty.desktop\n" + original)
        self.assertEqual(target.stat().st_mode & 0o777, 0o640)
        self.assertEqual(gnome.read_bytes(), b"kitty.desktop\norg.gnome.Terminal.desktop\n")
        self.assertEqual(unrelated.read_bytes(), b"org.kde.konsole.desktop\n")
        self.assertFalse((self.root / "luna configs").exists())

        before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in config.iterdir()}
        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, {path: (path.read_bytes(), path.stat().st_mtime_ns)
                                  for path in config.iterdir()})

    def test_missing_optional_commands_skip_without_changing_preferences(self):
        for name in ("kitty", "xdg-terminal-exec"):
            with self.subTest(command=name):
                command = self.bin / name
                saved = self.bin / f"saved-{name}"
                command.rename(saved)
                try:
                    result = self.setup()
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn(f"{name} is unavailable", result.stderr)
                    self.assertFalse(self.config_home.exists())
                finally:
                    saved.rename(command)

    def test_invalid_paths_fail_before_changing_preferences(self):
        self.env["XDG_CONFIG_HOME"] = "relative"
        result = self.setup()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("absolute path", result.stderr)
        self.assertFalse((self.root / "relative").exists())

        self.env["XDG_CONFIG_HOME"] = str(self.config_home)
        self.config_home.mkdir(parents=True)
        generic = self.config_home / "xdg-terminals.list"
        generic.write_bytes(b"Alacritty.desktop\n")
        (self.config_home / "hyprland-xdg-terminals.list").mkdir()
        result = self.setup()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Expected a terminal preference file", result.stderr)
        self.assertEqual(generic.read_bytes(), b"Alacritty.desktop\n")

    def test_rejects_symlinks_into_the_checkout(self):
        self.config_home.mkdir(parents=True)
        source = self.checkout / "preference"
        source.write_bytes(b"Alacritty.desktop\n")
        (self.config_home / "xdg-terminals.list").symlink_to(source)
        result = self.setup()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must not point into the Luna checkout", result.stderr)
        self.assertEqual(source.read_bytes(), b"Alacritty.desktop\n")

    def test_unverified_selection_warns_without_claiming_success(self):
        for name, value in (("TEST_TERMINAL_ID", "other.desktop"), ("TEST_TERMINAL_STATUS", "1")):
            with self.subTest(failure=name):
                self.env[name] = value
                result = self.setup()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("selection could not be verified", result.stderr)
                self.assertNotIn("Default terminal set to Kitty", result.stdout)
                self.assertEqual((self.config_home / "xdg-terminals.list").read_bytes(),
                                 b"kitty.desktop\n")
                del self.env[name]


if __name__ == "__main__":
    unittest.main()
