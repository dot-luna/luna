"""Check application config deployment with isolated homes and a fixture theme generator."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]


@unittest.skipUnless(Path("/usr/bin/lua").is_file(), "The generator requires /usr/bin/lua")
class SetupAppsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna apps '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.checkout = self.root / "checkout"
        for name in ("scripts/setup/apps.sh", "scripts/setup/kitty-include.py", "lib/common.sh"):
            destination = self.checkout / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, destination)
        # Keep Kitty deployment cases isolated from the other app installers.
        (self.checkout / "scripts/setup/starship.sh").write_text(
            '#!/usr/bin/env bash\nprintf "configured\\n" > "$HOME/.starship-setup-ran"\n')
        (self.checkout / "scripts/setup/zsh.sh").write_text(
            '#!/usr/bin/env bash\nprintf "configured\\n" > "$HOME/.zsh-setup-ran"\n')
        (self.checkout / "scripts/setup/zen.sh").write_text(
            '#!/usr/bin/env bash\nprintf "configured\\n" > "$HOME/.zen-setup-ran"\n')
        self.source = self.checkout / "apps/kitty"
        (self.source / "scripts").mkdir(parents=True)
        (self.source / "kitty.conf").write_text("# Static fixture\ninclude theme.conf\n")
        (self.source / "theme.conf").write_text("# Obsolete theme must not be copied\n")

        # Isolate deployment behavior from the generator's separately tested theme mapping.
        (self.source / "scripts/generate-theme.lua").write_text('''
assert(#arg == 0, "Setup arguments must not reach the generator")
if os.getenv("TEST_THEME_FAIL") == "1" then
    io.write("# Incomplete output\\n")
    io.stderr:write("Fixture generation failed\\n")
    os.exit(29)
end
io.write("# Generated fixture\\nbackground ", os.getenv("TEST_THEME_COLOR"), "\\n")
''')
        self.config_home = self.home / ".config"
        self.destination = self.config_home / "luna/kitty"
        self.env = dict(os.environ, HOME=str(self.home),
                        XDG_CONFIG_HOME=str(self.config_home), TEST_THEME_COLOR="#123456")
        for name in ("LUNA_CONFIG_DIR", "KITTY_CONFIG_DIRECTORY", "TEST_THEME_FAIL"):
            self.env.pop(name, None)

    def setup(self, *arguments, entry=None):
        script = entry or self.checkout / "scripts/setup/apps.sh"
        return subprocess.run(["bash", str(script), *arguments], env=self.env,
                              cwd=self.root, input="", capture_output=True, text=True, timeout=10)

    def assert_installed(self, result, destination=None):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        destination = destination or self.destination
        self.assertFalse(destination.is_symlink())
        for name in ("kitty.conf", "theme.conf"):
            self.assertTrue((destination / name).is_file(), str(destination / name))
            self.assertFalse((destination / name).is_symlink())
        self.assertEqual((destination / "kitty.conf").read_bytes(),
                         (self.source / "kitty.conf").read_bytes())
        self.assertEqual((destination / "theme.conf").read_text(),
                         "# Generated fixture\nbackground " + self.env["TEST_THEME_COLOR"] + "\n")

    def include_prefix(self, destination=None):
        destination = destination or self.destination
        path = str(destination / "kitty.conf").replace("$", "$$")
        return ("include " + path + "\n").encode()

    def test_default_kitty_deployment_copies_only_configuration(self):
        self.env.pop("XDG_CONFIG_HOME")
        self.assert_installed(self.setup())
        self.assertEqual({path.name for path in self.destination.iterdir()},
                         {"kitty.conf", "theme.conf"})
        self.assertEqual((self.config_home / "kitty/kitty.conf").read_bytes(), self.include_prefix())
        self.assertFalse((self.config_home / "luna/zsh").exists())
        self.assertFalse((self.config_home / "luna/starship").exists())
        self.assertEqual((self.home / ".starship-setup-ran").read_text(), "configured\n")
        self.assertEqual((self.home / ".zsh-setup-ran").read_text(), "configured\n")
        self.assertEqual((self.home / ".zen-setup-ran").read_text(), "configured\n")
        self.assertEqual(list(self.home.rglob("*.luna-backup*")), [])

    def test_required_zsh_child_failure_fails_app_setup(self):
        (self.checkout / "scripts/setup/zsh.sh").write_text("#!/usr/bin/env bash\nexit 23\n")
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.home / ".zen-setup-ran").exists())

    def test_required_zen_child_failure_fails_app_setup(self):
        (self.checkout / "scripts/setup/zen.sh").write_text("#!/usr/bin/env bash\nexit 23\n")
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.home / ".zsh-setup-ran").exists())

    def test_required_starship_child_failure_stops_before_zsh_setup(self):
        (self.checkout / "scripts/setup/starship.sh").write_text("#!/usr/bin/env bash\nexit 23\n")
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.home / ".zsh-setup-ran").exists())

    @unittest.skipUnless(shutil.which("zsh"), "Zsh is required")
    def test_installed_zsh_selects_starship_config_and_preserves_personal_file(self):
        for name in ("starship.sh", "zsh.sh", "zsh-config.py"):
            shutil.copy2(REPO / "scripts/setup" / name, self.checkout / "scripts/setup" / name)
        for name in ("starship", "zsh"):
            shutil.copytree(REPO / "apps" / name, self.checkout / "apps" / name)

        # Keep actual installation and shell wiring, replacing only external tools.
        fixture_bin = self.root / "bin"
        fixture_bin.mkdir()
        for name, body in {
            "mise": 'printf "# Optional mise fixture\\n"\n',
            "starship": 'printf "prompt_starship_precmd() { return 0; }\\n"\n',
        }.items():
            executable = fixture_bin / name
            executable.write_text("#!/bin/sh\n" + body)
            executable.chmod(0o755)
        self.env["PATH"] = str(fixture_bin) + os.pathsep + self.env["PATH"]
        for name in ("STARSHIP_CONFIG", "ZDOTDIR", "ANDROID_HOME", "PNPM_HOME"):
            self.env.pop(name, None)
        personal = self.root / "personal-starship.toml"
        personal.write_text("add_newline = false\n")
        self.config_home.mkdir()
        (self.config_home / "starship.toml").symlink_to(personal)

        self.assert_installed(self.setup())
        installed = self.config_home / "luna/starship/starship.toml"
        self.assertEqual(installed.read_bytes(), (REPO / "apps/starship/starship.toml").read_bytes())
        shell = subprocess.run(
            [shutil.which("zsh"), "-d", "-f", "-i", "-c",
             'source "$HOME/.zshrc"; print -r -- "$STARSHIP_CONFIG"'],
            env=self.env, cwd=self.root, input="", capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(shell.returncode, 0, shell.stdout + shell.stderr)
        self.assertEqual(shell.stdout.strip(), str(installed))
        self.assertTrue((self.config_home / "starship.toml").is_symlink())
        self.assertEqual(personal.read_text(), "add_newline = false\n")

    def test_xdg_config_home_controls_default_destination(self):
        config_home = self.root / "custom config"
        self.env["XDG_CONFIG_HOME"] = str(config_home)
        self.assert_installed(self.setup(), config_home / "luna/kitty")
        self.assertFalse(self.config_home.exists())
        self.assertEqual((config_home / "kitty/kitty.conf").read_bytes(),
                         self.include_prefix(config_home / "luna/kitty"))

    def test_luna_config_dir_overrides_xdg_destination(self):
        config_dir = self.root / "Luna configuration"
        self.env["LUNA_CONFIG_DIR"] = str(config_dir)
        self.assert_installed(self.setup(), config_dir / "kitty")
        self.assertEqual((self.config_home / "kitty/kitty.conf").read_bytes(),
                         self.include_prefix(config_dir / "kitty"))

    def test_empty_overrides_use_default_destination(self):
        self.env["LUNA_CONFIG_DIR"] = ""
        self.env["XDG_CONFIG_HOME"] = ""
        self.assert_installed(self.setup())

    def test_repeated_setup_refreshes_both_files_without_backups(self):
        self.assert_installed(self.setup())
        (self.source / "kitty.conf").write_text("# Updated static fixture\ninclude theme.conf\n")
        self.env["TEST_THEME_COLOR"] = "#abcdef"
        self.assert_installed(self.setup())
        self.assertEqual((self.config_home / "kitty/kitty.conf").read_bytes(), self.include_prefix())
        self.assertEqual(list(self.home.rglob("*.luna-backup*")), [])
        self.assertEqual((self.source / "theme.conf").read_text(),
                         "# Obsolete theme must not be copied\n")

    def test_symlink_entry_and_extra_arguments_use_the_checkout(self):
        entry = self.root / "install app configs"
        entry.symlink_to(self.checkout / "scripts/setup/apps.sh")
        result = self.setup("--help", "-h", "--force", "--unknown", "main", entry=entry)
        self.assert_installed(result)

    def test_include_is_prepended_without_changing_original_bytes(self):
        live = self.config_home / "kitty"
        live.mkdir(parents=True)
        config = live / "kitty.conf"
        original = b"font_size 12\r\n# Personal caf\xc3\xa9\r\n# No final newline"
        config.write_bytes(original)
        config.chmod(0o640)
        (live / "theme.conf").write_text("# Personal active theme\n")
        for _ in range(2):
            self.assert_installed(self.setup())
            self.assertEqual(config.read_bytes(), self.include_prefix() + original)
            self.assertEqual(config.stat().st_mode & 0o777, 0o640)
            self.assertEqual((live / "theme.conf").read_text(), "# Personal active theme\n")
        self.assertEqual({path.name for path in live.iterdir()}, {"kitty.conf", "theme.conf"})

    def test_equivalent_existing_include_anywhere_leaves_file_unchanged(self):
        live = self.config_home / "kitty"
        live.mkdir(parents=True)
        config = live / "kitty.conf"
        relative = os.path.relpath(self.destination / "kitty.conf", live)
        for path in (str(self.destination / "kitty.conf"), relative,
                     "~/.config/luna/kitty/kitty.conf", "$HOME/.config/luna/kitty/kitty.conf"):
            with self.subTest(path=path):
                original = ("font_size 17\r\n \tinclude\t " + path
                            + "  \r\n# Keep the include in this position").encode()
                config.write_bytes(original)
                config.chmod(0o640)
                before = config.stat()
                self.assert_installed(self.setup())
                self.assertEqual(config.read_bytes(), original)
                self.assertEqual(config.stat().st_mode & 0o777, 0o640)
                self.assertEqual(config.stat().st_mtime_ns, before.st_mtime_ns)

    def test_commented_include_does_not_prevent_active_include(self):
        live = self.config_home / "kitty"
        live.mkdir(parents=True)
        config = live / "kitty.conf"
        original = b"# " + self.include_prefix() + b"font_size 17\n"
        config.write_bytes(original)
        self.assert_installed(self.setup())
        self.assertEqual(config.read_bytes(), self.include_prefix() + original)

    def test_continued_existing_include_is_left_unchanged(self):
        live = self.config_home / "kitty"
        live.mkdir(parents=True)
        config = live / "kitty.conf"
        for newline in ("\n", "\r\n", "\r"):
            with self.subTest(newline=repr(newline)):
                original = ("font_size 17" + newline + "include " + str(self.destination)
                            + "/" + newline + " \t\\kitty.conf" + newline).encode()
                config.write_bytes(original)
                before = config.stat()
                self.assert_installed(self.setup())
                self.assertEqual(config.read_bytes(), original)
                self.assertEqual(config.stat().st_mtime_ns, before.st_mtime_ns)

    def test_continued_include_for_another_file_does_not_match_luna(self):
        live = self.config_home / "kitty"
        live.mkdir(parents=True)
        config = live / "kitty.conf"
        original = self.include_prefix() + b"\\.personal\nfont_size 17\n"
        config.write_bytes(original)
        self.assert_installed(self.setup())
        self.assertEqual(config.read_bytes(), self.include_prefix() + original)

    def test_existing_include_expands_builtin_kitty_os_before_environment(self):
        live = self.config_home / "kitty"
        live.mkdir(parents=True)
        config = live / "kitty.conf"
        config_dir = self.root / "linux/configs"
        self.env["LUNA_CONFIG_DIR"] = str(config_dir)
        original = ("font_size 17\ninclude " + str(self.root)
                    + "/$KITTY_OS/configs/kitty/kitty.conf\n").encode()
        for value in (None, "macos"):
            with self.subTest(KITTY_OS=value):
                if value is None:
                    self.env.pop("KITTY_OS", None)
                else:
                    self.env["KITTY_OS"] = value
                config.write_bytes(original)
                before = config.stat()
                self.assert_installed(self.setup(), config_dir / "kitty")
                self.assertEqual(config.read_bytes(), original)
                self.assertEqual(config.stat().st_mtime_ns, before.st_mtime_ns)

    def test_active_config_symlink_and_target_mode_are_preserved(self):
        live = self.config_home / "kitty"
        live.mkdir(parents=True)
        actual = self.root / "dotfiles/kitty.conf"
        actual.parent.mkdir()
        original = b"# Personal linked configuration\nfont_size 13"
        actual.write_bytes(original)
        actual.chmod(0o640)
        config = live / "kitty.conf"
        config.symlink_to(os.path.relpath(actual, live))
        link = config.readlink()
        for _ in range(2):
            self.assert_installed(self.setup())
            self.assertTrue(config.is_symlink())
            self.assertEqual(config.readlink(), link)
            self.assertEqual(actual.read_bytes(), self.include_prefix() + original)
            self.assertEqual(actual.stat().st_mode & 0o777, 0o640)

    def test_active_config_directory_symlink_is_preserved(self):
        actual = self.root / "dotfiles/kitty"
        actual.mkdir(parents=True)
        original = b"# Personal directory\n"
        config = actual / "kitty.conf"
        config.write_bytes(original)
        config.chmod(0o640)
        self.config_home.mkdir()
        live = self.config_home / "kitty"
        live.symlink_to(actual)
        self.assert_installed(self.setup())
        self.assertTrue(live.is_symlink())
        self.assertEqual(config.read_bytes(), self.include_prefix() + original)
        self.assertEqual(config.stat().st_mode & 0o777, 0o640)

    def test_custom_active_directory_and_literal_dollars_in_include_path(self):
        active = self.root / "custom active kitty"
        config_dir = self.root / "$HOME literal Luna configs"
        self.env["KITTY_CONFIG_DIRECTORY"] = str(active)
        self.env["LUNA_CONFIG_DIR"] = str(config_dir)
        for _ in range(2):
            self.assert_installed(self.setup(), config_dir / "kitty")
            self.assertEqual((active / "kitty.conf").read_bytes(),
                             self.include_prefix(config_dir / "kitty"))
        self.assertFalse((self.config_home / "kitty").exists())

    def test_real_generator_installs_selected_theme_and_personal_font(self):
        # Exercise setup and generation together while retaining disposable state.
        for name in ("kitty.conf", "scripts/generate-theme.lua"):
            shutil.copy2(REPO / "apps/kitty" / name, self.source / name)
        shutil.copytree(REPO / "lib/theme", self.checkout / "lib/theme")
        shutil.copy2(REPO / "lib/common.lua", self.checkout / "lib/common.lua")
        defaults = subprocess.run(
            ["/usr/bin/lua", "-E", "-", str(self.checkout)], env=self.env,
            cwd=self.root, capture_output=True, text=True, check=True, timeout=10,
            input='local root = arg[1]; print(dofile(root .. "/lib/theme/json.lua").encode('
                  'dofile(root .. "/lib/theme/defaults.lua")))',
        )
        theme = dict(json.loads(defaults.stdout), version=1, name="integration")
        theme["fonts"]["mono"] = "Selected Theme Mono"
        theme["colors"].update(background="#102030", foreground="#aabbcc",
                               accent="#abcdef", error="#dd2233")
        state = self.config_home / "luna"
        state.mkdir(parents=True)
        (state / "theme").write_text("integration\n")
        (state / "fonts.json").write_text(json.dumps({"mono": "Personal Integration Mono"}))
        live = self.config_home / "kitty"
        live.mkdir()
        sentinel = live / "kitty.conf"
        sentinel.write_text("# Keep the active Kitty configuration\n")
        config_dir = self.root / "generated configs"
        self.env["LUNA_CONFIG_DIR"] = str(config_dir)
        installed = config_dir / "kitty"

        # Changing the selected snapshot must refresh the installed theme on rerun.
        for background in ("#102030", "#405060"):
            with self.subTest(background=background):
                theme["colors"]["background"] = background
                (state / "theme.json").write_text(json.dumps(theme))
                result = self.setup()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual((installed / "kitty.conf").read_bytes(),
                                 (REPO / "apps/kitty/kitty.conf").read_bytes())
                for name in ("kitty.conf", "theme.conf"):
                    self.assertFalse((installed / name).is_symlink())
                options = dict(line.split(maxsplit=1)
                               for line in (installed / "theme.conf").read_text().splitlines()
                               if line.strip() and not line.startswith("#"))
                self.assertEqual(options["background"], background)
                self.assertEqual(options["foreground"], "#aabbcc")
                self.assertEqual(options["cursor"], "#abcdef")
                self.assertEqual(options["color1"], "#dd2233")
                self.assertEqual(options["font_family"], "Personal Integration Mono")
                self.assertEqual(sentinel.read_bytes(), self.include_prefix(installed)
                                 + b"# Keep the active Kitty configuration\n")
                self.assertEqual(set(live.iterdir()), {sentinel})
                self.assertEqual(json.loads((state / "theme.json").read_text()), theme)
                self.assertFalse((state / "kitty").exists())

    def test_failed_generation_preserves_previously_installed_files(self):
        self.assert_installed(self.setup())
        original = {path.name: path.read_bytes() for path in self.destination.iterdir()}
        active = self.config_home / "kitty/kitty.conf"
        original_active = active.read_bytes()
        (self.source / "kitty.conf").write_text("# New static config\n")
        self.env["TEST_THEME_FAIL"] = "1"
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual({path.name: path.read_bytes() for path in self.destination.iterdir()}, original)
        self.assertEqual(active.read_bytes(), original_active)
        self.assertEqual(list(self.home.rglob("*.luna-backup*")), [])

    def test_failed_first_generation_does_not_change_active_config(self):
        live = self.config_home / "kitty"
        live.mkdir(parents=True)
        config = live / "kitty.conf"
        original = b"# Keep existing settings\r\nfont_size 15"
        config.write_bytes(original)
        self.env["TEST_THEME_FAIL"] = "1"
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(config.read_bytes(), original)
        self.assertEqual(set(live.iterdir()), {config})

    def test_missing_static_config_fails_before_replacing_installed_files(self):
        self.assert_installed(self.setup())
        original = {path.name: path.read_bytes() for path in self.destination.iterdir()}
        (self.source / "kitty.conf").unlink()
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual({path.name: path.read_bytes() for path in self.destination.iterdir()}, original)

    def test_relative_luna_config_dir_is_rejected(self):
        self.env["LUNA_CONFIG_DIR"] = "relative configs"
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.root / "relative configs").exists())
        self.assertFalse(self.destination.exists())

    def test_relative_xdg_config_home_is_rejected(self):
        self.env["XDG_CONFIG_HOME"] = "relative configs"
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.root / "relative configs").exists())

    def test_relative_kitty_config_directory_is_rejected(self):
        self.env["KITTY_CONFIG_DIRECTORY"] = "relative kitty"
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.root / "relative kitty").exists())

    def test_config_dir_pointing_at_live_config_home_is_rejected(self):
        live = self.config_home / "kitty"
        live.mkdir(parents=True)
        personal = live / "kitty.conf"
        personal.write_text("# Keep active Kitty configuration\n")
        self.env["LUNA_CONFIG_DIR"] = str(self.config_home)
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(personal.read_text(), "# Keep active Kitty configuration\n")
        self.assertEqual(set(live.iterdir()), {personal})

    def test_destination_aliasing_checkout_apps_is_rejected(self):
        config_dir = self.root / "linked configs"
        config_dir.symlink_to(self.checkout / "apps")
        self.env["LUNA_CONFIG_DIR"] = str(config_dir)
        original = (self.source / "kitty.conf").read_bytes()
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.source / "kitty.conf").read_bytes(), original)
        self.assertTrue((self.source / "scripts/generate-theme.lua").is_file())

    def test_symlinked_kitty_destination_is_rejected(self):
        self.destination.parent.mkdir(parents=True)
        foreign = self.root / "foreign kitty"
        foreign.mkdir()
        personal = foreign / "kitty.conf"
        personal.write_text("# Personal configuration\n")
        self.destination.symlink_to(foreign)
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.destination.is_symlink())
        self.assertEqual(personal.read_text(), "# Personal configuration\n")
        self.assertEqual(set(foreign.iterdir()), {personal})

    def test_live_kitty_aliasing_destination_is_rejected(self):
        self.destination.mkdir(parents=True)
        personal = self.destination / "kitty.conf"
        personal.write_text("# Active configuration through an alias\n")
        live = self.config_home / "kitty"
        live.symlink_to(self.destination)
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(live.is_symlink())
        self.assertEqual(personal.read_text(), "# Active configuration through an alias\n")
        self.assertEqual(set(self.destination.iterdir()), {personal})

    def test_safe_parent_symlink_can_hold_installed_configuration(self):
        config_dir = self.root / "config alias"
        actual = self.root / "actual configs"
        actual.mkdir()
        config_dir.symlink_to(actual)
        self.env["LUNA_CONFIG_DIR"] = str(config_dir)
        self.assert_installed(self.setup(), actual / "kitty")
        self.assertTrue(config_dir.is_symlink())

    def test_config_file_symlinks_are_replaced_without_following_targets(self):
        self.destination.mkdir(parents=True)
        foreign = self.root / "foreign configs"
        foreign.mkdir()
        for name in ("kitty.conf", "theme.conf"):
            (foreign / name).write_text("# Personal " + name + "\n")
            (self.destination / name).symlink_to(foreign / name)
        self.assert_installed(self.setup())
        for name in ("kitty.conf", "theme.conf"):
            self.assertEqual((foreign / name).read_text(), "# Personal " + name + "\n")

    def test_directory_conflicts_fail_without_replacing_existing_files(self):
        self.destination.mkdir(parents=True)
        static = self.destination / "kitty.conf"
        static.write_text("# Keep existing configuration\n")
        theme = self.destination / "theme.conf"
        theme.mkdir()
        personal = theme / "personal"
        personal.write_text("Keep this directory\n")
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(static.read_text(), "# Keep existing configuration\n")
        self.assertEqual(personal.read_text(), "Keep this directory\n")


if __name__ == "__main__":
    unittest.main()
