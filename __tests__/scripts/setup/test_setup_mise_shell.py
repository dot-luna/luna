"""Check mise activation and personal startup-file preservation in temporary homes."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


from __tests__.scripts.setup.app_fixture import copy_app_setup


REPO = Path(__file__).resolve().parents[3]
BLOCK_START = "# >>> Luna mise activation >>>"


class SetupMiseShellTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna mise shell '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.checkout = self.root / "checkout"
        copy_app_setup(self.checkout)

        # Isolate command lookup so a missing fake cannot activate the host mise.
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for name in ("bash", "readlink", "realpath", "dirname", "mkdir", "mktemp",
                     "cat", "chmod", "grep", "mv", "rm", "cp"):
            (self.bin / name).symlink_to(shutil.which(name))
        self.mise = self.bin / "mise"
        self.mise.write_text("""#!/bin/sh
printf '%s\\n' "$*" >> "$MISE_TEST_LOG"
if [ "$1" = --cd ]; then shift 2; fi
case "$1" in
    activate)
        printf 'export LUNA_MISE_TEST_ACTIVE=%s\\n' "$2"
        printf '_mise_hook() { return 0; }\\n'
        ;;
    completion) printf '# Generated completion fixture\\n' ;;
    *) exit 1 ;;
esac
""")
        self.mise.chmod(0o755)
        self.log = self.root / "mise.log"
        self.env = dict(os.environ, HOME=str(self.home), SHELL="/bin/bash", PATH=str(self.bin),
                        XDG_CONFIG_HOME=str(self.home / ".config"), TERM="xterm",
                        XDG_CACHE_HOME=str(self.home / ".cache"),
                        XDG_DATA_HOME=str(self.home / ".local/share"),
                        XDG_STATE_HOME=str(self.home / ".local/state"),
                        MISE_TEST_LOG=str(self.log))
        for name in ("ZDOTDIR", "BASH_ENV", "ENV", "LUNA_MISE_TEST_ACTIVE",
                     "LUNA_INSTALL_DIR", "LUNA_CONFIG_DIR", "ANDROID_HOME", "PNPM_HOME",
                     "HISTFILE", "HISTSIZE", "SAVEHIST"):
            self.env.pop(name, None)

    def setup(self, *arguments):
        return subprocess.run([shutil.which("bash"), str(self.checkout / "scripts/setup/mise-shell.sh"),
                               *arguments], env=self.env, cwd=self.root, input="",
                              capture_output=True, text=True, timeout=10)

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_preserves_contents_permissions_and_old_backups_on_rerun(self):
        config = self.home / ".bashrc"
        original = "# Personal settings\nexport PERSONAL_SETTING='keep me'"
        config.write_text(original)
        config.chmod(0o640)
        prior_backup = config.with_name(".bashrc.luna-backup")
        prior_backup.write_text("User-created backup\n")
        self.assert_success(self.setup())
        self.assertTrue(config.read_text().startswith(original + "\n"))
        self.assertEqual(config.stat().st_mode & 0o777, 0o640)
        self.assertEqual(prior_backup.read_text(), "User-created backup\n")
        installed = config.read_bytes()
        self.assert_success(self.setup())
        self.assertEqual(config.read_bytes(), installed)
        self.assertEqual(config.read_text().count(BLOCK_START), 1)
        self.assertEqual(list(self.home.rglob("*.luna-backup*")), [prior_backup])
        self.assertFalse(self.log.exists())

    def test_zdotdir_symlink_keeps_target_without_creating_backups(self):
        self.env["SHELL"] = "/usr/bin/zsh"
        custom = self.root / "zsh config"
        custom.mkdir()
        self.env["ZDOTDIR"] = str(custom)
        foreign = self.root / "personal.zshrc"
        original = "# Personal Zsh configuration\n"
        foreign.write_text(original)
        foreign.chmod(0o600)
        config = custom / ".zshrc"
        config.symlink_to(os.path.relpath(foreign, custom))
        old_backup = config.with_name(".zshrc.luna-backup")
        old_backup.write_text("Earlier backup\n")

        self.assert_success(self.setup())
        self.assertTrue(config.is_symlink())
        self.assertEqual(config.stat().st_mode & 0o777, 0o600)
        self.assertTrue(config.read_text().endswith(original))
        self.assertIn("source ", config.read_text().splitlines()[0])
        self.assertEqual(list(custom.glob("*.luna-backup*")), [old_backup])
        self.assertEqual(old_backup.read_text(), "Earlier backup\n")
        self.assertEqual(foreign.read_bytes(), config.read_bytes())
        self.assertFalse((self.home / ".zshrc").exists())

    def check_shell_activation(self, shell, arguments, command):
        self.env["SHELL"] = shutil.which(shell)
        self.assert_success(self.setup())
        result = subprocess.run([shutil.which(shell), *arguments, command], env=self.env,
                                cwd=self.root, input="", capture_output=True, text=True, timeout=10)
        self.assert_success(result)
        self.assertEqual(result.stdout.strip(), shell)
        if shell == "zsh":
            self.assertEqual(self.log.read_text(), f"--cd {self.home} completion zsh\n"
                             "activate zsh\n")
        else:
            self.assertEqual(self.log.read_text(), f"activate {shell}\n")

    def test_bash_activates_in_new_interactive_shell(self):
        self.check_shell_activation("bash", ["--noprofile", "-i", "-c"],
                                    'printf "%s\\n" "$LUNA_MISE_TEST_ACTIVE"')

    @unittest.skipUnless(shutil.which("zsh"), "Zsh is required")
    def test_zsh_activates_from_custom_zdotdir(self):
        self.env["ZDOTDIR"] = str(self.root / "zsh config")
        self.check_shell_activation("zsh", ["-d", "-i", "-c"],
                                    'printf "%s\\n" "$LUNA_MISE_TEST_ACTIVE"')

    def test_noninteractive_source_and_removed_mise_are_quiet(self):
        self.assert_success(self.setup())
        result = subprocess.run([shutil.which("bash"), "--noprofile", "--norc", "-c",
                                 'source "$HOME/.bashrc"'], env=self.env, cwd=self.root,
                                capture_output=True, text=True, timeout=10)
        self.assert_success(result)
        self.assertFalse(self.log.exists())
        self.mise.unlink()
        result = subprocess.run([shutil.which("bash"), "--noprofile", "-i", "-c", "true"],
                                env=self.env, cwd=self.root, input="", capture_output=True,
                                text=True, timeout=10)
        self.assert_success(result)
        self.assertNotIn("mise:", result.stderr)
        self.assertFalse(self.log.exists())

    def test_unsupported_shell_and_nonfile_startup_warn_without_changes(self):
        self.env["SHELL"] = "/bin/unknown-shell"
        result = self.setup()
        self.assert_success(result)
        self.assertIn("not supported", result.stderr)
        self.assertEqual(list(self.home.iterdir()), [])
        self.env["SHELL"] = "/bin/bash"
        config = self.home / ".bashrc"
        config.mkdir()
        personal = config / "keep"
        personal.write_text("Keep me\n")
        result = self.setup()
        self.assert_success(result)
        self.assertIn("non-file startup path", result.stderr)
        self.assertEqual(personal.read_text(), "Keep me\n")

    def test_arguments_are_ignored_during_normal_shell_setup(self):
        result = self.setup("--help", "-h", "--force", "--unknown", "main")
        self.assert_success(result)
        self.assertEqual((self.home / ".bashrc").read_text().count(BLOCK_START), 1)
        self.assertFalse(self.log.exists())

    def test_missing_mise_warns_and_skips_without_modifying_home(self):
        self.mise.unlink()
        result = self.setup("--help", "-h", "--force", "--unknown", "main")
        self.assert_success(result)
        self.assertIn("mise", result.stderr)
        self.assertIn("[WARN]", result.stderr)
        self.assertEqual(list(self.home.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
