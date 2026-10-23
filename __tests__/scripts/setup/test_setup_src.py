"""Exercise real Stow in temporary homes without changing the running desktop."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]


@unittest.skipUnless(shutil.which("stow"), "GNU Stow is required")
class SetupSourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna stow '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.checkout = self.root / "checkout"
        self.source_target = self.home / ".local/src"
        self.env = dict(os.environ, HOME=str(self.home))

        # Copy only the deployment files; source packages need no running apps.
        for name in ("scripts/setup/src.sh", "lib/common.sh"):
            destination = self.checkout / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, destination)
        self.packages = sorted(path.name for path in (REPO / "src").iterdir() if path.is_dir())
        for name in self.packages:
            directory = self.checkout / "src" / name
            directory.mkdir(parents=True)
            (directory / "entry.lua").write_text("-- Source fixture\n")

    def setup(self, *arguments):
        # Closed stdin verifies that source deployment needs no confirmation.
        result = self.run_setup(*arguments)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def run_setup(self, *arguments):
        return subprocess.run(["bash", str(self.checkout / "scripts/setup/src.sh"), *arguments],
                              env=self.env, cwd=self.root, input="", capture_output=True,
                              text=True, timeout=10)

    def assert_links(self):
        for name in self.packages:
            target = self.source_target / name
            self.assertTrue(target.is_symlink(), str(target))
            self.assertEqual(target.resolve(), self.checkout / "src" / name)

    def test_source_directories_are_linked_on_repeat_runs(self):
        self.source_target.mkdir(parents=True)
        personal = self.source_target / "personal-project"
        personal.mkdir()
        for _ in range(2):
            self.setup()
            self.assert_links()
        self.assertTrue(personal.is_dir())
        self.assertEqual(list(self.home.rglob("*.luna-backup*")), [])
        self.assertEqual((self.source_target / "luna-cli/../../lib/common.sh").resolve(),
                         self.checkout / "lib/common.sh")

    def test_checkout_can_live_inside_local_src(self):
        self.source_target.mkdir(parents=True)
        destination = self.source_target / "luna"
        self.checkout.rename(destination)
        self.checkout = destination
        self.setup()
        self.assert_links()

    def test_checkout_inside_source_conflict_is_preserved_before_any_replacement(self):
        self.source_target.mkdir(parents=True)
        earlier_conflict = self.source_target / self.packages[0]
        earlier_conflict.write_text("Personal project\n")
        destination = self.source_target / self.packages[-1] / "checkout"
        destination.parent.mkdir()
        self.checkout.rename(destination)
        self.checkout = destination

        result = self.run_setup()

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("checkout", result.stderr)
        self.assertTrue((self.checkout / "scripts/setup/src.sh").is_file())
        self.assertEqual(earlier_conflict.read_text(), "Personal project\n")
        self.assertEqual(list(self.home.rglob("*.luna-backup*")), [])

    def test_source_target_aliasing_checkout_source_is_preserved(self):
        self.source_target.parent.mkdir(parents=True)
        self.source_target.symlink_to(self.checkout / "src")

        result = self.run_setup()

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("checkout", result.stderr)
        for name in self.packages:
            package = self.checkout / "src" / name
            self.assertFalse(package.is_symlink())
            self.assertEqual((package / "entry.lua").read_text(), "-- Source fixture\n")

    def test_source_conflicts_are_replaced_without_new_backups(self):
        target = self.source_target / "luna-cli"
        self.assert_conflict_replacement(target, self.checkout / "src/luna-cli")

    def assert_conflict_replacement(self, target, source):
        target.parent.mkdir(parents=True)
        foreign = self.root / "foreign"
        foreign.mkdir()
        foreign_file = foreign / "personal.lua"
        foreign_file.write_text("-- Foreign project\n")

        # Existing user-created backups must not be overwritten or cleaned up.
        prior_backup = target.with_name(target.name + ".luna-backup")
        prior_backup.symlink_to("prior-missing-target")
        for kind in ("file", "directory", "foreign-link", "dangling-link"):
            with self.subTest(kind=kind):
                if target.is_symlink():
                    target.unlink()
                if kind == "file":
                    target.write_text("-- Keep this file\n")
                elif kind == "directory":
                    target.mkdir()
                    (target / "personal.lua").write_text("-- Keep this project\n")
                else:
                    destination = foreign if kind == "foreign-link" else self.root / "missing"
                    target.symlink_to(os.path.relpath(destination, target.parent))

                self.setup()
                self.assertTrue(target.is_symlink())
                self.assertEqual(target.resolve(), source)
                self.assertEqual(list(target.parent.glob(target.name + ".luna-backup*")), [prior_backup])
                self.assertEqual(prior_backup.readlink(), Path("prior-missing-target"))
                self.assertEqual(foreign_file.read_text(), "-- Foreign project\n")

        self.setup()
        self.assertEqual(list(target.parent.glob(target.name + ".luna-backup*")), [prior_backup])
        self.assertEqual(prior_backup.readlink(), Path("prior-missing-target"))

    def test_source_arguments_are_ignored_during_normal_deployment(self):
        self.setup("--help", "-h", "--force", "--unknown", "main")
        self.assert_links()
        self.assertEqual(list(self.home.rglob("*.luna-backup*")), [])


if __name__ == "__main__":
    unittest.main()
