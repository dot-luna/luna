"""Exercise NVIDIA setup consent and command ordering without touching the host."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]


class SetupNvidiaTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna nvidia '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.checkout = self.root / "checkout"
        for name in ("scripts/setup/nvidia.sh", "lib/common.sh"):
            destination = self.checkout / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, destination)
        self.env = dict(os.environ, PATH=str(self.bin) + ":" + os.environ["PATH"],
                        TEST_NVIDIA_ROOT=str(self.root), BASH_ENV="")
        for name in ("TEST_NVIDIA_KERNEL_STATUS", "TEST_NVIDIA_PACKAGE_STATUS",
                     "TEST_NVIDIA_INITRAMFS_STATUS"):
            self.env.pop(name, None)

        # Even root test runs reach only these mocks for all privileged operations.
        backend = f"#!{sys.executable}\n" + '''
import json, os, pathlib, sys
root = pathlib.Path(os.environ["TEST_NVIDIA_ROOT"])
tool = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with (root / "calls.jsonl").open("a") as output:
    output.write(json.dumps([tool, *args]) + "\\n")
if tool == "sudo":
    if not args or args[0] not in ("pacman", "install", "tee", "mkinitcpio"):
        sys.exit("Unexpected sudo invocation")
    os.execv(str(root / "bin" / args[0]), args)
elif tool == "pacman":
    if args == ["-Q", "linux"]:
        sys.exit(int(os.environ.get("TEST_NVIDIA_KERNEL_STATUS", "0")))
    if args != ["-Syu", "--noconfirm", "--needed", "--", "linux", "nvidia-open", "nvidia-utils", "nvidia-settings"]:
        sys.exit("Unexpected pacman invocation: " + repr(args))
    sys.exit(int(os.environ.get("TEST_NVIDIA_PACKAGE_STATUS", "0")))
elif tool == "install":
    if args != ["-d", "/etc/modprobe.d"]:
        sys.exit("Unexpected install invocation")
elif tool == "tee":
    if args != ["/etc/modprobe.d/luna-nvidia.conf"]:
        sys.exit("Unexpected tee invocation")
    (root / "luna-nvidia.conf").write_text(sys.stdin.read())
elif tool == "mkinitcpio":
    if args != ["-P"]:
        sys.exit("Unexpected mkinitcpio invocation")
    sys.exit(int(os.environ.get("TEST_NVIDIA_INITRAMFS_STATUS", "0")))
'''
        for name in ("sudo", "pacman", "install", "tee", "mkinitcpio"):
            path = self.bin / name
            path.write_text(backend)
            path.chmod(0o755)

    def setup(self, *arguments, answer=""):
        return subprocess.run(["bash", str(self.checkout / "scripts/setup/nvidia.sh"), *arguments],
                              env=self.env, cwd=self.root, input=answer,
                              capture_output=True, text=True, timeout=10)

    def calls(self):
        path = self.root / "calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_decline_blank_and_eof_skip_without_running_commands(self):
        for answer in ("no\n", "n\n", "\n", ""):
            with self.subTest(answer=answer):
                result = self.setup(answer=answer)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("[y/N]", result.stdout)
                self.assertIn("NVIDIA setup skipped", result.stdout)
                self.assertEqual(self.calls(), [])

    def test_accepted_setup_installs_tools_before_configuring_and_rebuilding(self):
        result = self.setup(answer="yes\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("Install NVIDIA drivers and tools now?"), 1)
        self.assertIn("Reboot to load the driver", result.stdout)
        operations = [call for call in self.calls() if call[0] != "sudo"]
        self.assertEqual(operations, [
            ["pacman", "-Q", "linux"],
            ["pacman", "-Syu", "--noconfirm", "--needed", "--", "linux", "nvidia-open", "nvidia-utils", "nvidia-settings"],
            ["install", "-d", "/etc/modprobe.d"],
            ["tee", "/etc/modprobe.d/luna-nvidia.conf"],
            ["mkinitcpio", "-P"],
        ])
        expected_sudo = [["sudo", *call] for call in operations[1:]] if os.geteuid() != 0 else []
        self.assertEqual([call for call in self.calls() if call[0] == "sudo"], expected_sudo)
        self.assertEqual((self.root / "luna-nvidia.conf").read_text(),
                         "blacklist nouveau\noptions nvidia_drm modeset=1 fbdev=1\n")

    def test_invalid_confirmation_can_be_corrected_without_running_commands(self):
        result = self.setup(answer="maybe\nno\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("NVIDIA setup skipped", result.stdout)
        self.assertEqual(self.calls(), [])

    def test_ignored_arguments_do_not_bypass_nvidia_consent(self):
        result = self.setup("--help", "-h", "--force", "--yes", "main")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("[y/N]", result.stdout)
        self.assertIn("NVIDIA setup skipped", result.stdout)
        self.assertEqual(self.calls(), [])

    def test_unsupported_kernel_warns_and_skips_before_privileged_operations(self):
        self.env["TEST_NVIDIA_KERNEL_STATUS"] = "1"
        result = self.setup(answer="yes\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("standard Arch linux kernel", result.stderr)
        self.assertIn("[WARN]", result.stderr)
        self.assertEqual(self.calls(), [["pacman", "-Q", "linux"]])

    @unittest.skipIf(os.geteuid() == 0, "Root does not require sudo")
    def test_missing_sudo_warns_and_skips_before_privileged_operations(self):
        # A closed PATH prevents this missing-helper case from finding the host sudo.
        for name in ("bash", "readlink", "dirname"):
            (self.bin / name).symlink_to(shutil.which(name))
        (self.bin / "sudo").unlink()
        self.env["PATH"] = str(self.bin)
        result = self.setup(answer="yes\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("sudo is unavailable", result.stderr)
        self.assertIn("[WARN]", result.stderr)
        self.assertEqual(self.calls(), [["pacman", "-Q", "linux"]])

    def test_package_failure_does_not_write_config_or_rebuild(self):
        self.env["TEST_NVIDIA_PACKAGE_STATUS"] = "7"
        result = self.setup(answer="yes\n")
        self.assertEqual(result.returncode, 7)
        self.assertFalse((self.root / "luna-nvidia.conf").exists())
        self.assertFalse(any(call[0] in ("install", "tee", "mkinitcpio") for call in self.calls()))
        self.assertNotIn("drivers and tools installed", result.stdout)

    def test_package_install_does_not_ask_for_a_second_confirmation(self):
        result = self.setup(answer="yes\nno\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / "luna-nvidia.conf").exists())
        self.assertIn("--noconfirm", next(call for call in self.calls() if "-Syu" in call))

    def test_initramfs_failure_is_not_reported_as_success(self):
        self.env["TEST_NVIDIA_INITRAMFS_STATUS"] = "9"
        result = self.setup(answer="yes\n")
        self.assertEqual(result.returncode, 9)
        self.assertNotIn("drivers and tools installed", result.stdout)


if __name__ == "__main__":
    unittest.main()
