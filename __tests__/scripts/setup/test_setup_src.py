"""Exercise source links in temporary homes without changing the running desktop."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]


class SetupSourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna source '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.checkout = self.root / "checkout"
        self.source_target = self.home / ".local/src"
        # Linking whole source directories needs only Bash and coreutils.
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for name in ("bash", "readlink", "mkdir", "rm", "ln"):
            (self.bin / name).symlink_to(shutil.which(name))
        self.env = dict(os.environ, HOME=str(self.home), PATH=str(self.bin))

        # Copy only the deployment files; source packages need no running apps.
        for name in ("scripts/setup/12-link-sources.sh", "lib/common.sh"):
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
        return subprocess.run(["bash", str(self.checkout / "scripts/setup/12-link-sources.sh"), *arguments],
                              env=self.env, cwd=self.root, input="", capture_output=True,
                              text=True, timeout=10)

    def assert_links(self):
        for name in self.packages:
            target = self.source_target / name
            self.assertTrue(target.is_symlink(), str(target))
            self.assertFalse(target.readlink().is_absolute())
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
        self.assertTrue((self.checkout / "scripts/setup/12-link-sources.sh").is_file())
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

    def test_entrypoint_symlink_resolves_the_checkout_from_another_directory(self):
        entrypoint = self.root / "link-sources.sh"
        entrypoint.symlink_to(self.checkout / "scripts/setup/12-link-sources.sh")

        result = subprocess.run(["bash", str(entrypoint)], env=self.env, cwd=self.home,
                                input="", capture_output=True, text=True, timeout=10)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_links()

    def test_missing_sources_fail_before_changing_existing_links(self):
        shutil.rmtree(self.checkout / "src")
        self.source_target.mkdir(parents=True)
        personal = self.source_target / self.packages[0]
        personal.write_text("Keep me\n")

        result = self.run_setup()

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("source directory is missing", result.stderr)
        self.assertEqual(personal.read_text(), "Keep me\n")

    def test_link_creation_failure_is_required(self):
        linker = self.bin / "ln"
        linker.unlink()
        linker.write_text("#!/bin/sh\nexit 73\n")
        linker.chmod(0o755)

        result = self.run_setup()

        self.assertEqual(result.returncode, 73, result.stdout + result.stderr)
        self.assertNotIn("Linked Luna source directories", result.stdout)


if __name__ == "__main__":
    unittest.main()
