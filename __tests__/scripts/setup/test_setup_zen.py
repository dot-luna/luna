"""Connect Zen themes only inside temporary homes, without launching a browser."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]


class SetupZenTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna zen ' # Ω ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.config = self.home / ".config"
        self.destination = self.config / "luna/zen"
        self.generated = self.destination / "generated"
        self.checkout = self.root / "checkout"
        for name in ("scripts/setup/zen.sh", "scripts/setup/zen-profile.py", "lib/common.sh"):
            target = self.checkout / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, target)
        self.generator = self.checkout / "apps/zen/scripts/generate-theme.lua"
        self.generator.parent.mkdir(parents=True)
        self.generator.write_text('print([[{"chrome":"/* chrome */\\n","content":"/* content */\\n"}]])\n')

        # A closed PATH and fail-on-launch stub prevent host/browser interaction.
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for name in ("bash", "readlink", "dirname", "realpath"):
            (self.bin / name).symlink_to(shutil.which(name))
        (self.bin / "zen-browser").write_text('#!/bin/sh\nprintf launched > "$HOME/browser-launched"\nexit 99\n')
        (self.bin / "zen-browser").chmod(0o755)
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(("LUNA_", "ZEN_", "MOZ_", "XDG_"))}
        self.env.update(HOME=str(self.home), PATH=str(self.bin),
                        XDG_CONFIG_HOME=str(self.config), XDG_DATA_HOME=str(self.root / "data"),
                        XDG_CACHE_HOME=str(self.root / "cache"), XDG_STATE_HOME=str(self.root / "state"),
                        XDG_DATA_DIRS=str(self.root / "system-data"),
                        XDG_CONFIG_DIRS=str(self.root / "system-config"), BASH_ENV="", NO_COLOR="1")

    def setup(self, *arguments, ok=True):
        result = subprocess.run(
            [str(self.bin / "bash"), str(self.checkout / "scripts/setup/zen.sh"), *arguments],
            cwd=self.root, env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        self.assertFalse((self.home / "browser-launched").exists())
        return result

    def profile(self, root=None, name="default", registry=True):
        root = root or self.config / "zen"
        profile = root / name
        profile.mkdir(parents=True)
        if registry:
            (root / "profiles.ini").write_text(
                f"[Profile0]\nName=Default\nIsRelative=1\nPath={name}\nDefault=1\n")
        return profile

    def personal_files(self, profile):
        return [profile / "chrome/userChrome.css", profile / "chrome/userContent.css", profile / "user.js"]

    def assert_connected(self, profile):
        for path in self.personal_files(profile)[:2]:
            content = path.read_bytes()
            self.assertEqual(content.count(b"/* >>> Luna theme >>> */"), 1)
            self.assertIn((self.generated / path.name).as_uri().encode("ascii"), content)
        self.assertIn(b'user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);',
                      (profile / "user.js").read_bytes())

    def test_missing_profile_still_generates_without_creating_registry(self):
        result = self.setup("--help", "ignored")
        self.assertIn("Open Zen once", result.stderr)
        self.assertIn("without backups", result.stderr)
        self.assertEqual((self.generated / "userChrome.css").read_bytes(), b"/* chrome */\n")
        self.assertEqual((self.generated / "userContent.css").read_bytes(), b"/* content */\n")
        self.assertFalse((self.config / "zen").exists())
        self.assertFalse((self.home / ".zen").exists())

    def test_missing_browser_skips_profile_integration_but_installs_css(self):
        profile = self.profile()
        (self.bin / "zen-browser").unlink()
        result = self.setup()
        self.assertIn("Zen command is unavailable", result.stderr)
        self.assertTrue((self.generated / "userChrome.css").exists())
        self.assertFalse((profile / "chrome").exists())

        self.env["ZEN_PROFILE_DIR"] = str(profile)
        self.setup()
        self.assert_connected(profile)

    def test_xdg_registry_and_empty_or_unset_xdg_fallback(self):
        profile = self.profile()
        for value in (None, ""):
            with self.subTest(value=value):
                if value is None:
                    self.env.pop("XDG_CONFIG_HOME", None)
                else:
                    self.env["XDG_CONFIG_HOME"] = value
                self.setup()
                self.assert_connected(profile)

    def test_legacy_root_precedes_xdg_even_without_registry(self):
        xdg_profile = self.profile()
        legacy = self.home / ".zen"
        legacy.mkdir()
        self.assertIn("Open Zen once", self.setup().stderr)
        self.assertFalse((xdg_profile / "user.js").exists())
        legacy_profile = self.profile(root=legacy)
        self.setup()
        self.assert_connected(legacy_profile)
        self.assertFalse((xdg_profile / "user.js").exists())

    def test_install_default_precedes_legacy_default_and_ambiguity_needs_override(self):
        first = self.profile(name="first")
        second = self.profile(name="second", registry=False)
        registry = first.parent / "profiles.ini"
        with registry.open("a") as output:
            output.write("[Profile1]\nPath=second\nIsRelative=1\n[InstallABC]\nDefault=second\n")
        self.setup()
        self.assert_connected(second)
        self.assertFalse((first / "user.js").exists())
        with registry.open("a") as output:
            output.write("[InstallDEF]\nDefault=first\n")
        self.assertIn("Multiple profiles", self.setup().stderr)
        self.assertFalse((first / "user.js").exists())
        self.env["ZEN_PROFILE_DIR"] = str(first)
        self.setup()
        self.assert_connected(first)

    def test_single_profile_without_default_and_absolute_registry_path(self):
        profile = self.profile(root=self.root / "alternate", registry=False)
        registry = self.config / "zen/profiles.ini"
        registry.parent.mkdir(parents=True)
        registry.write_text(f"[Profile0]\nIsRelative=0\nPath={profile}\n")
        self.setup()
        self.assert_connected(profile)

    def test_mozilla_app_data_and_force_legacy_overrides(self):
        xdg_profile = self.profile()
        self.env["MOZ_LEGACY_HOME"] = "1"
        self.assertIn("Open Zen once", self.setup().stderr)
        self.assertFalse((xdg_profile / "user.js").exists())
        alternate = self.profile(root=self.root / "app data")
        self.env["MOZ_APP_DATA"] = str(alternate.parent)
        self.setup()
        self.assert_connected(alternate)
        self.assertFalse((xdg_profile / "user.js").exists())

    def test_personal_symlinks_bytes_mode_charset_and_effective_preference_survive_rerun(self):
        profile = self.profile()
        (profile / "chrome").mkdir()
        originals = [
            b'\xef\xbb\xbf@charset "UTF-8";\r\n@namespace url("custom");\r\n/* Personal */\r\n',
            b'@charset "ISO-8859-1";\r\n/* Personal: \xff */\r\nbody { color: red; }',
            b'\xef\xbb\xbf// Personal\r\nuser_pref("example", 1);\r\n',
        ]
        targets = []
        for index, (path, original) in enumerate(zip(self.personal_files(profile), originals)):
            target = self.root / f"personal-{index}"
            target.write_bytes(original)
            target.chmod(0o640)
            path.symlink_to(target)
            targets.append(target)
        self.setup()
        self.assert_connected(profile)
        self.assertTrue(targets[0].read_bytes().startswith(b'\xef\xbb\xbf@charset "UTF-8";\r\n/* >>>'))
        self.assertTrue(targets[1].read_bytes().startswith(b'@charset "ISO-8859-1";\r\n/* >>>'))
        for path, target, original in zip(self.personal_files(profile), targets, originals):
            self.assertTrue(path.is_symlink())
            self.assertEqual(target.stat().st_mode & 0o777, 0o640)
            self.assertIn(original.split(b"\r\n", 1)[1], target.read_bytes())
        before = [target.read_bytes() for target in targets]
        self.setup()
        self.assertEqual(before, [target.read_bytes() for target in targets])
        with targets[2].open("ab") as output:
            output.write(b'user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", false);\r\n')
        self.setup()
        prefs = targets[2].read_bytes()
        self.assertLess(prefs.index(b", false);"), prefs.index(b", true);"))
        self.assertEqual(prefs.count(b"// >>> Luna stylesheets >>>"), 1)

    def test_import_is_valid_before_rules_with_literal_uri_and_no_charset_newline(self):
        profile = self.profile()
        chrome = profile / "chrome"
        chrome.mkdir()
        original = b'@charset "UTF-8";@namespace url("custom");\n/* @import url("old"); */\n'
        (chrome / "userChrome.css").write_bytes(original)
        self.setup()
        contents = (chrome / "userChrome.css").read_bytes()
        self.assertTrue(contents.startswith(b'@charset "UTF-8";\n/* >>>'))
        self.assertLess(contents.index(b"@import"), contents.index(b"@namespace"))
        self.assertIn(b"%20", contents)
        self.assertIn(b"%27", contents)
        self.assertIn(b"%23", contents)
        self.assertIn(b"%CE%A9", contents)
        self.setup()
        self.assertEqual(contents, (chrome / "userChrome.css").read_bytes())

    def test_generation_errors_and_invalid_json_preserve_existing_files(self):
        profile = self.profile()
        self.setup()
        paths = [*self.personal_files(profile), *self.generated.iterdir()]
        before = {path: path.read_bytes() for path in paths}
        for program in ('error("bad theme")', 'print("broken json")', 'print([[{"chrome":"partial"}]])'):
            with self.subTest(program=program):
                self.generator.write_text(program)
                self.setup(ok=False)
                self.assertEqual(before, {path: path.read_bytes() for path in paths})

    def test_relative_destinations_and_profile_overlaps_fail_before_writes(self):
        for name, value in (("XDG_CONFIG_HOME", "relative"), ("LUNA_CONFIG_DIR", "relative"),
                            ("ZEN_PROFILE_DIR", "relative"), ("ZEN_PROFILE_DIR", str(self.checkout)),
                            ("ZEN_PROFILE_DIR", str(self.destination)), ("ZEN_PROFILE_DIR", str(self.home)),
                            ("LUNA_CONFIG_DIR", str(self.checkout))):
            with self.subTest(name=name, value=value):
                saved = self.env.copy()
                self.env[name] = value
                self.setup(ok=False)
                self.assertFalse(self.generated.exists())
                self.env = saved

    def test_output_directory_symlinks_are_rejected_but_owned_file_symlinks_are_replaced(self):
        outside = self.root / "outside"
        outside.mkdir()
        self.destination.parent.mkdir(parents=True)
        self.destination.symlink_to(outside)
        self.setup(ok=False)
        self.assertEqual(list(outside.iterdir()), [])
        self.destination.unlink()
        self.destination.mkdir()
        self.generated.symlink_to(outside)
        self.setup(ok=False)
        self.assertEqual(list(outside.iterdir()), [])
        self.generated.unlink()
        self.generated.mkdir()
        personal = outside / "personal"
        personal.write_text("keep")
        (self.generated / "userChrome.css").symlink_to(personal)
        self.setup()
        self.assertEqual(personal.read_text(), "keep")
        self.assertFalse((self.generated / "userChrome.css").is_symlink())

    def test_profile_aliases_into_owned_files_and_directory_errors_fail_before_writes(self):
        profile = self.profile()
        chrome = profile / "chrome"
        chrome.mkdir()
        target = self.checkout / "personal.css"
        target.write_text("preserve")
        (chrome / "userChrome.css").symlink_to(target)
        self.setup(ok=False)
        self.assertEqual(target.read_text(), "preserve")
        self.assertFalse(self.generated.exists())
        (chrome / "userChrome.css").unlink()
        (profile / "user.js").mkdir()
        self.setup(ok=False)
        self.assertFalse(self.generated.exists())
        self.assertFalse((chrome / "userChrome.css").exists())

    def test_invalid_registry_and_missing_explicit_profile_are_optional(self):
        registry = self.config / "zen/profiles.ini"
        registry.parent.mkdir(parents=True)
        for contents in ("[invalid", "[Profile0]\nPath=relative\nIsRelative=invalid\n",
                         "[Profile0]\nPath=/absolute\nIsRelative=1\n"):
            registry.write_text(contents)
            self.assertIn("Cannot read profiles.ini", self.setup().stderr)
        self.env["ZEN_PROFILE_DIR"] = str(self.root / "missing-profile")
        self.assertIn("does not exist", self.setup().stderr)
        self.assertFalse((self.root / "missing-profile").exists())

    def test_real_generator_rounding_change_replaces_css_preserving_personal_files(self):
        shutil.copy2(REPO / "apps/zen/scripts/generate-theme.lua", self.generator)
        shutil.copytree(REPO / "lib/theme", self.checkout / "lib/theme")
        profile = self.profile()
        (profile / "chrome").mkdir()
        personal = b"/* personal styles */\n#custom { color: red; }\n"
        (profile / "chrome/userChrome.css").write_bytes(personal)
        self.setup()
        for path in self.generated.iterdir():
            self.assertIn(b"border-radius: 0", path.read_bytes())
        imported = (profile / "chrome/userChrome.css").read_bytes()
        resolved = subprocess.run(
            ["/usr/bin/lua", "-E", "-", str(self.checkout)], env=self.env, cwd=self.root,
            input='local root=arg[1]; local theme=dofile(root .. "/lib/theme/resolved.lua")(root); '
                  'print(theme.encode(theme.resolve({hyprland={decoration={rounding=12}}}, "custom")))',
            capture_output=True, text=True, check=True)
        state = self.config / "luna"
        (state / "theme.json").write_text(resolved.stdout)
        (state / "theme").write_text("custom\n")
        self.setup()
        for path in self.generated.iterdir():
            self.assertNotIn(b"radius", path.read_bytes())
        self.assertEqual(imported, (profile / "chrome/userChrome.css").read_bytes())
        self.assertTrue(imported.endswith(personal))
        self.assert_connected(profile)


if __name__ == "__main__":
    unittest.main()
