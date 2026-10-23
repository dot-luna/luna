"""Exercise Zsh installation and startup preservation with disposable homes and mise."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]
STATIC_FILES = ("zshrc", "completion.zsh", "tools.zsh", "plugins.zsh")
RETIRED_FILES = ("paths.zsh", "development.zsh", "interactive.zsh", "mise.zsh",
                 "zoxide.zsh", "fzf.zsh", "starship.zsh", "env.zsh", "mise-completion.zsh")


class SetupZshTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna zsh '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.checkout = self.root / "checkout"
        for name in ("scripts/setup/zsh.sh", "scripts/setup/zsh-config.py", "lib/common.sh"):
            destination = self.checkout / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, destination)
        shutil.copytree(REPO / "apps/zsh", self.checkout / "apps/zsh")

        # A restricted PATH prevents accidentally running the developer's mise.
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for name in ("bash", "readlink", "realpath", "dirname", "mkdir", "mktemp",
                     "cp", "mv", "rm", "rmdir", "cat", "chmod", "grep"):
            (self.bin / name).symlink_to(shutil.which(name))
        self.mise = self.bin / "mise"
        self.mise.write_text('''#!/usr/bin/python3
import json
import os
import sys

arguments = sys.argv[1:]
with open(os.environ["MISE_TEST_LOG"], "a") as log:
    log.write(json.dumps(arguments) + "\\n")
if arguments[:2] == ["--cd", os.environ["HOME"]]:
    action, shell = arguments[2:]
elif arguments == ["activate", "zsh"]:
    action, shell = arguments
else:
    sys.exit(8)
if shell != "zsh":
    sys.exit(9)
if os.environ.get("MISE_TEST_FAIL") == action:
    print("INCOMPLETE_GENERATED_OUTPUT")
    sys.exit(12)
if action == "activate":
    print("export LUNA_MISE_TEST_ACTIVE=zsh")
    print("_mise_hook() { return 0; }")
elif action == "completion":
    print("export LUNA_MISE_TEST_COMPLETION=ready")
    print("_fake_mise() { return 0; }")
    print("compdef _fake_mise mise")
else:
    sys.exit(10)
''')
        self.mise.chmod(0o755)
        self.log = self.root / "mise.log"
        self.config_home = self.home / ".config"
        self.destination = self.config_home / "luna/zsh"
        self.env = dict(os.environ, HOME=str(self.home), PATH=str(self.bin),
                        XDG_CONFIG_HOME=str(self.config_home), TERM="xterm",
                        XDG_CACHE_HOME=str(self.home / ".cache"),
                        XDG_DATA_HOME=str(self.home / ".local/share"),
                        XDG_STATE_HOME=str(self.home / ".local/state"),
                        MISE_TEST_LOG=str(self.log))
        for name in ("ZDOTDIR", "LUNA_CONFIG_DIR", "LUNA_INSTALL_DIR", "MISE_TEST_FAIL",
                     "LUNA_MISE_TEST_ACTIVE", "LUNA_MISE_TEST_COMPLETION", "BASH_ENV", "ENV",
                     "ANDROID_HOME", "PNPM_HOME", "HISTFILE", "HISTSIZE", "SAVEHIST"):
            self.env.pop(name, None)

    def setup(self, *arguments, entry=None):
        script = entry or self.checkout / "scripts/setup/zsh.sh"
        return subprocess.run([shutil.which("bash"), str(script), *arguments], env=self.env,
                              cwd=self.root, input="", capture_output=True, text=True, timeout=10)

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def assert_installed(self, result, destination=None):
        self.assert_success(result)
        destination = destination or self.destination
        for name in STATIC_FILES:
            self.assertEqual((destination / name).read_bytes(),
                             (self.checkout / "apps/zsh" / name).read_bytes())
            self.assertFalse((destination / name).is_symlink())
        self.assertTrue((destination / "generated/env.zsh").is_file())
        for name in RETIRED_FILES:
            self.assertFalse((destination / name).exists())
            self.assertFalse((destination / name).is_symlink())

    def generation_calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def source_shell(self, overrides=None, startup=None, repeat=False, interactive=True):
        if not shutil.which("zsh"):
            self.skipTest("Zsh is required to exercise installed startup files")
        environment = dict(self.env)
        for name in ("LUNA_CONFIG_DIR", "LUNA_INSTALL_DIR"):
            environment.pop(name, None)
        environment.update(overrides or {})
        environment["LUNA_TEST_STARTUP"] = str(startup or self.home / ".zshrc")
        command = '''source "$LUNA_TEST_STARTUP"
/usr/bin/python3 -c 'import json, os; print(json.dumps(dict(os.environ)))'
'''
        if repeat:
            command = 'source "$LUNA_TEST_STARTUP"\n' + command
        arguments = [shutil.which("zsh"), "-d", "-f"]
        if interactive:
            arguments.append("-i")
        result = subprocess.run([*arguments, "-c", command],
                                env=environment, cwd=self.root, input="", capture_output=True,
                                text=True, timeout=10)
        self.assert_success(result)
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def test_default_install_caches_completion_and_exports_luna_paths(self):
        self.env["LUNA_INSTALL_DIR"] = str(self.root / "stale checkout")
        self.assert_installed(self.setup())
        calls = self.generation_calls()
        self.assertEqual(calls, [["--cd", str(self.home), "completion", "zsh"]])
        self.assertIn("LUNA_MISE_TEST_COMPLETION", (self.destination / "generated/mise-completion.zsh").read_text())
        self.assertEqual({path.name for path in self.destination.iterdir()},
                         {*STATIC_FILES, "generated"})
        environment = self.source_shell(repeat=True)
        self.assertEqual(environment["LUNA_INSTALL_DIR"], str(self.checkout))
        self.assertEqual(environment["LUNA_CONFIG_DIR"], str(self.destination.parent))
        self.assertEqual(environment["LUNA_MISE_TEST_ACTIVE"], "zsh")
        self.assertEqual(environment["LUNA_MISE_TEST_COMPLETION"], "ready")
        self.assertNotIn("ANDROID_HOME", environment)
        self.assertEqual(environment["PNPM_HOME"], str(self.home / ".local/share/pnpm"))
        self.assertEqual(self.generation_calls(), calls + [["activate", "zsh"]])
        self.assertEqual(list(self.home.rglob("*.luna-backup*")), [])

    def test_custom_directory_and_shell_metacharacters_are_literal(self):
        config_dir = self.root / "configs ' $HOME $(touch INJECTED) `touch INJECTED`"
        self.env["LUNA_CONFIG_DIR"] = str(config_dir)
        self.assert_installed(self.setup(), config_dir / "zsh")
        environment = self.source_shell()
        self.assertEqual(environment["LUNA_CONFIG_DIR"], str(config_dir))
        self.assertEqual(environment["LUNA_INSTALL_DIR"], str(self.checkout))
        self.assertFalse((self.root / "INJECTED").exists())

    def test_environment_preserves_nonempty_overrides_and_defaults_empty_values(self):
        self.assert_installed(self.setup())
        overrides = {"LUNA_CONFIG_DIR": str(self.root / "other config"),
                     "LUNA_INSTALL_DIR": str(self.root / "other checkout")}
        environment = self.source_shell(overrides)
        for name, value in overrides.items():
            self.assertEqual(environment[name], value)
        environment = self.source_shell({name: "" for name in overrides})
        self.assertEqual(environment["LUNA_CONFIG_DIR"], str(self.destination.parent))
        self.assertEqual(environment["LUNA_INSTALL_DIR"], str(self.checkout))

    def test_prepends_source_preserving_bytes_permissions_and_rerun(self):
        config = self.home / ".zshrc"
        original = b"# Personal caf\xc3\xa9\r\nexport PERSONAL_SETTING=kept\r\n# No final newline"
        config.write_bytes(original)
        config.chmod(0o640)
        self.assert_installed(self.setup())
        installed = config.read_bytes()
        prefix = installed[:-len(original)]
        self.assertTrue(installed.endswith(original))
        self.assertIn(b"source ", prefix)
        self.assertEqual(prefix.count(b"\n"), 1)
        self.assertEqual(config.stat().st_mode & 0o777, 0o640)
        previous = config.stat()
        self.assert_installed(self.setup())
        self.assertEqual(config.read_bytes(), installed)
        self.assertEqual(config.stat().st_mtime_ns, previous.st_mtime_ns)

    def test_personal_settings_execute_after_luna_defaults(self):
        config = self.home / ".zshrc"
        config.write_text('''export LUNA_TEST_DEFAULT_HISTORY="$HISTFILE:$HISTSIZE:$SAVEHIST"
export LUNA_CONFIG_DIR="$HOME/personal"
export ANDROID_HOME="$HOME/personal SDK"
export PNPM_HOME="$HOME/personal pnpm"
export HISTFILE="$HOME/personal history"
export HISTSIZE=9000 SAVEHIST=8000
bindkey -v
export LUNA_TEST_KEYMAP="$(bindkey -lL main)"
''')
        self.assert_installed(self.setup())
        environment = self.source_shell()
        self.assertEqual(environment["LUNA_CONFIG_DIR"], str(self.home / "personal"))
        self.assertEqual(environment["LUNA_TEST_DEFAULT_HISTORY"],
                         f"{self.home}/.histfile:1000:1000")
        self.assertEqual(environment["ANDROID_HOME"], str(self.home / "personal SDK"))
        self.assertEqual(environment["PNPM_HOME"], str(self.home / "personal pnpm"))
        self.assertEqual(environment["HISTFILE"], str(self.home / "personal history"))
        self.assertEqual(environment["HISTSIZE"], "9000")
        self.assertEqual(environment["SAVEHIST"], "8000")
        self.assertEqual(environment["LUNA_TEST_KEYMAP"], "bindkey -A viins main")

    def test_existing_source_anywhere_is_preserved_but_commented_source_is_not_active(self):
        self.assert_installed(self.setup())
        config = self.home / ".zshrc"
        prefix = config.read_bytes()
        original = b"# Personal header\n" + prefix + b"# Personal footer"
        config.write_bytes(original)
        self.assert_installed(self.setup())
        self.assertEqual(config.read_bytes(), original)
        commented = b"# " + prefix + b"# Personal footer"
        config.write_bytes(commented)
        self.assert_installed(self.setup())
        self.assertEqual(config.read_bytes(), prefix + commented)

    def test_zdotdir_file_symlink_and_target_mode_are_preserved(self):
        active = self.root / "custom startup"
        active.mkdir()
        self.env["ZDOTDIR"] = str(active)
        target = self.root / "personal.zshrc"
        original = b"# Linked personal config\nexport PERSONAL_SETTING=preserved\n"
        target.write_bytes(original)
        target.chmod(0o600)
        config = active / ".zshrc"
        config.symlink_to(os.path.relpath(target, active))
        link = config.readlink()
        self.assert_installed(self.setup())
        installed = target.read_bytes()
        self.assert_installed(self.setup())
        self.assertTrue(config.is_symlink())
        self.assertEqual(config.readlink(), link)
        self.assertEqual(target.read_bytes(), installed)
        self.assertTrue(installed.endswith(original))
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertFalse((self.home / ".zshrc").exists())
        self.assertEqual(self.source_shell(startup=config)["PERSONAL_SETTING"], "preserved")

    def test_zdotdir_directory_symlink_is_preserved(self):
        target = self.root / "dotfiles"
        target.mkdir()
        config = target / ".zshrc"
        original = b"# Personal directory\n"
        config.write_bytes(original)
        alias = self.root / "startup alias"
        alias.symlink_to(target)
        self.env["ZDOTDIR"] = str(alias)
        self.assert_installed(self.setup())
        self.assertTrue(alias.is_symlink())
        self.assertTrue(config.read_bytes().endswith(original))

    def test_symlink_entry_uses_real_checkout_and_ignores_extra_arguments(self):
        entry = self.root / "install zsh"
        entry.symlink_to(self.checkout / "scripts/setup/zsh.sh")
        self.assert_installed(self.setup("--help", "-h", "--force", "--unknown", entry=entry))
        self.assertEqual(self.source_shell()["LUNA_INSTALL_DIR"], str(self.checkout))

    def test_missing_mise_warns_but_core_config_installs_and_sources(self):
        self.mise.unlink()
        result = self.setup()
        self.assert_installed(result)
        self.assertIn("[WARN]", result.stderr)
        self.assertIn("mise", result.stderr.lower())
        self.assertFalse(self.log.exists())
        self.assertEqual(self.source_shell()["LUNA_CONFIG_DIR"], str(self.destination.parent))

    def test_failed_optional_generator_preserves_previous_complete_output(self):
        self.assert_installed(self.setup())
        completion = self.destination / "generated/mise-completion.zsh"
        generated = completion.read_bytes()
        self.env["MISE_TEST_FAIL"] = "completion"
        result = self.setup()
        self.assert_installed(result)
        self.assertIn("[WARN]", result.stderr)
        self.assertEqual(completion.read_bytes(), generated)
        environment = self.source_shell()
        self.assertEqual(environment["LUNA_MISE_TEST_ACTIVE"], "zsh")
        self.assertEqual(environment["LUNA_MISE_TEST_COMPLETION"], "ready")

    def test_failed_first_generation_does_not_install_partial_script(self):
        self.env["MISE_TEST_FAIL"] = "completion"
        result = self.setup()
        self.assert_installed(result)
        self.assertIn("[WARN]", result.stderr)
        self.assertFalse((self.destination / "generated/mise-completion.zsh").exists())
        self.assertEqual(self.source_shell()["LUNA_MISE_TEST_ACTIVE"], "zsh")

    def test_noninteractive_source_does_not_activate_mise(self):
        self.assert_installed(self.setup())
        calls = self.generation_calls()
        environment = self.source_shell(interactive=False)
        self.assertNotIn("LUNA_MISE_TEST_ACTIVE", environment)
        self.assertEqual(environment["LUNA_CONFIG_DIR"], str(self.destination.parent))
        self.assertEqual(self.generation_calls(), calls)

    def test_missing_static_source_fails_before_changing_existing_files(self):
        self.assert_installed(self.setup())
        previous = {name: (self.destination / name).read_bytes()
                    for name in (*STATIC_FILES, "generated/env.zsh")}
        retired = self.destination / "paths.zsh"
        retired.write_text("# Still needed until installation succeeds\n")
        config = self.home / ".zshrc"
        startup = config.read_bytes()
        (self.checkout / "apps/zsh/tools.zsh").unlink()
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        for name, content in previous.items():
            self.assertEqual((self.destination / name).read_bytes(), content)
        self.assertEqual(config.read_bytes(), startup)
        self.assertEqual(retired.read_text(), "# Still needed until installation succeeds\n")

    def test_migration_keeps_old_completion_on_generation_failure_and_removes_only_retired_files(self):
        self.assert_installed(self.setup())
        startup = (self.home / ".zshrc").read_bytes()
        generated = self.destination / "generated"
        completion = (generated / "mise-completion.zsh").read_bytes()
        for path in generated.iterdir():
            path.rename(self.destination / path.name)
        generated.rmdir()
        for name in RETIRED_FILES:
            path = self.destination / name
            if not path.exists():
                path.write_text("# Retired Luna module\n")
        personal = self.destination / "personal.zsh"
        personal.write_text("# Keep this module\n")
        nested = self.destination / "personal/options.zsh"
        nested.parent.mkdir()
        nested.write_text("# Keep this directory\n")

        self.env["MISE_TEST_FAIL"] = "completion"
        self.assert_installed(self.setup())
        self.assertEqual((generated / "mise-completion.zsh").read_bytes(), completion)
        self.assertEqual((self.home / ".zshrc").read_bytes(), startup)
        self.assertEqual(personal.read_text(), "# Keep this module\n")
        self.assertEqual(nested.read_text(), "# Keep this directory\n")
        self.assertEqual(self.source_shell()["LUNA_MISE_TEST_COMPLETION"], "ready")

    def test_migration_preserves_old_completion_when_mise_is_missing(self):
        self.destination.mkdir(parents=True)
        completion = self.destination / "mise-completion.zsh"
        original = b"# Previous complete generation\n"
        completion.write_bytes(original)
        self.mise.unlink()
        self.assert_installed(self.setup())
        self.assertEqual((self.destination / "generated/mise-completion.zsh").read_bytes(), original)
        self.assertFalse(self.log.exists())

    def test_existing_new_completion_takes_precedence_over_retired_copy(self):
        self.assert_installed(self.setup())
        completion = self.destination / "generated/mise-completion.zsh"
        original = completion.read_bytes()
        (self.destination / "mise-completion.zsh").write_text("# Older copy\n")
        previous = self.destination / "autogenerated"
        previous.mkdir()
        (previous / "mise-completion.zsh").write_text("# Previous directory copy\n")
        self.env["MISE_TEST_FAIL"] = "completion"
        self.assert_installed(self.setup())
        self.assertEqual(completion.read_bytes(), original)
        self.assertFalse(previous.exists())

    def test_previous_generated_directory_migrates_completion_and_preserves_unknown_files(self):
        self.assert_installed(self.setup())
        current = self.destination / "generated"
        original = (current / "mise-completion.zsh").read_bytes()
        previous = self.destination / "autogenerated"
        current.rename(previous)
        personal = previous / "personal.zsh"
        personal.write_text("# Keep this generated user file\n")
        (self.destination / "mise-completion.zsh").write_text("# Older root copy\n")
        self.env["MISE_TEST_FAIL"] = "completion"
        self.assert_installed(self.setup())
        self.assertEqual((current / "mise-completion.zsh").read_bytes(), original)
        self.assertEqual({path.name for path in previous.iterdir()}, {"personal.zsh"})
        self.assertEqual(personal.read_text(), "# Keep this generated user file\n")
        self.assertEqual(self.source_shell()["LUNA_MISE_TEST_COMPLETION"], "ready")

    def test_previous_generated_directory_is_removed_if_empty_after_migration(self):
        self.assert_installed(self.setup())
        current = self.destination / "generated"
        original = (current / "mise-completion.zsh").read_bytes()
        previous = self.destination / "autogenerated"
        current.rename(previous)
        self.mise.unlink()
        self.assert_installed(self.setup())
        self.assertEqual((current / "mise-completion.zsh").read_bytes(), original)
        self.assertFalse(previous.exists())

    def test_retired_symlinks_are_removed_without_modifying_targets(self):
        self.destination.mkdir(parents=True)
        target = self.root / "personal.zsh"
        original = b"# Preserve external module\n"
        target.write_bytes(original)
        (self.destination / "paths.zsh").symlink_to(target)
        (self.destination / "mise-completion.zsh").symlink_to(target)
        self.mise.unlink()
        self.assert_installed(self.setup())
        self.assertEqual(target.read_bytes(), original)
        migrated = self.destination / "generated/mise-completion.zsh"
        self.assertFalse(migrated.is_symlink())
        self.assertEqual(migrated.read_bytes(), original)

    def test_generated_file_symlinks_are_replaced_without_modifying_targets(self):
        generated = self.destination / "generated"
        generated.mkdir(parents=True)
        target = self.root / "personal.zsh"
        original = b"# Preserve external file\n"
        target.write_bytes(original)
        for name in ("env.zsh", "mise-completion.zsh"):
            (generated / name).symlink_to(target)
        self.assert_installed(self.setup())
        self.assertEqual(target.read_bytes(), original)
        for name in ("env.zsh", "mise-completion.zsh"):
            self.assertFalse((generated / name).is_symlink())
        self.assertEqual(self.source_shell()["LUNA_MISE_TEST_COMPLETION"], "ready")

    def test_generated_directory_symlink_is_rejected_before_changes(self):
        self.destination.mkdir(parents=True)
        current = self.destination / "zshrc"
        current.write_text("# Previous entry point\n")
        target = self.root / "personal configs"
        target.mkdir()
        personal = target / "env.zsh"
        personal.write_text("# Preserve personal environment\n")
        for name in ("generated", "autogenerated"):
            with self.subTest(name=name):
                generated = self.destination / name
                generated.symlink_to(target)
                result = self.setup()
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertTrue(generated.is_symlink())
                self.assertEqual(personal.read_text(), "# Preserve personal environment\n")
                self.assertEqual(current.read_text(), "# Previous entry point\n")
                self.assertFalse(self.log.exists())
                generated.unlink()

    def test_generated_directory_file_conflict_is_rejected_before_changes(self):
        self.destination.mkdir(parents=True)
        for name in ("generated", "autogenerated"):
            with self.subTest(name=name):
                generated = self.destination / name
                generated.write_text("# Preserve conflicting file\n")
                result = self.setup()
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(generated.read_text(), "# Preserve conflicting file\n")
                self.assertFalse((self.destination / "zshrc").exists())
                self.assertFalse(self.log.exists())
                generated.unlink()

    def test_configuration_directory_conflicts_are_not_removed_or_partially_updated(self):
        for name in ("generated/env.zsh", "generated/mise-completion.zsh", "paths.zsh",
                     "autogenerated/env.zsh", "autogenerated/mise-completion.zsh"):
            with self.subTest(name=name):
                conflict = self.destination / name
                conflict.mkdir(parents=True)
                personal = conflict / "personal"
                personal.write_text("# Keep this directory\n")
                result = self.setup()
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(personal.read_text(), "# Keep this directory\n")
                self.assertFalse((self.destination / "zshrc").exists())
                self.assertFalse(self.log.exists())
                shutil.rmtree(conflict)

    def test_required_startup_write_failure_is_reported(self):
        config = self.home / ".zshrc"
        config.mkdir()
        personal = config / "personal"
        personal.write_text("Keep this directory\n")
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(personal.read_text(), "Keep this directory\n")

    def test_relative_config_paths_are_rejected(self):
        for name in ("LUNA_CONFIG_DIR", "XDG_CONFIG_HOME", "ZDOTDIR"):
            with self.subTest(variable=name):
                previous = self.env.get(name)
                self.env[name] = "relative config"
                result = self.setup()
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertFalse((self.root / "relative config").exists())
                if previous is None:
                    self.env.pop(name)
                else:
                    self.env[name] = previous

    def test_generated_destination_symlink_is_not_followed(self):
        target = self.root / "personal configs"
        target.mkdir()
        personal = target / "zshrc"
        personal.write_text("# Preserve personal config\n")
        self.destination.parent.mkdir(parents=True)
        self.destination.symlink_to(target)
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.destination.is_symlink())
        self.assertEqual(personal.read_text(), "# Preserve personal config\n")


if __name__ == "__main__":
    unittest.main()
