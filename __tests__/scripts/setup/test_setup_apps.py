"""Check application config deployment with isolated homes and a fixture theme generator."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from __tests__.scripts.setup.app_fixture import copy_app_setup


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
        copy_app_setup(self.checkout)
        # Keep Kitty cases focused while retaining the shared production runner.
        self.order = ["kitty"]
        self.write_order()
        self.app = self.checkout / "apps/kitty"
        self.source = self.app / "config"
        (self.source / "kitty.conf").write_text("# Static fixture\ninclude generated/theme.conf\n")
        (self.app / "theme.conf").write_text("# App metadata must not be copied\n")

        # Only the theme values are faked; staging and publishing use production code.
        (self.app / "build.lua").write_text('''return function(ctx)
    if os.getenv("TEST_THEME_FAIL") == "1" then
        ctx.write("generated/theme.conf", "# Incomplete output\\n")
        error("Fixture generation failed")
    end
    ctx.write("generated/theme.conf", "# Generated fixture\\nbackground "
        .. os.getenv("TEST_THEME_COLOR") .. "\\n")
end
''')
        self.config_home = self.home / ".config"
        self.destination = self.config_home / "luna/kitty"
        self.env = dict(os.environ, HOME=str(self.home),
                        XDG_CONFIG_HOME=str(self.config_home), TEST_THEME_COLOR="#123456")
        for name in ("LUNA_CONFIG_DIR", "KITTY_CONFIG_DIRECTORY", "TEST_THEME_FAIL", "LUNA_SETUP_APP"):
            self.env.pop(name, None)

    def setup(self, *arguments, entry=None):
        script = entry or self.checkout / "scripts/setup/10-setup-app-configs.lua"
        return subprocess.run(["/usr/bin/lua", "-E", str(script), *arguments], env=self.env,
                              cwd=self.root, input="", capture_output=True, text=True, timeout=10)

    def assert_installed(self, result, destination=None):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        destination = destination or self.destination
        self.assertFalse(destination.is_symlink())
        for name in ("kitty.conf", "generated/theme.conf"):
            self.assertTrue((destination / name).is_file(), str(destination / name))
            self.assertFalse((destination / name).is_symlink())
        self.assertEqual((destination / "kitty.conf").read_bytes(),
                         (self.source / "kitty.conf").read_bytes())
        self.assertEqual((destination / "generated/theme.conf").read_text(),
                         "# Generated fixture\nbackground " + self.env["TEST_THEME_COLOR"] + "\n")

    def installed_contents(self):
        return {str(path.relative_to(self.destination)): path.read_bytes()
                for path in self.destination.rglob("*") if path.is_file()}

    def include_prefix(self, destination=None):
        destination = destination or self.destination
        path = str(destination / "kitty.conf").replace("$", "$$")
        return ("include " + path + "\n").encode()

    def write_order(self):
        (self.checkout / "apps/order.lua").write_text(
            "return { " + ", ".join(json.dumps(name) for name in self.order) + " }\n")

    def add_app(self, name, builder=None, registered=True):
        app = self.checkout / "apps" / name
        (app / "config").mkdir(parents=True)
        (app / "config/main.conf").write_text("# " + name + " defaults\n")
        descriptor = 'return { config = "config"'
        if builder is not None:
            descriptor += ', builder = "build.lua"'
            (app / "build.lua").write_text(builder)
        (app / "app.lua").write_text(descriptor + " }\n")
        if registered:
            self.order.append(name)
            self.write_order()
        return app

    def test_installs_registered_app_without_builder_or_personal_connection(self):
        app = self.add_app("notes")
        (app / "config/nested").mkdir()
        (app / "config/nested/options.conf").write_text("# Nested settings\n")
        (app / "README.md").write_text("App documentation\n")
        (app / "unregistered.lua").write_text('error("Only app.lua is a descriptor")\n')
        self.assert_installed(self.setup())
        installed = self.destination.parent / "notes"
        self.assertEqual({str(path.relative_to(installed)) for path in installed.rglob("*") if path.is_file()},
                         {"main.conf", "nested/options.conf"})
        self.assertEqual((installed / "nested/options.conf").read_text(), "# Nested settings\n")
        self.assertFalse((self.config_home / "notes").exists())

    def test_builders_run_in_declared_order(self):
        # The explicit order takes precedence over app names and directory order.
        for name in ("zulu", "alpha"):
            self.add_app(name, '''return function(ctx)
    local log = assert(io.open(os.getenv("HOME") .. "/build-order", "a"))
    log:write(ctx.source:match("([^/]+)$"), "\\n")
    log:close()
end
''')
        self.assert_installed(self.setup())
        self.assertEqual((self.home / "build-order").read_text(), "zulu\nalpha\n")

    def test_unregistered_app_descriptor_is_not_loaded(self):
        app = self.add_app("notes", registered=False)
        (app / "app.lua").write_text('error("Unregistered app must not run")\n')
        self.assert_installed(self.setup())
        self.assertFalse((self.destination.parent / "notes").exists())

    def test_missing_registered_descriptor_fails_before_installing_any_app(self):
        self.order.append("missing")
        self.write_order()
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("missing", result.stderr)
        self.assertFalse(self.destination.exists())
        self.assertFalse((self.config_home / "kitty").exists())

    def test_invalid_order_fails_before_installing_any_app(self):
        for value in ('"kitty"', 'true', '{ kitty = true }',
                      '{ [1] = "kitty", [3] = "mpv" }',
                      '{ "kitty", "kitty" }', '{ "kitty", "../notes" }',
                      '{ "kitty", 12 }'):
            with self.subTest(order=value):
                (self.checkout / "apps/order.lua").write_text("return " + value + "\n")
                result = self.setup()
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertFalse(self.destination.exists())
                self.assertFalse((self.config_home / "kitty").exists())

    def test_empty_order_installs_nothing(self):
        self.order = []
        self.write_order()
        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.destination.parent.exists())
        self.assertFalse((self.config_home / "kitty").exists())

    def test_selected_app_must_be_registered(self):
        self.add_app("notes", registered=False)
        self.env["LUNA_SETUP_APP"] = "notes"
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("notes", result.stderr)
        self.assertFalse(self.destination.parent.exists())

    def test_selected_app_does_not_load_other_descriptors(self):
        app = self.add_app("notes")
        (app / "app.lua").write_text('error("Only Kitty was selected")\n')
        self.env["LUNA_SETUP_APP"] = "kitty"
        self.assert_installed(self.setup())
        self.assertFalse((self.destination.parent / "notes").exists())

    def test_selected_app_still_validates_complete_order(self):
        self.order.append("../notes")
        self.write_order()
        self.env["LUNA_SETUP_APP"] = "kitty"
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.destination.exists())

    def test_failed_app_build_stops_later_apps_without_publishing_partial_output(self):
        self.add_app("zulu")
        self.add_app("omega", '''return function(ctx)
    ctx.write("generated/options.conf", "# Partial output\\n")
    error("Required fixture build failed")
end
''')
        self.add_app("alpha")
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Required fixture build failed", result.stderr)
        self.assertTrue((self.destination.parent / "zulu/main.conf").is_file())
        self.assertTrue((self.destination / "kitty.conf").is_file())
        self.assertFalse((self.destination.parent / "omega").exists())
        self.assertFalse((self.destination.parent / "alpha").exists())

    def test_invalid_later_descriptor_fails_before_installing_any_app(self):
        app = self.add_app("zulu")
        (app / "app.lua").write_text('return { config = "../kitty/config" }\n')
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.destination.exists())
        self.assertFalse((self.config_home / "kitty").exists())

    def test_template_replacements_are_literal_and_use_final_install_paths(self):
        app = self.add_app("notes", '''return function(ctx)
    ctx.render("options.conf.in", "generated/options.conf", {
        paths = { installed = ctx.destination },
        literal = "%1 $HOME $(touch INJECTED) `touch INJECTED` {{untouched}}",
    })
end
''')
        (app / "options.conf.in").write_text("path={{paths.installed}}\ntext={{literal}}\n")
        self.assert_installed(self.setup())
        installed = self.destination.parent / "notes"
        self.assertEqual((installed / "generated/options.conf").read_text(),
                         f"path={installed}\ntext=%1 $HOME $(touch INJECTED) `touch INJECTED` {{{{untouched}}}}\n")
        self.assertFalse((self.root / "INJECTED").exists())
        self.assertFalse((installed / "options.conf.in").exists())

    def test_missing_template_value_preserves_previous_app_configuration(self):
        app = self.add_app("notes", '''return function(ctx)
    ctx.render("options.conf.in", "generated/options.conf", { value = "complete" })
end
''')
        template = app / "options.conf.in"
        template.write_text("option={{value}}\n")
        self.assert_installed(self.setup())
        installed = self.destination.parent / "notes"
        template.write_text("option={{missing}}\n")
        (app / "config/main.conf").write_text("# New version\n")
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Missing template value: missing", result.stderr)
        self.assertEqual((installed / "main.conf").read_text(), "# notes defaults\n")
        self.assertEqual((installed / "generated/options.conf").read_text(), "option=complete\n")

    def test_current_apps_config_step_never_runs_system_or_browser_extras(self):
        # Restore the production order and app descriptors for this smoke test.
        copy_app_setup(self.checkout)
        # Old installers and optional extras must never run from the config step.
        for name in ("hypr.sh", "kitty.sh", "mpv.sh", "starship.sh", "zsh.sh", "zen.sh", "zen-extensions.sh"):
            (self.checkout / "scripts/setup" / name).write_text(
                '#!/bin/sh\nprintf forbidden > "$HOME/extra-ran"\nexit 99\n')
        (self.checkout / "scripts/setup/zen_mods.py").write_text(
            'raise RuntimeError("Config setup must not import Mod installation")\n')
        (self.checkout / "scripts/setup/zen-extensions.py").write_text(
            'raise RuntimeError("Config setup must not import policy installation")\n')
        fixture_bin = self.root / "bin"
        fixture_bin.mkdir()
        for name in ("readlink", "mkdir"):
            (fixture_bin / name).symlink_to(shutil.which(name))
        for name in ("sudo", "curl", "wget", "zen", "zen-browser", "systemctl", "gsettings"):
            command = fixture_bin / name
            command.write_text('#!/bin/sh\nprintf forbidden > "$HOME/command-ran"\nexit 99\n')
            command.chmod(0o755)
        mise = fixture_bin / "mise"
        mise.write_text('#!/bin/sh\nprintf "# Fixture completion\\n"\n')
        mise.chmod(0o755)
        self.env = {"HOME": str(self.home), "PATH": str(fixture_bin),
                    "XDG_CONFIG_HOME": str(self.config_home), "NO_COLOR": "1"}
        profile = self.home / "zen-profile"
        profile.mkdir()
        (profile / "prefs.js").write_text("// Existing browser profile\n")
        self.env["ZEN_PROFILE_DIR"] = str(profile)
        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual({path.name for path in self.destination.parent.iterdir()},
                         {"hypr", "kitty", "mpv", "luna-wallpaper", "wallpaper.toml", "starship", "zen", "zsh"})
        self.assertTrue((profile / "chrome/userChrome.css").is_file())
        self.assertFalse((self.home / "extra-ran").exists())
        self.assertFalse((self.home / "command-ran").exists())

    def test_default_kitty_deployment_copies_only_configuration(self):
        self.env.pop("XDG_CONFIG_HOME")
        self.assert_installed(self.setup())
        self.assertEqual({path.name for path in self.destination.iterdir()},
                         {"kitty.conf", "generated"})
        self.assertEqual((self.config_home / "kitty/kitty.conf").read_bytes(), self.include_prefix())
        self.assertFalse((self.config_home / "luna/zsh").exists())
        self.assertFalse((self.config_home / "luna/starship").exists())
        self.assertEqual(list(self.home.rglob("*.luna-backup*")), [])

    @unittest.skipUnless(shutil.which("zsh"), "Zsh is required")
    def test_installed_zsh_selects_starship_config_and_preserves_personal_file(self):
        self.order.extend(("starship", "zsh"))
        self.write_order()

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
        self.assertEqual(installed.read_bytes(), (REPO / "apps/starship/config/starship.toml").read_bytes())
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
        (self.source / "kitty.conf").write_text("# Updated static fixture\ninclude generated/theme.conf\n")
        self.env["TEST_THEME_COLOR"] = "#abcdef"
        self.assert_installed(self.setup())
        self.assertEqual((self.config_home / "kitty/kitty.conf").read_bytes(), self.include_prefix())
        self.assertEqual(list(self.home.rglob("*.luna-backup*")), [])
        self.assertEqual((self.app / "theme.conf").read_text(),
                         "# App metadata must not be copied\n")

    def test_symlink_entry_and_extra_arguments_use_the_checkout(self):
        entry = self.root / "install app configs"
        entry.symlink_to(self.checkout / "scripts/setup/10-setup-app-configs.lua")
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
        shutil.copytree(REPO / "apps/kitty", self.app, dirs_exist_ok=True)
        defaults = subprocess.run(
            ["/usr/bin/lua", "-E", "-", str(self.checkout)], env=self.env,
            cwd=self.root, capture_output=True, text=True, check=True, timeout=10,
            input='local root = arg[1]; print(dofile(root .. "/lib/json.lua").encode('
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
                                 (REPO / "apps/kitty/config/kitty.conf").read_bytes())
                self.assertIn("remember_window_size no\n", (installed / "kitty.conf").read_text())
                for name in ("kitty.conf", "generated/theme.conf"):
                    self.assertFalse((installed / name).is_symlink())
                options = dict(line.split(maxsplit=1)
                               for line in (installed / "generated/theme.conf").read_text().splitlines()
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
        original = self.installed_contents()
        active = self.config_home / "kitty/kitty.conf"
        original_active = active.read_bytes()
        (self.source / "kitty.conf").write_text("# New static config\n")
        self.env["TEST_THEME_FAIL"] = "1"
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.installed_contents(), original)
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
        original = self.installed_contents()
        (self.source / "kitty.conf").unlink()
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.installed_contents(), original)

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
        self.assertTrue((self.app / "build.lua").is_file())

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
        for name in ("kitty.conf", "generated/theme.conf"):
            (foreign / name).parent.mkdir(parents=True, exist_ok=True)
            (self.destination / name).parent.mkdir(parents=True, exist_ok=True)
            (foreign / name).write_text("# Personal " + name + "\n")
            (self.destination / name).symlink_to(foreign / name)
        self.assert_installed(self.setup())
        for name in ("kitty.conf", "generated/theme.conf"):
            self.assertEqual((foreign / name).read_text(), "# Personal " + name + "\n")

    def test_directory_conflicts_fail_without_replacing_existing_files(self):
        self.destination.mkdir(parents=True)
        static = self.destination / "kitty.conf"
        static.write_text("# Keep existing configuration\n")
        theme = self.destination / "generated/theme.conf"
        theme.mkdir(parents=True)
        personal = theme / "personal"
        personal.write_text("Keep this directory\n")
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(static.read_text(), "# Keep existing configuration\n")
        self.assertEqual(personal.read_text(), "Keep this directory\n")

    def test_personal_link_through_owned_file_is_rejected_before_publication(self):
        personal = self.root / "personal.conf"
        personal.write_text("# Personal settings\n")
        self.destination.mkdir(parents=True)
        installed = self.destination / "kitty.conf"
        installed.symlink_to(personal)
        active = self.config_home / "kitty/kitty.conf"
        active.parent.mkdir()
        active.symlink_to(installed)
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(installed.is_symlink())
        self.assertEqual(personal.read_text(), "# Personal settings\n")

    def test_existing_include_is_not_duplicated_when_owned_symlink_is_replaced(self):
        personal = self.root / "prior.conf"
        personal.write_text("# Previous installed file\n")
        self.destination.mkdir(parents=True)
        (self.destination / "kitty.conf").symlink_to(personal)
        active = self.config_home / "kitty/kitty.conf"
        active.parent.mkdir()
        original = self.include_prefix() + b"# Personal settings\n"
        active.write_bytes(original)
        self.assert_installed(self.setup())
        self.assertEqual(active.read_bytes(), original)
        self.assertEqual(personal.read_text(), "# Previous installed file\n")

    def test_multiple_lua_connections_preserve_personal_settings_on_rerun(self):
        app = self.add_app("notes")
        (app / "config/main.conf").rename(app / "config/main.lua")
        (app / "config/main.lua").write_text("-- Lua defaults\n")
        (app / "app.lua").write_text('''return {
    config = "config",
    connections = {
        { type = "lua", source = "main.lua", target = "notes/first.lua" },
        { type = "lua", source = "main.lua", target = "notes/second.lua" },
    },
}
''')
        active = self.config_home / "notes/first.lua"
        active.parent.mkdir(parents=True)
        active.write_text("-- Personal settings\n")
        active.chmod(0o640)
        self.assert_installed(self.setup())
        original = active.read_bytes()
        self.assertTrue(original.endswith(b"-- Personal settings\n"))
        self.assertEqual(original.count(b"dofile("), 1)
        self.assertEqual(active.stat().st_mode & 0o777, 0o640)
        self.assert_installed(self.setup())
        self.assertEqual(active.read_bytes(), original)
        self.assertEqual(active.with_name("second.lua").read_bytes(), original.splitlines(keepends=True)[0])

    def test_lua_connection_rejects_alias_through_file_that_will_be_replaced(self):
        app = self.add_app("notes")
        (app / "app.lua").write_text('''return {
    config = "config",
    connections = { { type = "lua", source = "main.conf", target = "notes/main.lua" } },
}
''')
        installed = self.destination.parent / "notes/main.conf"
        installed.parent.mkdir(parents=True)
        personal = self.root / "personal.lua"
        personal.write_text("-- Personal settings\n")
        installed.symlink_to(personal)
        active = self.config_home / "notes/main.lua"
        active.parent.mkdir()
        active.symlink_to(installed)
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(installed.is_symlink())
        self.assertEqual(personal.read_text(), "-- Personal settings\n")


if __name__ == "__main__":
    unittest.main()
