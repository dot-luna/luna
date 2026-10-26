"""Check global command installation with redirected paths and fake privileges."""

import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]


class SetupCommandTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna command '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.checkout = self.root / "checkout"
        self.target = self.root / "system/usr/local/bin/luna"
        for name in ("scripts/setup/8-install-luna-command.sh", "lib/common.sh"):
            destination = self.checkout / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, destination)

        # Redirect the production constant before execution; never write to /usr.
        # A fixture-only variable exercises both privilege branches as any user.
        entrypoint = self.checkout / "scripts/setup/8-install-luna-command.sh"
        script = entrypoint.read_text()
        self.assertIn("command_target=/usr/local/bin/luna", script)
        self.assertIn("(( EUID != 0 ))", script)
        script = script.replace("command_target=/usr/local/bin/luna",
                                "command_target=" + shlex.quote(str(self.target)))
        script = script.replace("(( EUID != 0 ))", "(( LUNA_TEST_EUID != 0 ))")
        entrypoint.write_text(script)

        self.launcher = self.checkout / "bin/luna"
        self.launcher.parent.mkdir()
        self.launcher.write_text("#!/bin/sh\nprintf 'Installed checkout\\n'\n")
        self.launcher.chmod(0o755)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for name in ("bash", "readlink", "realpath", "mkdir", "ln"):
            (self.bin / name).symlink_to(shutil.which(name))
        self.sudo = self.bin / "sudo"
        self.sudo.write_text(
            '#!/bin/sh\n'
            'printf "%s\\n" "$1" >> "$SUDO_TEST_LOG"\n'
            'if [ "$1" = "${SUDO_FAIL_COMMAND:-}" ]; then exit 73; fi\n'
            'exec "$@"\n'
        )
        self.sudo.chmod(0o755)
        self.log = self.root / "sudo.log"
        self.env = dict(os.environ, HOME=str(self.home), SHELL="/bin/bash",
                        PATH=str(self.bin), LUNA_TEST_EUID="1000", SUDO_TEST_LOG=str(self.log))
        for name in ("ZDOTDIR", "BASH_ENV", "ENV", "SUDO_FAIL_COMMAND"):
            self.env.pop(name, None)

    def setup(self, *arguments, entrypoint=None):
        entrypoint = entrypoint or self.checkout / "scripts/setup/8-install-luna-command.sh"
        return subprocess.run([shutil.which("bash"), str(entrypoint), *arguments],
                              env=self.env, cwd=self.home, input="", capture_output=True,
                              text=True, timeout=10)

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.target.is_symlink())
        self.assertEqual(self.target.resolve(), self.launcher)

    def test_global_link_is_installed_once_without_startup_files_or_backups(self):
        self.assert_success(self.setup())
        self.assertEqual(self.log.read_text().splitlines(), ["mkdir", "ln"])
        installed_inode = self.target.lstat().st_ino
        self.assert_success(self.setup())
        self.assertEqual(self.target.lstat().st_ino, installed_inode)
        self.assertEqual(self.log.read_text().splitlines(), ["mkdir", "ln"])
        self.assertEqual(list(self.home.iterdir()), [])
        self.assertEqual(list(self.root.rglob("*.luna-backup*")), [])

        result = subprocess.run([str(self.target)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "Installed checkout\n")

    def test_root_installs_directly_without_sudo(self):
        self.env["LUNA_TEST_EUID"] = "0"
        self.sudo.unlink()
        self.assert_success(self.setup())
        self.assertFalse(self.log.exists())

    def test_nonroot_requires_sudo_before_creating_target_parent(self):
        self.sudo.unlink()
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("sudo is missing", result.stderr)
        self.assertFalse(self.target.parent.exists())

    def test_correct_existing_link_needs_no_sudo(self):
        self.target.parent.mkdir(parents=True)
        self.target.symlink_to(self.launcher)
        self.sudo.unlink()
        self.assert_success(self.setup())
        self.assertFalse(self.log.exists())

    def test_files_and_symlinks_are_replaced_without_following_their_targets(self):
        self.target.parent.mkdir(parents=True)
        first_backup = self.target.with_name("luna.luna-backup")
        first_backup.symlink_to("previous-missing-target")
        foreign = self.root / "foreign"
        foreign.write_text("Foreign launcher\n")
        foreign_directory = self.root / "foreign-directory"
        foreign_directory.mkdir()
        personal = foreign_directory / "keep"
        personal.write_text("Personal file\n")
        for kind in ("file", "symlink", "directory-link", "dangling"):
            with self.subTest(kind=kind):
                if self.target.is_symlink():
                    self.target.unlink()
                if kind == "file":
                    self.target.write_text("Personal launcher\n")
                else:
                    destination = {"symlink": foreign, "directory-link": foreign_directory,
                                   "dangling": self.root / "missing"}[kind]
                    self.target.symlink_to(os.path.relpath(destination, self.target.parent))
                self.assert_success(self.setup())
        self.assertEqual(first_backup.readlink(), Path("previous-missing-target"))
        self.assertEqual(foreign.read_text(), "Foreign launcher\n")
        self.assertEqual(personal.read_text(), "Personal file\n")
        self.assertEqual(list(self.root.rglob("*.luna-backup*")), [first_backup])

    def test_directory_at_command_target_is_preserved(self):
        self.target.mkdir(parents=True)
        personal = self.target / "keep"
        personal.write_text("Personal directory\n")
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("destination is a directory", result.stderr)
        self.assertEqual(personal.read_text(), "Personal directory\n")
        self.assertFalse(self.log.exists())

    def test_checkout_inside_command_target_is_preserved(self):
        self.target.mkdir(parents=True)
        destination = self.target / "checkout"
        self.checkout.rename(destination)
        self.checkout = destination
        self.launcher = self.checkout / "bin/luna"
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("checkout", result.stderr)
        self.assertTrue(self.launcher.is_file())
        self.assertFalse(self.log.exists())

    def test_command_target_parent_aliasing_checkout_bin_is_preserved(self):
        self.target.parent.parent.mkdir(parents=True)
        self.target.parent.symlink_to(self.checkout / "bin")
        original = self.launcher.read_bytes()
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("checkout", result.stderr)
        self.assertFalse(self.launcher.is_symlink())
        self.assertEqual(self.launcher.read_bytes(), original)
        self.assertFalse(self.log.exists())

    def test_missing_nonexecutable_or_directory_launcher_is_rejected(self):
        for kind in ("missing", "nonexecutable", "directory"):
            with self.subTest(kind=kind):
                if self.launcher.is_file():
                    self.launcher.unlink()
                if kind == "nonexecutable":
                    self.launcher.write_text("Not executable\n")
                elif kind == "directory":
                    self.launcher.mkdir()
                result = self.setup()
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("missing or not executable", result.stderr)
                self.assertFalse(self.target.parent.exists())
                self.assertFalse(self.log.exists())

    def test_privileged_operation_failure_is_required_and_preserves_existing_file(self):
        self.target.parent.mkdir(parents=True)
        self.target.write_text("Existing command\n")
        for command in ("mkdir", "ln"):
            with self.subTest(command=command):
                self.env["SUDO_FAIL_COMMAND"] = command
                result = self.setup()
                self.assertEqual(result.returncode, 73, result.stdout + result.stderr)
                self.assertEqual(self.target.read_text(), "Existing command\n")
                self.assertNotIn("Installed Luna command", result.stdout)

    def test_entrypoint_symlink_resolves_the_checkout_from_another_directory(self):
        entrypoint = self.root / "install-command.sh"
        entrypoint.symlink_to(self.checkout / "scripts/setup/8-install-luna-command.sh")
        self.assert_success(self.setup(entrypoint=entrypoint))

    def test_shell_startup_files_and_user_local_command_are_untouched(self):
        bash_config = self.home / ".bashrc"
        original_bash = b"# Personal Bash configuration\n"
        bash_config.write_bytes(original_bash)
        foreign_zsh = self.root / "personal.zshrc"
        original_zsh = b"# Personal Zsh configuration\r\n"
        foreign_zsh.write_bytes(original_zsh)
        zsh_config = self.home / ".zshrc"
        zsh_config.symlink_to(foreign_zsh)
        custom_zsh = self.root / "custom-zsh"
        custom_zsh.mkdir()
        self.env["ZDOTDIR"] = str(custom_zsh)
        local_command = self.home / ".local/bin/luna"
        local_command.parent.mkdir(parents=True)
        local_command.symlink_to("previous-checkout")

        for shell in ("/bin/bash", "/bin/zsh", "/bin/fish", "/bin/unknown-shell", ""):
            with self.subTest(shell=shell):
                self.env["SHELL"] = shell
                self.assert_success(self.setup())
                self.assertEqual(bash_config.read_bytes(), original_bash)
                self.assertTrue(zsh_config.is_symlink())
                self.assertEqual(foreign_zsh.read_bytes(), original_zsh)
                self.assertEqual(list(custom_zsh.iterdir()), [])
                self.assertEqual(local_command.readlink(), Path("previous-checkout"))
                self.target.unlink()

    def test_arguments_are_ignored_during_normal_command_setup(self):
        self.assert_success(self.setup("--help", "-h", "--force", "--unknown", "main"))
        self.assertEqual(list(self.home.iterdir()), [])

    def test_previous_local_launcher_warns_without_being_removed(self):
        previous = self.root / "previous-checkout/bin/luna"
        previous.parent.mkdir(parents=True)
        previous.write_text("#!/bin/sh\nprintf 'Previous checkout\\n'\n")
        previous.chmod(0o755)
        local_command = self.home / ".local/bin/luna"
        local_command.parent.mkdir(parents=True)
        local_command.symlink_to(previous)

        for _ in range(2):
            result = self.setup()
            self.assert_success(result)
            self.assertIn("may override this installation", result.stderr)
            self.assertEqual(local_command.resolve(), previous)

        local_command.unlink()
        local_command.symlink_to(self.launcher)
        result = self.setup()
        self.assert_success(result)
        self.assertNotIn("may override", result.stderr)


if __name__ == "__main__":
    unittest.main()
