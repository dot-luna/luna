"""Install and migrate Hyprland configuration inside temporary checkouts only."""

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from __tests__.scripts.setup.app_fixture import copy_app_setup


REPO = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("hypr_config", REPO / "scripts/setup/hypr-config.py")
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)
PERSONAL = b'\n-- Personal LG TV setting\nhl.monitor({ output = "LG TV", mode = "1920x1080@60" })\n'


class SetupHyprTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna hypr ' Ω ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.checkout = self.root / "checkout"
        self.config = self.home / ".config"
        self.destination = self.config / "luna/hypr"
        self.active = self.config / "hypr/hyprland.lua"
        copy_app_setup(self.checkout)
        source = self.checkout / "apps/hypr/config"
        for name in helper.MODULES:
            module = source / (name + ".lua")
            module.parent.mkdir(parents=True, exist_ok=True)
            content = "loads = (loads or 0) + 1\n" if name == "hyprland" else "-- static module\n"
            module.write_text(content)
        self.generator = source.parent / "build.lua"

        self.bin = self.root / "bin"
        self.bin.mkdir()
        for name in ("bash", "readlink", "dirname", "realpath", "mktemp", "cp", "rm", "git", "mkdir", "find"):
            (self.bin / name).symlink_to(shutil.which(name))
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(("LUNA_", "XDG_", "HYPRLAND_", "GIT_"))}
        self.env.update(HOME=str(self.home), XDG_CONFIG_HOME=str(self.config), PATH=str(self.bin),
                        TMPDIR=str(self.root), BASH_ENV="", NO_COLOR="1", GIT_CONFIG_NOSYSTEM="1",
                        GIT_CONFIG_GLOBAL="/dev/null", GIT_AUTHOR_NAME="Luna Test",
                        GIT_AUTHOR_EMAIL="test@example.invalid", GIT_COMMITTER_NAME="Luna Test",
                        GIT_COMMITTER_EMAIL="test@example.invalid")

    def setup(self, *arguments, ok=True, script=None):
        result = subprocess.run(
            [str(self.bin / "bash"), str(script or self.checkout / "scripts/setup/hypr.sh"), *arguments],
            cwd=self.root, env=self.env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return result

    def put_active(self, content):
        self.active.parent.mkdir(parents=True, exist_ok=True)
        self.active.write_bytes(content)

    def run_lua(self, path=None):
        result = subprocess.run(
            ["/usr/bin/lua", "-E", "-", str(path or self.active)], env=self.env, cwd=self.root,
            input='hl = { monitor = function() monitors = (monitors or 0) + 1 end }; '
                  'dofile(arg[1]); print(loads or 0, monitors or 0)\n',
            capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def git(self, checkout, *arguments):
        return subprocess.run([str(self.bin / "git"), "-C", str(checkout), *arguments],
                              env=self.env, capture_output=True, check=True).stdout

    def legacy_entry(self, checkout=None, history=False):
        checkout = checkout or self.checkout
        source = checkout / helper.LEGACY_PATH
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(helper.LEGACY_PREFIX + PERSONAL)
        if history:
            for name in ("bin/luna", "lib/common.sh", "packages/packages.lua"):
                target = checkout / name
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    target.write_text("-- Luna fixture\n")
            self.git(checkout, "init", "-q")
            self.git(checkout, "add", ".")
            self.git(checkout, "-c", "core.hooksPath=/dev/null", "commit", "-qm", "Legacy entry")
        self.active.parent.mkdir(parents=True, exist_ok=True)
        self.active.symlink_to(source)
        return source

    def test_fresh_setup_and_rerun_preserve_personal_content_and_ignore_extra_arguments(self):
        self.put_active(PERSONAL)
        self.active.chmod(0o640)
        result = self.setup("--help", "extra")
        self.assertNotIn("Back up", result.stderr)
        content = self.active.read_bytes()
        self.assertTrue(content.startswith(helper.START + b"\n"))
        self.assertTrue(content.endswith(PERSONAL))
        self.assertEqual(self.active.stat().st_mode & 0o777, 0o640)
        self.assertEqual(self.run_lua(), "1\t1")
        self.assertEqual({str(path.relative_to(self.destination)) for path in self.destination.rglob("*")
                          if path.is_file()},
                         {name + ".lua" for name in helper.MODULES} | {"generated/paths.lua"})
        self.assertEqual((self.destination / "input.lua").read_bytes(), b"-- static module\n")
        self.assertTrue((self.destination / "generated/paths.lua").is_file())
        before = self.active.stat().st_mtime_ns
        self.setup()
        self.assertEqual(self.active.read_bytes(), content)
        self.assertEqual(self.active.stat().st_mtime_ns, before)

    def test_missing_entry_and_empty_unset_xdg_defaults(self):
        for value in (None, ""):
            if value is None:
                self.env.pop("XDG_CONFIG_HOME", None)
            else:
                self.env["XDG_CONFIG_HOME"] = value
            self.setup()
            self.assertEqual(self.run_lua(), "1\t0")
            self.assertEqual(self.active.read_bytes().count(helper.START), 1)

    def test_include_updates_to_new_destination_with_quoted_backslash_path(self):
        self.put_active(PERSONAL)
        self.setup()
        self.destination = self.root / 'new "configs" \\ path/luna/hypr'
        self.env["LUNA_CONFIG_DIR"] = str(self.destination.parent)
        self.setup()
        content = self.active.read_bytes()
        self.assertIn(helper.lua_string(str(self.destination / "hyprland.lua")), content)
        self.assertEqual(content.count(helper.START), 1)
        self.assertTrue(content.endswith(PERSONAL))
        self.assertEqual(self.run_lua(), "1\t1")

    def test_personal_file_and_directory_symlinks_preserve_their_targets_and_modes(self):
        personal = self.root / "dotfiles/personal.lua"
        personal.parent.mkdir()
        personal.write_bytes(PERSONAL)
        personal.chmod(0o640)
        directory = self.root / "active configs"
        directory.mkdir()
        self.active.parent.parent.mkdir(parents=True)
        self.active.parent.symlink_to(directory)
        self.active.symlink_to(personal)
        self.setup()
        self.assertTrue(self.active.is_symlink())
        self.assertTrue(self.active.parent.is_symlink())
        self.assertTrue(personal.read_bytes().endswith(PERSONAL))
        self.assertEqual(personal.stat().st_mode & 0o777, 0o640)
        self.assertEqual(self.run_lua(), "1\t1")

    def test_manual_direct_include_is_not_duplicated_but_comments_and_strings_do_not_count(self):
        manual = b"dofile(" + helper.lua_string(str(self.destination / "hyprland.lua")) + b")"
        self.put_active(manual + b" -- already loaded\n" + PERSONAL)
        original = self.active.read_bytes()
        self.setup()
        self.assertEqual(self.active.read_bytes(), original)
        self.assertEqual(self.run_lua(), "1\t1")

        commented = b"--[=[\n" + manual + b"\n]=]\nlocal example = [==[\n" + manual + b"\n]==]\n"
        self.active.write_bytes(commented + PERSONAL)
        self.setup()
        self.assertTrue(self.active.read_bytes().startswith(helper.START))
        self.assertTrue(self.active.read_bytes().endswith(commented + PERSONAL))
        self.assertEqual(self.run_lua(), "1\t1")

        for content in (b"if false then\n" + manual + b"\nend\n",
                        b"dofile(" + helper.lua_string(str(self.checkout / "apps/hypr/hyprland.lua")) + b")\n",
                        b"dofile(" + helper.lua_string(str(self.checkout / "apps/hypr/config/hyprland.lua")) + b")\n"):
            self.active.write_bytes(content)
            self.setup(ok=False)
            self.assertEqual(self.active.read_bytes(), content)

    def test_bom_crlf_and_shebang_remain_at_the_start(self):
        original = helper.BOM + b"#!/usr/bin/lua\r\n" + PERSONAL.replace(b"\n", b"\r\n")
        self.put_active(original)
        self.setup()
        content = self.active.read_bytes()
        self.assertTrue(content.startswith(helper.BOM + b"#!/usr/bin/lua\r\n" + helper.START + b"\r\n"))
        self.assertTrue(content.endswith(PERSONAL.replace(b"\n", b"\r\n")))
        self.assertEqual(self.run_lua(), "1\t1")
        self.setup()
        self.assertEqual(content, self.active.read_bytes())

    def test_legacy_symlink_detaches_preserving_monitor_settings_root_and_source(self):
        source = self.legacy_entry()
        source.write_bytes(source.read_bytes() + b"assert(root == " + helper.lua_string(str(self.checkout)) + b")\n")
        original = source.read_bytes()
        self.setup()
        self.assertFalse(self.active.is_symlink())
        self.assertEqual(source.read_bytes(), original)
        self.assertIn(PERSONAL, self.active.read_bytes())
        self.assertNotIn(b"/default/hypr/bootstrap.lua", self.active.read_bytes())
        self.assertEqual(self.run_lua(), "1\t1")
        content = self.active.read_bytes()
        self.setup()
        self.assertEqual(content, self.active.read_bytes())

    def test_regular_legacy_copy_is_migrated_without_discarding_personal_tail(self):
        self.put_active(helper.LEGACY_PREFIX.replace(b"\n", b"\r\n") + PERSONAL)
        self.setup()
        self.assertTrue(self.active.read_bytes().endswith(PERSONAL))
        self.assertIn(helper.LEGACY_ROOT, self.active.read_bytes())
        self.assertEqual(self.run_lua(), "1\t1")

    def test_deleted_legacy_symlink_recovers_from_local_git_history_without_checkout(self):
        for foreign in (False, True):
            with self.subTest(foreign=foreign):
                self.active.unlink(missing_ok=True)
                checkout = self.root / "previous Luna checkout" if foreign else self.checkout
                source = self.legacy_entry(checkout, history=True)
                source.unlink()
                self.git(checkout, "add", "-u")
                self.git(checkout, "-c", "core.hooksPath=/dev/null", "commit", "-qm", "Remove legacy entry")
                status = self.git(checkout, "status", "--porcelain")
                self.setup()
                self.assertFalse(self.active.is_symlink())
                self.assertFalse(source.exists())
                self.assertTrue(self.active.read_bytes().endswith(PERSONAL))
                self.assertEqual(self.git(checkout, "status", "--porcelain"), status)
                self.assertEqual(self.run_lua(), "1\t1")

    def test_unrecoverable_or_unrecognized_legacy_config_fails_before_replacing_files(self):
        source = self.legacy_entry()
        source.unlink()
        self.setup(ok=False)
        self.assertTrue(self.active.is_symlink())
        self.assertFalse(self.destination.exists())
        source.write_bytes(helper.LEGACY_PREFIX.replace(b"local root =", b"local custom_root =") + PERSONAL)
        self.setup(ok=False)
        self.assertTrue(self.active.is_symlink())
        self.assertFalse(self.destination.exists())
        self.active.unlink()
        self.active.write_bytes(b'dofile("/somewhere/default/hypr/bootstrap.lua")("/somewhere")\n' + PERSONAL)
        self.assertIn("migrate", self.setup(ok=False).stderr)
        self.assertFalse(self.destination.exists())

    def test_legacy_conf_only_and_explicit_conf_are_preserved_without_shadowing(self):
        legacy = self.active.with_suffix(".conf")
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(b"monitor = , preferred, auto, 1\n")
        result = self.setup()
        self.assertIn("convert it to Lua", result.stderr)
        self.assertFalse(self.active.exists())
        self.assertTrue((self.destination / "hyprland.lua").exists())
        self.env["HYPRLAND_CONFIG"] = str(legacy)
        result = self.setup()
        self.assertIn("Convert it to Lua", result.stderr)
        self.assertEqual(legacy.read_bytes(), b"monitor = , preferred, auto, 1\n")
        self.assertFalse(self.active.exists())

    def test_custom_lua_and_symlinked_setup_entry_resolve_correctly(self):
        custom = self.root / "custom config/my.lua"
        custom.parent.mkdir()
        custom.write_bytes(PERSONAL)
        self.env["HYPRLAND_CONFIG"] = str(custom)
        script = self.root / "linked setup"
        script.symlink_to(self.checkout / "scripts/setup/hypr.sh")
        self.setup(script=script)
        self.assertEqual(self.run_lua(custom), "1\t1")
        self.assertFalse(self.active.exists())

    def test_generation_failure_keeps_all_installed_and_personal_bytes(self):
        self.put_active(PERSONAL)
        self.setup()
        paths = [self.active, *self.destination.rglob("*.lua")]
        before = {path: path.read_bytes() for path in paths}
        self.generator.write_text('return function(ctx) ctx.write("generated/paths.lua", "partial"); error("bad generation") end\n')
        self.setup(ok=False)
        self.assertEqual(before, {path: path.read_bytes() for path in paths})

    def test_incomplete_modules_preserve_installed_and_personal_content(self):
        self.put_active(PERSONAL)
        self.setup()
        paths = [self.active, *self.destination.rglob("*.lua")]
        before = {path: path.read_bytes() for path in paths}
        for name, contents in (("bindings/desktop.lua", (None, b"")), ("input.lua", (None, b""))):
            module = self.checkout / "apps/hypr/config" / name
            original = module.read_bytes()
            for content in contents:
                with self.subTest(module=name, content=content):
                    if content is None:
                        module.unlink()
                    else:
                        module.write_bytes(content)
                    self.setup(ok=False)
                    self.assertEqual(before, {path: path.read_bytes() for path in paths})
                    module.write_bytes(original)

    def test_relative_paths_repository_and_active_aliases_are_rejected(self):
        for name, value in (("XDG_CONFIG_HOME", "relative"), ("LUNA_CONFIG_DIR", "relative"),
                            ("HYPRLAND_CONFIG", "relative"), ("LUNA_CONFIG_DIR", str(self.checkout)),
                            ("LUNA_CONFIG_DIR", str(self.config))):
            with self.subTest(name=name, value=value):
                saved = self.env.copy()
                self.env[name] = value
                self.setup(ok=False)
                self.assertFalse(self.destination.exists())
                self.env = saved
        self.active.parent.parent.mkdir(parents=True)
        self.active.parent.symlink_to(self.checkout / "apps/hypr")
        self.setup(ok=False)
        self.assertFalse(self.destination.exists())

    def test_output_symlinks_conflicting_directories_and_active_source_aliases_are_safe(self):
        outside = self.root / "outside"
        outside.mkdir()
        self.destination.parent.mkdir(parents=True)
        self.destination.symlink_to(outside)
        self.setup(ok=False)
        self.assertEqual(list(outside.iterdir()), [])
        self.destination.unlink()
        self.destination.mkdir()
        for name in ("generated", "bindings"):
            with self.subTest(directory=name):
                (self.destination / name).symlink_to(outside)
                self.setup(ok=False)
                with self.assertRaisesRegex(ValueError, "not a symlink"):
                    helper.plan(self.checkout / "apps/hypr/config", self.destination, self.active)
                self.assertEqual(list(outside.iterdir()), [])
                (self.destination / name).unlink()
        (self.destination / "theme.lua").mkdir()
        self.setup(ok=False)
        self.assertFalse(self.active.exists())
        (self.destination / "theme.lua").rmdir()
        self.active.parent.mkdir(parents=True)
        self.active.symlink_to(self.checkout / "apps/hypr/config/hyprland.lua")
        self.setup(ok=False)
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_owned_file_symlink_is_replaced_without_touching_its_target(self):
        self.destination.mkdir(parents=True)
        personal = self.root / "do not change.lua"
        personal.write_bytes(PERSONAL)
        (self.destination / "hyprland.lua").symlink_to(personal)
        self.setup()
        self.assertFalse((self.destination / "hyprland.lua").is_symlink())
        self.assertEqual(personal.read_bytes(), PERSONAL)
        self.assertEqual(self.run_lua(), "1\t0")

    def test_personal_link_through_an_owned_symlink_is_rejected_before_publication(self):
        personal = self.root / "personal.lua"
        personal.write_bytes(PERSONAL)
        self.destination.mkdir(parents=True)
        installed = self.destination / "hyprland.lua"
        installed.symlink_to(personal)
        self.active.parent.mkdir(parents=True)
        self.active.symlink_to(installed)

        self.setup(ok=False)
        self.assertTrue(installed.is_symlink())
        self.assertEqual(self.active.read_bytes(), PERSONAL)
        self.assertEqual(personal.read_bytes(), PERSONAL)


if __name__ == "__main__":
    unittest.main()
