"""Configure temporary D-Bus/PAM files without using sudo or a real keyring."""

import contextlib
import importlib.util
import io
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[3]
HELPER = REPO / "scripts/setup/keyring-config.py"
SPEC = importlib.util.spec_from_file_location("luna_keyring_config", HELPER)
keyring = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(keyring)

SERVICE = b"[D-BUS Service]\nName=org.freedesktop.secrets\n" \
          b"Exec=/usr/bin/gnome-keyring-daemon --start --foreground --components=secrets\n"
PAM = b"#%PAM-1.0\nauth include system-login\npassword include system-login\nsession include system-login\n"


class KeyringConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luna keyring '")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "config"
        self.data = self.root / "data"
        self.service = self.root / "packaged.service"
        self.service.write_bytes(SERVICE)
        self.pam = self.root / "pam.d/sddm"
        self.pam.parent.mkdir()
        self.pam.write_bytes(keyring.pam_content(PAM))
        self.destination = self.data / "dbus-1/services/org.freedesktop.secrets.service"
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(keyring, "PAM_FILE", self.pam).start()
        mock.patch.object(keyring, "DBUS_SERVICE", self.service).start()
        self.sudo = mock.patch.object(keyring.shutil, "which", return_value="/test/sudo").start()
        self.run = mock.patch.object(keyring.subprocess, "run",
                                     return_value=subprocess.CompletedProcess([], 0)).start()
        self.errors = io.StringIO()
        self.stderr = contextlib.redirect_stderr(self.errors)
        self.stderr.__enter__()
        self.addCleanup(self.stderr.__exit__, None, None, None)

    def configure(self):
        keyring.configure(str(self.config), str(self.data))

    def test_provider_is_installed_without_modifying_adequate_pam_or_credentials(self):
        original = self.pam.read_bytes()
        self.configure()
        self.assertEqual(self.destination.read_bytes(), SERVICE)
        self.assertEqual(self.pam.read_bytes(), original)
        self.assertFalse(self.config.exists())
        self.assertFalse((self.data / "keyrings").exists())
        self.run.assert_not_called()
        self.assertEqual(self.errors.getvalue(), "")
        before = self.destination.stat()
        self.configure()
        self.assertEqual(self.destination.stat().st_mtime_ns, before.st_mtime_ns)

    def test_provider_preserves_regular_file_mode(self):
        self.destination.parent.mkdir(parents=True)
        self.destination.write_bytes(b"personal provider\n")
        self.destination.chmod(0o640)
        self.configure()
        self.assertEqual(self.destination.read_bytes(), SERVICE)
        self.assertEqual(stat.S_IMODE(self.destination.stat().st_mode), 0o640)

    def test_replacing_provider_symlink_preserves_its_old_target(self):
        previous = self.root / "previous.service"
        previous.write_bytes(b"another provider\n")
        self.destination.parent.mkdir(parents=True)
        self.destination.symlink_to(previous)
        self.configure()
        self.assertFalse(self.destination.is_symlink())
        self.assertEqual(self.destination.read_bytes(), SERVICE)
        self.assertEqual(previous.read_bytes(), b"another provider\n")

    def test_existing_symlink_to_packaged_provider_is_preserved(self):
        self.destination.parent.mkdir(parents=True)
        self.destination.symlink_to(self.service)
        self.configure()
        self.assertTrue(self.destination.is_symlink())
        self.assertEqual(self.destination.resolve(), self.service)

    def test_invalid_xdg_paths_fail_before_writes(self):
        for config, data in (("relative", str(self.data)), (str(self.config), "relative")):
            with self.subTest(config=config, data=data), self.assertRaises(ValueError):
                keyring.configure(config, data)
        self.assertFalse(self.data.exists())
        self.run.assert_not_called()

    def test_missing_packaged_provider_and_directory_conflict_fail(self):
        self.service.unlink()
        with self.assertRaises(FileNotFoundError):
            self.configure()
        self.assertFalse(self.data.exists())
        self.service.write_bytes(SERVICE)
        self.destination.mkdir(parents=True)
        with self.assertRaises(ValueError):
            self.configure()
        self.run.assert_not_called()

    def test_repository_parent_symlink_is_rejected_before_writes(self):
        self.data.mkdir()
        (self.data / "dbus-1").symlink_to(REPO, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "checkout"):
            self.configure()
        self.run.assert_not_called()

    def test_failed_atomic_provider_write_propagates_and_cleans_temporary_file(self):
        with mock.patch.object(keyring.os, "replace", side_effect=PermissionError("read-only")):
            with self.assertRaises(PermissionError):
                self.configure()
        self.assertEqual(list(self.destination.parent.iterdir()), [])
        self.run.assert_not_called()

    def test_pam_adds_only_missing_hooks_preserving_original_bytes_mode_and_symlink(self):
        target = self.root / "original pam"
        original = PAM.replace(b"\n", b"\r\n") + b"-auth optional pam_gnome_keyring.so # existing"
        target.write_bytes(original)
        target.chmod(0o640)
        self.pam.unlink()
        self.pam.symlink_to(target)
        keyring.configure_sddm(self.pam)
        updated = target.read_bytes()
        self.assertTrue(updated.startswith(original + b"\r\n"))
        self.assertEqual(updated.count(b"-auth optional pam_gnome_keyring.so"), 1)
        self.assertIn(b"-password optional pam_gnome_keyring.so use_authtok\r\n", updated)
        self.assertIn(b"-session optional pam_gnome_keyring.so auto_start\r\n", updated)
        self.assertTrue(self.pam.is_symlink())
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o640)
        before = target.stat().st_mtime_ns
        keyring.configure_sddm(self.pam)
        self.assertEqual(target.stat().st_mtime_ns, before)

    def test_adequate_absolute_modules_controls_and_continuations_are_recognized(self):
        content = (
            b"auth [success=ok default=ignore] /usr/lib/security/pam_gnome_keyring.so\n"
            b"-password optional pam_gnome_keyring.so \\\n    use_authtok\n"
            b"session required pam_gnome_keyring.so auto_start only_if=sddm\n"
        )
        self.assertEqual(keyring.pam_content(content), content)

    def test_comments_and_inadequate_hooks_do_not_count_as_unlock_integration(self):
        content = (
            b"# -auth optional pam_gnome_keyring.so\n"
            b"password optional pam_gnome_keyring.so # use_authtok\n"
            b"session optional pam_gnome_keyring.so auto_starting\n"
        )
        updated = keyring.pam_content(content)
        self.assertTrue(updated.startswith(content))
        for _, _, line in keyring.HOOKS:
            self.assertIn(line + b"\n", updated)

    def test_hooks_restricted_to_another_login_manager_do_not_count(self):
        content = (b"auth optional pam_gnome_keyring.so only_if=gdm,login\n"
                   b"password optional pam_gnome_keyring.so use_authtok only_if=gdm\n"
                   b"session optional pam_gnome_keyring.so auto_start only_if=login\n")
        updated = keyring.pam_content(content)
        self.assertTrue(updated.startswith(content))
        for _, _, line in keyring.HOOKS:
            self.assertIn(line + b"\n", updated)

    def test_missing_hooks_call_only_the_helper_sddm_mode_through_sudo(self):
        self.pam.write_bytes(PAM)
        self.configure()
        self.run.assert_called_once_with(
            ["/test/sudo", "/usr/bin/python3", str(HELPER), "sddm", str(self.pam)], check=False)
        self.assertEqual(self.pam.read_bytes(), PAM)

    def test_missing_sddm_warns_without_creating_it(self):
        self.pam.unlink()
        self.configure()
        self.assertEqual(self.destination.read_bytes(), SERVICE)
        self.assertFalse(self.pam.exists())
        self.assertIn("login manager manually", self.errors.getvalue())
        self.run.assert_not_called()

    def test_unavailable_or_failing_sudo_warns_without_failing_provider_setup(self):
        self.pam.write_bytes(PAM)
        self.sudo.return_value = None
        self.configure()
        self.assertIn("sudo is unavailable", self.errors.getvalue())
        self.run.assert_not_called()
        self.sudo.return_value = "/test/sudo"
        self.run.return_value = subprocess.CompletedProcess([], 1)
        self.configure()
        self.assertIn("auto-unlock setup failed", self.errors.getvalue())
        self.run.side_effect = PermissionError("blocked")
        self.configure()
        self.assertIn("blocked", self.errors.getvalue())
        self.assertEqual(self.destination.read_bytes(), SERVICE)
        self.assertEqual(self.pam.read_bytes(), PAM)

    def test_privileged_mode_rejects_other_services_missing_files_and_repo_targets(self):
        other = self.pam.with_name("other")
        other.write_bytes(PAM)
        with self.assertRaisesRegex(ValueError, "Only the SDDM"):
            keyring.configure_sddm(other)
        self.assertEqual(other.read_bytes(), PAM)
        self.pam.unlink()
        with self.assertRaises(FileNotFoundError):
            keyring.configure_sddm(self.pam)
        self.pam.symlink_to(REPO / "AGENTS.md")
        with self.assertRaisesRegex(ValueError, "checkout"):
            keyring.configure_sddm(self.pam)

    def test_pam_write_failure_preserves_existing_file(self):
        self.pam.write_bytes(PAM)
        with mock.patch.object(keyring.os, "replace", side_effect=PermissionError("read-only")):
            with self.assertRaises(PermissionError):
                keyring.configure_sddm(self.pam)
        self.assertEqual(self.pam.read_bytes(), PAM)
        self.assertEqual(list(self.pam.parent.iterdir()), [self.pam])


if __name__ == "__main__":
    unittest.main()
