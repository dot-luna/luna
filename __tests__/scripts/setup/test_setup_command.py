"""Check command deployment and shell lookup using disposable homes only."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]
BLOCK_START = "# >>> Luna command PATH >>>"


class SetupCommandTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna command '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.checkout = self.root / "checkout"
        for name in ("scripts/setup/command.sh", "lib/common.sh"):
            destination = self.checkout / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, destination)
        self.launcher = self.checkout / "bin/luna"
        self.launcher.parent.mkdir()
        self.launcher.write_text("#!/bin/sh\nprintf 'Installed checkout\\n'\n")
        self.launcher.chmod(0o755)
        self.target = self.home / ".local/bin/luna"
        self.env = dict(os.environ, HOME=str(self.home), SHELL="/bin/bash",
                        XDG_CONFIG_HOME=str(self.home / ".config"), TERM="xterm")
        self.env.pop("ZDOTDIR", None)

    def setup(self, *arguments):
        return subprocess.run(["bash", str(self.checkout / "scripts/setup/command.sh"), *arguments],
                              env=self.env, cwd=self.root, input="", capture_output=True,
                              text=True, timeout=10)

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.target.is_symlink())
        self.assertEqual(self.target.resolve(), self.launcher)

    def test_fresh_setup_and_rerun_do_not_duplicate_config_or_backups(self):
        for _ in range(2):
            self.assert_success(self.setup())
        config = self.home / ".bashrc"
        self.assertEqual(config.read_text().count(BLOCK_START), 1)
        self.assertEqual(list(self.home.rglob("*.luna-backup*")), [])

    def test_existing_shell_config_is_preserved_without_new_backups(self):
        config = self.home / ".bashrc"
        original = "# Personal settings\nexport PERSONAL_SETTING='keep me'"
        config.write_text(original)
        config.chmod(0o640)
        prior_backup = config.with_name(".bashrc.luna-backup")
        prior_backup.write_text("User-created backup\n")
        self.assert_success(self.setup())
        self.assertTrue(config.read_text().startswith(original + "\n"))
        self.assertEqual(prior_backup.read_text(), "User-created backup\n")
        self.assertEqual(config.stat().st_mode & 0o777, 0o640)
        installed = config.read_bytes()
        self.assert_success(self.setup())
        self.assertEqual(config.read_bytes(), installed)
        self.assertEqual(list(self.home.rglob("*.luna-backup*")), [prior_backup])

    def test_command_conflicts_are_replaced_without_new_backups(self):
        self.target.parent.mkdir(parents=True)
        first_backup = self.target.with_name("luna.luna-backup")
        first_backup.symlink_to("previous-missing-target")
        foreign = self.root / "foreign"
        foreign.write_text("Foreign launcher\n")
        for kind in ("file", "directory", "symlink", "dangling"):
            with self.subTest(kind=kind):
                if self.target.is_symlink():
                    self.target.unlink()
                if kind == "file":
                    self.target.write_text("Personal launcher\n")
                elif kind == "directory":
                    self.target.mkdir()
                    (self.target / "keep").write_text("Personal directory\n")
                else:
                    destination = foreign if kind == "symlink" else self.root / "missing"
                    self.target.symlink_to(os.path.relpath(destination, self.target.parent))

                self.assert_success(self.setup())
                self.assertEqual(list(self.home.rglob("*.luna-backup*")), [first_backup])
        self.assertEqual(first_backup.readlink(), Path("previous-missing-target"))
        self.assertEqual(foreign.read_text(), "Foreign launcher\n")

    def test_checkout_inside_command_target_is_preserved(self):
        self.target.parent.mkdir(parents=True)
        destination = self.target / "checkout"
        destination.parent.mkdir()
        self.checkout.rename(destination)
        self.checkout = destination
        self.launcher = self.checkout / "bin/luna"

        result = self.setup()

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("checkout", result.stderr)
        self.assertTrue(self.launcher.is_file())
        self.assertTrue((self.checkout / "scripts/setup/command.sh").is_file())
        self.assertFalse((self.home / ".bashrc").exists())

    def test_command_target_aliasing_checkout_bin_is_preserved(self):
        self.target.parent.parent.mkdir(parents=True)
        self.target.parent.symlink_to(self.checkout / "bin")
        original = self.launcher.read_bytes()

        result = self.setup()

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("checkout", result.stderr)
        self.assertFalse(self.launcher.is_symlink())
        self.assertEqual(self.launcher.read_bytes(), original)
        self.assertFalse((self.home / ".bashrc").exists())

    def test_zdotdir_symlink_config_keeps_original_target_unchanged(self):
        self.env["SHELL"] = "/usr/bin/zsh"
        custom = self.root / "zsh config"
        custom.mkdir()
        self.env["ZDOTDIR"] = str(custom)
        foreign = self.root / "personal.zshrc"
        foreign.write_text("# Personal Zsh configuration\n")
        config = custom / ".zshrc"
        config.symlink_to(os.path.relpath(foreign, custom))
        self.assert_success(self.setup())
        self.assertFalse(config.is_symlink())
        self.assertIn(BLOCK_START, config.read_text())
        self.assertTrue(config.read_text().startswith("# Personal Zsh configuration\n"))
        self.assertEqual(list(custom.glob("*.luna-backup*")), [])
        self.assertEqual(foreign.read_text(), "# Personal Zsh configuration\n")
        self.assertFalse((self.home / ".zshrc").exists())

    def check_shell_lookup(self, shell, config, arguments, command):
        # A pre-existing checkout used to win PATH resolution in every new shell.
        old_bin = self.home / "coding/luna/bin"
        old_bin.mkdir(parents=True)
        old_launcher = old_bin / "luna"
        old_launcher.write_text("#!/bin/sh\nprintf 'Old checkout\\n'\n")
        old_launcher.chmod(0o755)
        self.env["SHELL"] = shutil.which(shell)
        config.parent.mkdir(parents=True, exist_ok=True)
        if shell == "fish":
            config.write_text('set -gx PATH "$HOME/coding/luna/bin" $PATH\n')
        else:
            config.write_text('export PATH="$HOME/coding/luna/bin:$PATH"\n')
        self.assert_success(self.setup())
        result = subprocess.run([shutil.which(shell), *arguments, command], env=self.env,
                                cwd=self.root, input="", capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.target))

    def test_bash_prefers_installed_checkout_in_new_interactive_shell(self):
        self.check_shell_lookup("bash", self.home / ".bashrc",
                                ["--noprofile", "-i", "-c"], "command -v luna")

    @unittest.skipUnless(shutil.which("zsh"), "Zsh is required")
    def test_zsh_prefers_installed_checkout_in_new_interactive_shell(self):
        custom = self.root / "zsh config"
        self.env["ZDOTDIR"] = str(custom)
        self.check_shell_lookup("zsh", custom / ".zshrc", ["-d", "-i", "-c"], "command -v luna")

    @unittest.skipUnless(shutil.which("fish"), "fish is required")
    def test_fish_prefers_installed_checkout_in_new_interactive_shell(self):
        self.check_shell_lookup("fish", self.home / ".config/fish/config.fish",
                                ["-i", "-c"], "command -s luna")

    def test_unsupported_shell_warns_after_installing_command(self):
        self.env["SHELL"] = "/bin/unknown-shell"
        result = self.setup()
        self.assert_success(result)
        self.assertIn("not supported", result.stdout + result.stderr)
        self.assertFalse((self.home / ".bashrc").exists())

    def test_directory_at_startup_path_is_preserved_with_warning(self):
        config = self.home / ".bashrc"
        config.mkdir()
        personal = config / "keep"
        personal.write_text("Keep me\n")
        result = self.setup()
        self.assert_success(result)
        self.assertIn("non-file startup path", result.stdout + result.stderr)
        self.assertEqual(personal.read_text(), "Keep me\n")

    def test_arguments_are_ignored_during_normal_command_setup(self):
        result = self.setup("--help", "-h", "--force", "--unknown", "main")
        self.assert_success(result)
        self.assertEqual((self.home / ".bashrc").read_text().count(BLOCK_START), 1)
        self.assertEqual(list(self.home.rglob("*.luna-backup*")), [])


if __name__ == "__main__":
    unittest.main()
