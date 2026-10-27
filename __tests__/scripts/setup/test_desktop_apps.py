"""Install and launch Settings entries inside temporary, isolated XDG homes."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[3]


class DesktopAppTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna desktop '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.checkout = self.root / "checkout"
        self.helper = self.checkout / "scripts/setup/desktop-apps.py"
        self.helper.parent.mkdir(parents=True)
        shutil.copy2(REPO / "scripts/setup/desktop-apps.py", self.helper)
        self.command = self.checkout / "bin/luna"
        self.command.parent.mkdir()
        self.command.write_text('''#!/usr/bin/python3
import json, os, pathlib, sys
pathlib.Path(os.environ["TEST_LAUNCH_RECORD"]).write_text(json.dumps({
    "argv": sys.argv,
    "install_dir": os.environ.get("LUNA_INSTALL_DIR"),
}))
''')
        self.command.chmod(0o755)
        self.shell = self.checkout / "src/luna-settings/shell.qml"
        self.shell.parent.mkdir(parents=True)
        self.shell.write_text("// Settings fixture\n")
        self.data_home = self.home / ".local/share"
        self.desktop = self.data_home / "applications/luna-settings.desktop"
        self.env = dict(os.environ, HOME=str(self.home), PATH="/usr/bin",
                        XDG_DATA_HOME=str(self.data_home),
                        XDG_DATA_DIRS=str(self.root / "system data"),
                        XDG_CONFIG_HOME=str(self.home / ".config"),
                        XDG_CONFIG_DIRS=str(self.root / "system config"),
                        XDG_CACHE_HOME=str(self.home / ".cache"), GIO_USE_VFS="local",
                        TEST_LAUNCH_RECORD=str(self.root / "launch.json"))

    def run_setup(self, *arguments):
        return subprocess.run(["/usr/bin/python3", str(self.helper), *arguments],
                              env=self.env, cwd=self.root, input="", capture_output=True,
                              text=True, timeout=10)

    def setup(self, *arguments):
        result = self.run_setup(*arguments)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_default_and_custom_data_homes_and_extra_arguments(self):
        for value in (None, "", str(self.root / "custom data")):
            with self.subTest(xdg_data_home=value):
                if value is None:
                    self.env.pop("XDG_DATA_HOME")
                else:
                    self.env["XDG_DATA_HOME"] = value
                destination = Path(value or self.data_home) / "applications/luna-settings.desktop"

                self.setup("--help", "--unknown", "extra")

                self.assertTrue(destination.is_file())
                self.assertEqual(destination.stat().st_mode & 0o777, 0o644)
                self.assertIn("Luna Settings", destination.read_text())
                destination.unlink()
        self.assertEqual(list(self.home.rglob("*.luna-backup*")), [])

    def test_repeat_setup_preserves_unchanged_file_and_repairs_mode(self):
        self.setup()
        previous = self.desktop.stat()
        self.setup()
        self.assertEqual(self.desktop.stat().st_ino, previous.st_ino)
        self.assertEqual(self.desktop.stat().st_mtime_ns, previous.st_mtime_ns)

        self.desktop.chmod(0o600)
        self.setup()
        self.assertEqual(self.desktop.stat().st_mode & 0o777, 0o644)

    def test_gio_launch_preserves_special_checkout_path_and_clears_stale_install_dir(self):
        destination = self.root / 'checkout \'single\' "double" \\backslash $HOME `uname` %f %%'
        self.checkout.rename(destination)
        self.checkout = destination
        self.helper = self.checkout / "scripts/setup/desktop-apps.py"
        self.command = self.checkout / "bin/luna"
        self.env["LUNA_INSTALL_DIR"] = str(self.root / "stale-install")
        self.setup()

        # Gio performs both desktop-entry parsing and field-code expansion. Wait
        # for its harmless fixture process so no real application is ever opened.
        result = subprocess.run(["/usr/bin/python3", "-c", '''
import os, sys
import gi
gi.require_version("GioUnix", "2.0")
from gi.repository import GioUnix, GLib
application = GioUnix.DesktopAppInfo.new_from_filename(sys.argv[1])
assert application is not None
assert application.get_name() == "Luna Settings"
assert application.get_generic_name() == "Settings"
assert application.should_show()
assert set(application.get_categories().split(";")) >= {"Settings", "DesktopSettings"}
pids = []
application.launch_uris_as_manager([], None, GLib.SpawnFlags.DO_NOT_REAP_CHILD,
                                   None, None, lambda app, pid, data: pids.append(pid), None)
assert len(pids) == 1
_, status = os.waitpid(pids[0], 0)
assert os.waitstatus_to_exitcode(status) == 0
''', str(self.desktop)], env=self.env, cwd=self.home, capture_output=True, text=True, timeout=10)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        launched = json.loads(Path(self.env["TEST_LAUNCH_RECORD"]).read_text())
        self.assertEqual(launched["argv"], [str(self.command), "settings"])
        self.assertIsNone(launched["install_dir"])

    def test_missing_or_nonexecutable_sources_preserve_existing_launcher(self):
        self.desktop.parent.mkdir(parents=True)
        self.desktop.write_text("Personal launcher\n")
        for failure in ("command", "mode", "shell"):
            with self.subTest(failure=failure):
                changed = self.shell if failure == "shell" else self.command
                saved = changed.with_name(changed.name + ".saved")
                if failure == "mode":
                    changed.chmod(0o644)
                else:
                    changed.rename(saved)
                try:
                    result = self.run_setup()
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("Cannot install Luna Settings launcher", result.stderr)
                    self.assertEqual(self.desktop.read_text(), "Personal launcher\n")
                finally:
                    if failure == "mode":
                        changed.chmod(0o755)
                    else:
                        saved.rename(changed)

    def test_relative_data_home_is_rejected_before_writing(self):
        self.env["XDG_DATA_HOME"] = "relative/data"

        result = self.run_setup()

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("XDG_DATA_HOME must be an absolute path", result.stderr)
        self.assertFalse((self.root / "relative").exists())
        self.assertFalse(self.data_home.exists())

    def test_checkout_destinations_and_parent_aliases_are_rejected(self):
        alias = self.root / "checkout-alias"
        alias.symlink_to(self.checkout)
        for path in (self.checkout / "data", alias / "data"):
            with self.subTest(path=path):
                self.env["XDG_DATA_HOME"] = str(path)

                result = self.run_setup()

                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("checkout", result.stderr)
                self.assertFalse((self.checkout / "data").exists())

    def test_final_symlinks_are_replaced_without_touching_targets(self):
        self.desktop.parent.mkdir(parents=True)
        foreign = self.root / "foreign.desktop"
        foreign.write_text("Keep this launcher\n")
        for target in (foreign, self.root / "missing.desktop", self.checkout, self.command):
            with self.subTest(target=target):
                self.desktop.symlink_to(target)

                self.setup()

                self.assertFalse(self.desktop.is_symlink())
                self.assertIn("Name=Luna Settings", self.desktop.read_text())
                self.assertEqual(foreign.read_text(), "Keep this launcher\n")
                self.assertTrue(self.checkout.is_dir())
                self.assertTrue(os.access(self.command, os.X_OK))
                self.desktop.unlink()

    def test_directory_conflict_is_preserved(self):
        self.desktop.mkdir(parents=True)
        personal = self.desktop / "personal.txt"
        personal.write_text("Keep me\n")

        result = self.run_setup()

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("must be a file", result.stderr)
        self.assertEqual(personal.read_text(), "Keep me\n")

    def test_parent_file_conflict_is_required(self):
        self.data_home.mkdir(parents=True)
        self.desktop.parent.write_text("Keep me\n")

        result = self.run_setup()

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.desktop.parent.read_text(), "Keep me\n")

    def test_failed_atomic_replace_keeps_existing_launcher_and_cleans_temporary(self):
        self.desktop.parent.mkdir(parents=True)
        self.desktop.write_text("Personal launcher\n")
        spec = importlib.util.spec_from_file_location("luna_desktop_apps", self.helper)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with mock.patch.dict(os.environ, self.env, clear=True), \
                mock.patch.object(module.os, "replace", side_effect=PermissionError("Cannot replace")):
            with self.assertRaises(PermissionError):
                module.install_settings()

        self.assertEqual(self.desktop.read_text(), "Personal launcher\n")
        self.assertEqual(list(self.desktop.parent.iterdir()), [self.desktop])


if __name__ == "__main__":
    unittest.main()
