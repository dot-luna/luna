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
        for name in ("scripts/setup/13-set-default-apps.sh", "scripts/setup/app-defaults.py", "default/apps.lua", "lib/common.sh", "lib/theme/json.lua"):
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
        for name in ("TEST_TERMINAL_ID", "TEST_TERMINAL_STATUS", "TEST_FILE_MANAGER_ID", "TEST_FILE_MANAGER_STATUS",
                     "TEST_MEDIA_FAILURE_TYPE", "TEST_FLAC_ID", "TEST_PNG_ID"):
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

    def add_mpv(self, mime_types="audio/mpeg;audio/flac;video/mp4;video/x-matroska;image/jpeg;application/json;x-scheme-handler/https;"):
        (self.bin / "mpv").write_text("#!/bin/sh\nexit 99\n")
        (self.bin / "mpv").chmod(0o755)
        self.add_desktop("mpv.desktop", "mpv --player-operation-mode=pseudo-gui -- %U", "AudioVideo;",
                         f"MimeType={mime_types}\n")
        (self.bin / "xdg-mime").write_text(f"#!{sys.executable}\n" + '''
import os, pathlib, sys
assert len(sys.argv) == 4 and sys.argv[1:3] == ["query", "default"]
with pathlib.Path(os.environ["HOME"], "media-queries").open("a") as output:
    output.write(sys.argv[3] + "\\n")
if sys.argv[3] == os.environ.get("TEST_MEDIA_FAILURE_TYPE"):
    print("other.desktop")
elif sys.argv[3] == "audio/flac":
    print(os.environ.get("TEST_FLAC_ID", "mpv.desktop"))
else:
    print("mpv.desktop")
''')
        (self.bin / "xdg-mime").chmod(0o755)

    def add_imv(self, mime_types="image/jpeg;image/png;image/webp;audio/mpeg;application/pdf;text/plain;"):
        (self.bin / "imv").write_text("#!/bin/sh\nexit 99\n")
        (self.bin / "imv").chmod(0o755)
        self.add_desktop("imv.desktop", "imv %F", "Graphics;",
                         f"NoDisplay=true\nMimeType={mime_types}\n")
        (self.bin / "xdg-mime").write_text(f"#!{sys.executable}\n" + '''
import os, pathlib, sys
assert len(sys.argv) == 4 and sys.argv[1:3] == ["query", "default"]
with pathlib.Path(os.environ["HOME"], "image-queries").open("a") as output:
    output.write(sys.argv[3] + "\\n")
print(os.environ.get("TEST_PNG_ID", "imv.desktop") if sys.argv[3] == "image/png" else "imv.desktop")
''')
        (self.bin / "xdg-mime").chmod(0o755)

    def setup(self, *arguments):
        return subprocess.run([str(self.bin / "bash"),
                               str(self.checkout / "scripts/setup/13-set-default-apps.sh"), *arguments],
                              env=self.env, cwd=self.root, input="", capture_output=True,
                              text=True, timeout=5)

    def test_new_preferences_use_default_xdg_path_and_ignore_extra_arguments(self):
        self.env.pop("XDG_CONFIG_HOME")
        self.env.pop("XDG_CURRENT_DESKTOP")
        result = self.setup("--help", "--unknown", "extra")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Default terminal set to kitty.desktop", result.stdout)
        self.assertNotIn("Back up", result.stderr)
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

    def test_mpv_selects_only_advertised_audio_video_types_and_preserves_other_defaults(self):
        self.add_mpv()
        self.config_home.mkdir(parents=True)
        generic = self.config_home / "mimeapps.list"
        generic.write_text("[Default Applications]\naudio/mpeg=old.desktop;\n"
                           "audio/unsupported=other.desktop;\nimage/jpeg=viewer.desktop;\n"
                           "application/json=editor.desktop;\nx-scheme-handler/https=browser.desktop;\n"
                           "[Added Associations]\naudio/mpeg=old.desktop;\n"
                           "[Removed Associations]\naudio/mpeg=mpv.desktop;blocked.desktop;\n")
        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Default audio player set to mpv.desktop", result.stdout)
        self.assertIn("Default video player set to mpv.desktop", result.stdout)
        self.assertNotIn("Default audio/mpeg set", result.stdout)
        media_types = {"audio/mpeg", "audio/flac", "video/mp4", "video/x-matroska"}
        self.assertEqual(set((self.home / "media-queries").read_text().splitlines()), media_types)
        for name in ("mimeapps.list", "hyprland-mimeapps.list"):
            content = (self.config_home / name).read_text()
            for mime_type in media_types:
                self.assertIn(f"{mime_type}=mpv.desktop;", content)
            self.assertNotIn("/*", content)
            for mime_type in ("audio/unsupported", "image/jpeg", "application/json", "x-scheme-handler/https"):
                self.assertNotIn(f"{mime_type}=mpv.desktop;", content)
        content = generic.read_text()
        self.assertIn("audio/mpeg=mpv.desktop;old.desktop;", content)
        self.assertIn("[Removed Associations]\naudio/mpeg=blocked.desktop;", content)
        self.assertIn("audio/unsupported=other.desktop;", content)
        self.assertIn("image/jpeg=viewer.desktop;", content)
        self.assertIn("application/json=editor.desktop;", content)
        self.assertIn("x-scheme-handler/https=browser.desktop;", content)
        before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in self.config_home.iterdir()}
        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, {path: (path.read_bytes(), path.stat().st_mtime_ns)
                                  for path in self.config_home.iterdir()})

    def test_missing_mpv_preserves_existing_media_defaults(self):
        self.config_home.mkdir(parents=True)
        mime = self.config_home / "mimeapps.list"
        original = b"[Default Applications]\naudio/mpeg=other.desktop;\nvideo/mp4=other.desktop;\n"
        mime.write_bytes(original)
        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("mpv.desktop is unavailable", result.stderr)
        self.assertEqual(mime.read_bytes(), original)
        self.assertFalse((self.config_home / "hyprland-mimeapps.list").exists())

    def test_media_defaults_skip_missing_or_invalid_support_metadata(self):
        self.add_mpv("image/jpeg;audio/*;video/bad=value;")
        self.manifest.write_text('return { ["audio/*"] = "mpv.desktop", ["video/*"] = "mpv.desktop" }\n')
        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("advertises no supported types", result.stderr)
        self.assertFalse(self.config_home.exists())

        self.add_desktop("mpv.desktop", "mpv %U", "AudioVideo;")
        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("advertises no supported types", result.stderr)
        self.assertFalse(self.config_home.exists())

    def test_exact_media_preferences_override_wildcards(self):
        self.add_mpv()
        self.add_desktop("music.desktop", "/bin/true %U", "Audio;", "MimeType=audio/flac;\n")
        self.env["TEST_FLAC_ID"] = "music.desktop"
        self.manifest.write_text('''return {
    ["audio/flac"] = "music.desktop",
    ["audio/*"] = "mpv.desktop",
    ["video/*"] = "mpv.desktop",
}
''')
        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Default audio/flac set to music.desktop", result.stdout)
        for name in ("mimeapps.list", "hyprland-mimeapps.list"):
            content = (self.config_home / name).read_text()
            self.assertIn("audio/flac=music.desktop;", content)
            self.assertNotIn("audio/flac=mpv.desktop;", content)
            self.assertIn("audio/mpeg=mpv.desktop;", content)

    def test_media_verification_failure_warns_once_and_keeps_saved_preferences(self):
        self.add_mpv()
        self.env["TEST_MEDIA_FAILURE_TYPE"] = "audio/mpeg"
        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Default audio player preferences saved, but could not verify 1 MIME defaults", result.stderr)
        self.assertIn("Check xdg-mime query default audio/mpeg", result.stderr)
        self.assertNotIn("Default audio player set to", result.stdout)
        self.assertIn("Default video player set to mpv.desktop", result.stdout)
        self.assertIn("audio/mpeg=mpv.desktop;", (self.config_home / "mimeapps.list").read_text())

    def test_unavailable_exact_media_choice_preserves_existing_preference(self):
        self.add_mpv()
        self.add_desktop("hidden.desktop", "/bin/true %U", "Audio;", "Hidden=true\nMimeType=audio/flac;\n")
        self.config_home.mkdir(parents=True)
        mime = self.config_home / "mimeapps.list"
        mime.write_text("[Default Applications]\naudio/flac=existing.desktop;\n")
        for desktop_id in ("missing.desktop", "hidden.desktop"):
            with self.subTest(desktop_id=desktop_id):
                self.manifest.write_text('return { ["audio/*"] = "mpv.desktop", '
                                         f'["audio/flac"] = "{desktop_id}" }}\n')
                result = self.setup()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"{desktop_id} is unavailable", result.stderr)
                self.assertIn("audio/flac=existing.desktop;", mime.read_text())
                self.assertNotIn("audio/flac=mpv.desktop;", mime.read_text())
                self.assertIn("audio/mpeg=mpv.desktop;", mime.read_text())

    def test_imv_uses_advertised_images_despite_nodisplay_and_preserves_other_defaults(self):
        self.add_imv()
        self.config_home.mkdir(parents=True)
        mime = self.config_home / "mimeapps.list"
        mime.write_text("[Default Applications]\nimage/png=old.desktop;\n"
                        "image/unsupported=other.desktop;\naudio/mpeg=player.desktop;\n"
                        "application/pdf=reader.desktop;\ntext/plain=editor.desktop;\n"
                        "[Added Associations]\nimage/png=old.desktop;\n"
                        "[Removed Associations]\nimage/png=imv.desktop;blocked.desktop;\n")

        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Default image viewer set to imv.desktop", result.stdout)
        images = {"image/jpeg", "image/png", "image/webp"}
        self.assertEqual(set((self.home / "image-queries").read_text().splitlines()), images)
        for name in ("mimeapps.list", "hyprland-mimeapps.list"):
            content = (self.config_home / name).read_text()
            for mime_type in images:
                self.assertIn(f"{mime_type}=imv.desktop;", content)
            self.assertNotIn("/*", content)
        content = mime.read_text()
        for preference in ("image/unsupported=other.desktop;", "audio/mpeg=player.desktop;",
                           "application/pdf=reader.desktop;", "text/plain=editor.desktop;"):
            self.assertIn(preference, content)
        self.assertIn("image/png=imv.desktop;old.desktop;", content)
        self.assertIn("[Removed Associations]\nimage/png=blocked.desktop;", content)

    def test_exact_image_choice_overrides_wildcard_and_unavailable_choice_preserves_it(self):
        self.add_imv()
        self.add_desktop("special.desktop", "/bin/true %U", "Graphics;", "MimeType=image/png;\n")
        self.add_desktop("hidden.desktop", "/bin/true %U", "Graphics;", "Hidden=true\nMimeType=image/png;\n")
        self.env["TEST_PNG_ID"] = "special.desktop"
        for desktop_id in ("special.desktop", "missing.desktop", "hidden.desktop"):
            with self.subTest(desktop_id=desktop_id):
                self.manifest.write_text('return { '
                                         f'["image/png"] = "{desktop_id}", ["image/*"] = "imv.desktop" }}\n')
                (self.home / "image-queries").unlink(missing_ok=True)
                result = self.setup()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                if desktop_id == "special.desktop":
                    self.assertIn("Default image/png set to special.desktop", result.stdout)
                else:
                    self.assertIn(f"{desktop_id} is unavailable", result.stderr)
                    self.assertNotIn("image/png", (self.home / "image-queries").read_text())
                for name in ("mimeapps.list", "hyprland-mimeapps.list"):
                    content = (self.config_home / name).read_text()
                    self.assertIn("image/png=special.desktop;", content)
                    self.assertNotIn("image/png=imv.desktop;", content)
                    self.assertIn("image/jpeg=imv.desktop;", content)

    def test_image_defaults_skip_missing_or_invalid_support_metadata_without_changes(self):
        self.add_imv()
        self.manifest.write_text('return { ["image/*"] = "imv.desktop" }\n')
        self.config_home.mkdir(parents=True)
        mime = self.config_home / "mimeapps.list"
        original = b"[Default Applications]\nimage/png=old.desktop;\napplication/pdf=reader.desktop;\n"
        mime.write_bytes(original)
        for metadata in ("MimeType=image/*;image/bad=value;audio/mpeg;application/pdf;\n", ""):
            with self.subTest(metadata=metadata):
                self.add_desktop("imv.desktop", "imv %F", "Graphics;", "NoDisplay=true\n" + metadata)
                result = self.setup()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("advertises no supported types", result.stderr)
                self.assertNotIn("Default image viewer set", result.stdout)
                self.assertEqual(mime.read_bytes(), original)
                self.assertFalse((self.config_home / "hyprland-mimeapps.list").exists())
                self.assertFalse((self.home / "image-queries").exists())

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
                       'return { ["application/*"] = "mpv.desktop" }',
                       'return { ["audio/m*"] = "mpv.desktop" }',
                       'return { ["*/*"] = "mpv.desktop" }',
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
    def test_real_mime_lookup_uses_imv_evince_and_zed_while_html_stays_in_browser(self):
        self.add_imv("image/jpeg;image/png;")
        for desktop_id, mime_types in (
                ("org.gnome.Evince.desktop", "application/pdf;"),
                ("dev.zed.Zed.desktop", "text/plain;application/json;"),
                ("zen.desktop", "text/html;application/xhtml+xml;")):
            self.add_desktop(desktop_id, "/bin/true %U", extra=f"MimeType={mime_types}\n")
        (self.bin / "xdg-mime").unlink()
        (self.bin / "xdg-mime").symlink_to(shutil.which("xdg-mime"))
        self.env.update(PATH=f"{self.bin}:/usr/bin:/bin", LC_ALL="C")
        # Use the real MIME inheritance database without exposing system applications.
        system_data = Path(self.env["XDG_DATA_DIRS"])
        system_data.mkdir()
        (system_data / "mime").symlink_to("/usr/share/mime", target_is_directory=True)
        self.config_home.mkdir(parents=True)
        (self.config_home / "mimeapps.list").write_text(
            "[Default Applications]\ntext/html=zen.desktop;\napplication/xhtml+xml=zen.desktop;\n"
            "text/plain=old.desktop;\nimage/png=old.desktop;\napplication/pdf=old.desktop;\n")

        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Default image viewer set to imv.desktop", result.stdout)
        for mime_type, desktop_id in (
                ("image/jpeg", "imv.desktop"), ("image/png", "imv.desktop"),
                ("application/pdf", "org.gnome.Evince.desktop"),
                ("text/plain", "dev.zed.Zed.desktop"), ("text/x-python", "dev.zed.Zed.desktop"),
                ("text/x-lua", "dev.zed.Zed.desktop"), ("text/x-shellscript", "dev.zed.Zed.desktop"),
                ("application/json", "dev.zed.Zed.desktop"),
                ("text/html", "zen.desktop"), ("application/xhtml+xml", "zen.desktop")):
            with self.subTest(mime_type=mime_type):
                query = subprocess.run([shutil.which("gio"), "mime", mime_type], env=self.env,
                                       capture_output=True, text=True, timeout=5)
                self.assertEqual(query.returncode, 0, query.stderr)
                self.assertIn(desktop_id, query.stdout.splitlines()[0])
                # Direct lookups do not use GIO's MIME inheritance fallback.
                direct = subprocess.run([str(self.bin / "xdg-mime"), "query", "default", mime_type],
                                        env=self.env, capture_output=True, text=True, timeout=5)
                self.assertEqual(direct.returncode, 0, direct.stderr)
                self.assertEqual(direct.stdout.strip(), desktop_id)

    @unittest.skipUnless(shutil.which("xdg-mime") and shutil.which("gio"), "xdg-mime and gio are required")
    def test_real_mime_lookup_uses_mpv_for_audio_and_video(self):
        self.add_mpv("audio/mpeg;video/mp4;")
        self.add_desktop("old.desktop", "/bin/true %U", "AudioVideo;", "MimeType=audio/mpeg;video/mp4;\n")
        (self.bin / "xdg-mime").unlink()
        (self.bin / "xdg-mime").symlink_to(shutil.which("xdg-mime"))
        self.config_home.mkdir(parents=True)
        self.env.update(PATH=f"{self.bin}:/usr/bin:/bin", XDG_CURRENT_DESKTOP="GNOME:Hyprland", LC_ALL="C")
        original = "[Default Applications]\naudio/mpeg=old.desktop;\nvideo/mp4=old.desktop;\n"
        (self.config_home / "mimeapps.list").write_text(original + "[Removed Associations]\n"
                                                      "audio/mpeg=mpv.desktop;\nvideo/mp4=mpv.desktop;\n")
        (self.config_home / "gnome-mimeapps.list").write_text(original)

        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Default audio player set to mpv.desktop", result.stdout)
        self.assertIn("Default video player set to mpv.desktop", result.stdout)
        for desktop in ("GNOME:Hyprland", "Hyprland", ""):
            for mime_type in ("audio/mpeg", "video/mp4"):
                with self.subTest(desktop=desktop, mime_type=mime_type):
                    query = subprocess.run([shutil.which("gio"), "mime", mime_type],
                                           env=dict(self.env, XDG_CURRENT_DESKTOP=desktop),
                                           capture_output=True, text=True, timeout=5)
                    self.assertEqual(query.returncode, 0, query.stderr)
                    self.assertIn("mpv.desktop", query.stdout.splitlines()[0])

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
