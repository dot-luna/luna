"""Check default applications using isolated preferences and harmless commands."""

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
        self.manifest = self.checkout / "default/apps.lua"
        for name in ("scripts/setup/defaults.sh", "scripts/setup/app-defaults.py", "default/apps.lua", "lib/common.sh", "lib/theme/json.lua"):
            destination = self.checkout / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, destination)

        # A closed PATH prevents tests from launching an installed terminal.
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.desktop_entries = self.root / "data/applications"
        self.desktop_entries.mkdir(parents=True)
        for name in ("bash", "readlink", "dirname"):
            (self.bin / name).symlink_to(shutil.which(name))
        (self.bin / "kitty").write_text("#!/bin/sh\nexit 99\n")
        (self.bin / "kitty").chmod(0o755)
        self.add_desktop("kitty.desktop", "kitty", "TerminalEmulator;")
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
                        XDG_DATA_HOME=str(self.desktop_entries.parent),
                        XDG_DATA_DIRS=str(self.root / "system data"),
                        XDG_CONFIG_DIRS=str(self.root / "system config"),
                        XDG_CACHE_HOME=str(self.root / "cache"), GIO_USE_VFS="local",
                        BASH_ENV="", NO_COLOR="1")
        for name in ("TEST_TERMINAL_ID", "TEST_TERMINAL_STATUS", "TEST_FILE_MANAGER_ID", "TEST_FILE_MANAGER_STATUS"):
            self.env.pop(name, None)

    def add_desktop(self, desktop_id, command, categories="", extra=""):
        (self.desktop_entries / desktop_id).write_text(
            f"[Desktop Entry]\nType=Application\nName={desktop_id}\nExec={command}\n"
            f"Categories={categories}\n{extra}")

    def add_nautilus(self):
        (self.bin / "nautilus").write_text("#!/bin/sh\nexit 99\n")
        (self.bin / "nautilus").chmod(0o755)
        self.add_desktop("org.gnome.Nautilus.desktop", "nautilus %U", "FileManager;", "MimeType=inode/directory;\n")
        (self.bin / "xdg-mime").write_text(f"#!{sys.executable}\n" + '''
import os, pathlib, sys
assert len(sys.argv) == 4 and sys.argv[1:3] == ["query", "default"]
pathlib.Path(os.environ["HOME"], "file-manager-verified").touch()
print(os.environ.get("TEST_FILE_MANAGER_ID", "org.gnome.Nautilus.desktop"))
sys.exit(int(os.environ.get("TEST_FILE_MANAGER_STATUS", "0")))
''')
        (self.bin / "xdg-mime").chmod(0o755)

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
        self.assertIn("Default terminal set to kitty.desktop", result.stdout)
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
                    self.assertIn(f"{name + '.desktop' if name == 'kitty' else name} is unavailable", result.stderr)
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
                self.assertNotIn("Default terminal set to kitty.desktop", result.stdout)
                self.assertEqual((self.config_home / "xdg-terminals.list").read_bytes(),
                                 b"kitty.desktop\n")
                del self.env[name]

    def test_nautilus_default_is_independent_of_missing_kitty(self):
        self.add_nautilus()
        (self.bin / "kitty").unlink()
        self.env["XDG_CONFIG_HOME"] = ""
        result = self.setup("--help", "extra")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("kitty.desktop is unavailable", result.stderr)
        self.assertIn("Default inode/directory set to org.gnome.Nautilus.desktop", result.stdout)
        expected = b"[Default Applications]\ninode/directory=org.gnome.Nautilus.desktop;\n"
        self.assertEqual((self.config_home / "hyprland-mimeapps.list").read_bytes(), expected)
        self.assertEqual((self.config_home / "mimeapps.list").read_bytes(), expected +
                         b"\n[Added Associations]\ninode/directory=org.gnome.Nautilus.desktop;\n")
        self.assertFalse((self.config_home / "xdg-terminals.list").exists())
        self.assertTrue((self.home / "file-manager-verified").exists())

    def test_mime_preferences_preserve_other_associations_symlinks_and_desktops(self):
        self.add_nautilus()
        self.home.mkdir()
        config = self.root / "custom config"
        config.mkdir()
        self.env.update(XDG_CONFIG_HOME=str(config), XDG_CURRENT_DESKTOP="GNOME:Hyprland:GNOME")
        original = (b"# Preferences\r\n[Default Applications]\r\n"
                    b"text/plain=editor.desktop;\r\ninode/directory=org.kde.dolphin.desktop;\r\n"
                    b"[Added Associations]\r\ninode/directory=other.desktop;\r\n"
                    b"image/png=view.desktop;\r\n[Removed Associations]\r\n"
                    b"inode/directory=org.gnome.Nautilus.desktop;excluded.desktop;\r\n"
                    b"text/plain=blocked.desktop;\r\n# Notes: \xff")
        target = self.root / "dotfiles/mimeapps.list"
        target.parent.mkdir()
        target.write_bytes(original)
        target.chmod(0o640)
        (config / "mimeapps.list").symlink_to(target)
        gnome = config / "gnome-mimeapps.list"
        gnome.write_bytes(b"[Default Applications]\ninode/directory=org.kde.dolphin.desktop;\n"
                          b"text/html=browser.desktop;\n")
        unrelated = config / "kde-mimeapps.list"
        unrelated.write_bytes(b"[Default Applications]\ninode/directory=org.kde.dolphin.desktop;\n")

        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = original.replace(b"inode/directory=org.kde.dolphin.desktop;",
                                    b"inode/directory=org.gnome.Nautilus.desktop;")
        expected = expected.replace(b"inode/directory=other.desktop;",
                                    b"inode/directory=org.gnome.Nautilus.desktop;other.desktop;")
        expected = expected.replace(b"inode/directory=org.gnome.Nautilus.desktop;excluded.desktop;",
                                    b"inode/directory=excluded.desktop;")
        self.assertEqual(target.read_bytes(), expected)
        self.assertTrue((config / "mimeapps.list").is_symlink())
        self.assertEqual(target.stat().st_mode & 0o777, 0o640)
        self.assertEqual(gnome.read_bytes(), b"[Default Applications]\ninode/directory=org.gnome.Nautilus.desktop;\n"
                                           b"text/html=browser.desktop;\n")
        self.assertEqual(unrelated.read_bytes(), b"[Default Applications]\ninode/directory=org.kde.dolphin.desktop;\n")
        before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in config.iterdir()}
        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, {path: (path.read_bytes(), path.stat().st_mtime_ns)
                                  for path in config.iterdir()})

    def test_nautilus_fills_empty_defaults_and_missing_sections(self):
        self.add_nautilus()
        self.config_home.mkdir(parents=True)
        generic = self.config_home / "mimeapps.list"
        generic.write_bytes(b"[Default Applications]\ninode/directory=\n"
                            b"[Removed Associations]\ninode/directory=org.gnome.Nautilus.desktop;\n")
        desktop = self.config_home / "hyprland-mimeapps.list"
        desktop.write_bytes(b"# Personal note without a newline")
        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b"[Default Applications]\ninode/directory=org.gnome.Nautilus.desktop;\n", generic.read_bytes())
        self.assertIn(b"[Removed Associations]\n\n[Added Associations]", generic.read_bytes())
        self.assertEqual(desktop.read_bytes(), b"# Personal note without a newline\n\n"
                                             b"[Default Applications]\ninode/directory=org.gnome.Nautilus.desktop;\n")

    def test_invalid_mime_destinations_fail_before_mime_writes(self):
        self.add_nautilus()
        self.config_home.mkdir(parents=True)
        generic = self.config_home / "mimeapps.list"
        original = b"[Default Applications]\ninode/directory=org.kde.dolphin.desktop;\n"
        generic.write_bytes(original)
        (self.config_home / "hyprland-mimeapps.list").mkdir()
        result = self.setup()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Expected a mime preference file", result.stderr)
        self.assertEqual(generic.read_bytes(), original)

    def test_rejects_mime_symlinks_into_the_checkout(self):
        self.add_nautilus()
        self.config_home.mkdir(parents=True)
        source = self.checkout / "mime-preference"
        original = b"[Default Applications]\ninode/directory=org.kde.dolphin.desktop;\n"
        source.write_bytes(original)
        (self.config_home / "mimeapps.list").symlink_to(source)
        result = self.setup()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("MIME preferences must not point into the Luna checkout", result.stderr)
        self.assertEqual(source.read_bytes(), original)

    def test_nautilus_verification_failure_warns_and_keeps_terminal_default(self):
        self.add_nautilus()
        self.env["TEST_FILE_MANAGER_ID"] = "org.kde.dolphin.desktop"
        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Default inode/directory preference saved, but selection could not be verified", result.stderr)
        self.assertNotIn("Default inode/directory set to org.gnome.Nautilus.desktop", result.stdout)
        self.assertIn("Default terminal set to kitty.desktop", result.stdout)
        self.assertIn(b"inode/directory=org.gnome.Nautilus.desktop;", (self.config_home / "mimeapps.list").read_bytes())

    def test_manifest_controls_terminal_and_arbitrary_mime_defaults(self):
        self.add_nautilus()
        for command in ("kitty", "nautilus"):
            (self.bin / command).unlink()
        for command in ("custom-terminal", "custom-files"):
            (self.bin / command).write_text("#!/bin/sh\nexit 99\n")
            (self.bin / command).chmod(0o755)
        self.add_desktop("custom-terminal.desktop", "custom-terminal", "TerminalEmulator;")
        self.add_desktop("custom-files.desktop", "custom-files %U", "FileManager;")
        self.manifest.write_text('''return {
    terminal = "custom-terminal.desktop",
    ["inode/directory"] = "custom-files.desktop",
    ["application/json"] = "custom-files.desktop",
}
''')
        self.env.update(TEST_TERMINAL_ID="custom-terminal.desktop", TEST_FILE_MANAGER_ID="custom-files.desktop")
        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Default terminal set to custom-terminal.desktop", result.stdout)
        self.assertIn("Default application/json set to custom-files.desktop", result.stdout)
        for name in ("xdg-terminals.list", "hyprland-xdg-terminals.list"):
            self.assertEqual((self.config_home / name).read_bytes(), b"custom-terminal.desktop\n")
        for name in ("mimeapps.list", "hyprland-mimeapps.list"):
            content = (self.config_home / name).read_bytes()
            self.assertIn(b"inode/directory=custom-files.desktop;", content)
            self.assertIn(b"application/json=custom-files.desktop;", content)
            self.assertNotIn(b"Nautilus", content)

    def test_invalid_manifest_fails_before_any_preference_is_changed(self):
        self.add_nautilus()
        self.config_home.mkdir(parents=True)
        terminal = self.config_home / "xdg-terminals.list"
        terminal.write_bytes(b"other.desktop\n")
        mime = self.config_home / "mimeapps.list"
        mime.write_bytes(b"[Default Applications]\ninode/directory=other.desktop;\n")
        before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in self.config_home.iterdir()}
        for source in ("return false", 'return { terminal = "kitty.desktop", browser = "other.desktop" }',
                       'return { terminal = "kitty.desktop", ["inode/directory"] = 4 }',
                       'return { terminal = "$(touch INJECTED).desktop" }', "return {"):
            with self.subTest(manifest=source):
                self.manifest.write_text(source)
                result = self.setup()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Invalid default app manifest", result.stderr)
                self.assertEqual(before, {path: (path.read_bytes(), path.stat().st_mtime_ns)
                                          for path in self.config_home.iterdir()})
                self.assertFalse((self.home / "verified").exists())
                self.assertFalse((self.home / "file-manager-verified").exists())
                self.assertFalse((self.root / "INJECTED").exists())

    def test_empty_manifest_does_not_apply_unlisted_defaults(self):
        self.add_nautilus()
        self.manifest.write_text("return {}\n")
        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.config_home.exists())
        self.assertEqual(result.stdout, "")

    def test_user_hidden_desktop_entry_overrides_available_system_application(self):
        self.add_nautilus()
        system_apps = self.root / "system data/applications"
        system_apps.mkdir(parents=True)
        shutil.copy2(self.desktop_entries / "org.gnome.Nautilus.desktop", system_apps)
        self.add_desktop("org.gnome.Nautilus.desktop", "nautilus %U", extra="Hidden=true\n")
        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("org.gnome.Nautilus.desktop is unavailable", result.stderr)
        self.assertIn("Default terminal set to kitty.desktop", result.stdout)
        self.assertFalse((self.config_home / "mimeapps.list").exists())

    @unittest.skipUnless(shutil.which("xdg-mime") and shutil.which("gio"), "xdg-mime and gio are required")
    def test_real_mime_lookup_uses_nautilus_after_desktop_override_and_removal(self):
        self.add_nautilus()
        (self.bin / "xdg-mime").unlink()
        (self.bin / "xdg-mime").symlink_to(shutil.which("xdg-mime"))
        applications = self.home / ".local/share/applications"
        applications.mkdir(parents=True)
        for name, command in (("org.gnome.Nautilus.desktop", "nautilus"),
                              ("org.kde.dolphin.desktop", "/bin/true")):
            (applications / name).write_text(f"[Desktop Entry]\nType=Application\nName={name}\n"
                                              f"Exec={command} %U\nMimeType=inode/directory;\n")
        self.config_home.mkdir()
        (self.config_home / "mimeapps.list").write_text(
            "[Default Applications]\ninode/directory=org.kde.dolphin.desktop;\n"
            "[Removed Associations]\ninode/directory=org.gnome.Nautilus.desktop;\n")
        (self.config_home / "gnome-mimeapps.list").write_text(
            "[Default Applications]\ninode/directory=org.kde.dolphin.desktop;\n")
        self.env.update(PATH=f"{self.bin}:/usr/bin:/bin", XDG_CURRENT_DESKTOP="GNOME:Hyprland",
                        XDG_DATA_HOME=str(applications.parent), XDG_CONFIG_DIRS=str(self.root / "system config"),
                        XDG_DATA_DIRS=str(self.root / "system data"), XDG_CACHE_HOME=str(self.home / ".cache"),
                        GIO_USE_VFS="local", LC_ALL="C")

        before = subprocess.run([shutil.which("gio"), "mime", "inode/directory"], env=self.env,
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(before.returncode, 0, before.stderr)
        self.assertIn("Default application for", before.stdout)
        self.assertIn("org.kde.dolphin.desktop", before.stdout.splitlines()[0])
        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Default inode/directory set to org.gnome.Nautilus.desktop", result.stdout)
        for desktop in ("GNOME:Hyprland", "Hyprland", ""):
            with self.subTest(desktop=desktop):
                environment = dict(self.env, XDG_CURRENT_DESKTOP=desktop)
                query = subprocess.run([shutil.which("gio"), "mime", "inode/directory"], env=environment,
                                       capture_output=True, text=True, timeout=5)
                self.assertEqual(query.returncode, 0, query.stderr)
                self.assertIn("org.gnome.Nautilus.desktop", query.stdout.splitlines()[0])


if __name__ == "__main__":
    unittest.main()
