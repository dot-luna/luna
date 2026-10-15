"""Exercise real Stow in temporary homes without changing the running desktop."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("stow"), "GNU Stow is required")
class SetupConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna stow '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.checkout = self.root / "checkout"
        self.source_target = self.home / ".local/src"
        self.config = self.home / ".config"
        self.env = dict(os.environ, HOME=str(self.home), XDG_CONFIG_HOME=str(self.config))

        # Copy only the deployment files; source packages need no running apps.
        for name in ("scripts/setup/config.sh", "scripts/setup/src.sh", "lib/common.sh",
                     "config/hypr/.config/hypr/hyprland.lua"):
            destination = self.checkout / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, destination)
        self.packages = sorted(path.name for path in (REPO / "src").iterdir() if path.is_dir())
        for name in self.packages:
            directory = self.checkout / "src" / name
            directory.mkdir(parents=True)
            (directory / "entry.lua").write_text("-- Source fixture\n")

    def setup(self, step, *arguments):
        # Closed stdin verifies that config/source deployment needs no confirmation.
        result = subprocess.run(["bash", str(self.checkout / f"scripts/setup/{step}.sh"), *arguments],
                                env=self.env, cwd=self.root, input="", capture_output=True,
                                text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def setup_both(self, *arguments):
        self.setup("config", *arguments)
        self.setup("src", *arguments)

    def assert_links(self):
        for name in self.packages:
            target = self.source_target / name
            self.assertTrue(target.is_symlink(), str(target))
            self.assertEqual(target.resolve(), self.checkout / "src" / name)
        entry = Path(self.env["XDG_CONFIG_HOME"]) / "hypr/hyprland.lua"
        self.assertTrue(entry.is_symlink())
        self.assertEqual(entry.resolve(), self.checkout / "config/hypr/.config/hypr/hyprland.lua")

    def test_source_directories_and_config_are_linked_on_repeat_runs(self):
        self.source_target.mkdir(parents=True)
        personal = self.source_target / "personal-project"
        personal.mkdir()
        for _ in range(2):
            self.setup_both()
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
        self.setup_both()
        self.assert_links()

    def test_custom_config_location_preserves_other_hyprland_files(self):
        custom = self.root / "custom config"
        self.env["XDG_CONFIG_HOME"] = str(custom)
        (custom / "hypr").mkdir(parents=True)
        personal = custom / "hypr/personal.lua"
        personal.write_text("-- Personal config\n")
        self.setup_both()
        self.assert_links()
        self.assertEqual(personal.read_text(), "-- Personal config\n")

    def test_config_and_source_steps_are_independent(self):
        self.setup("config")
        self.assertTrue((self.config / "hypr/hyprland.lua").is_symlink())
        self.assertFalse(self.source_target.exists())
        self.setup("src")
        self.assert_links()

    def test_source_conflicts_are_backed_up_without_prompts(self):
        target = self.source_target / "luna-cli"
        self.assert_conflict_backups("src", target, self.checkout / "src/luna-cli")

    def test_config_conflicts_are_backed_up_without_prompts(self):
        entry = self.config / "hypr/hyprland.lua"
        self.assert_conflict_backups("config", entry, self.checkout / "config/hypr/.config/hypr/hyprland.lua")

    def assert_conflict_backups(self, step, target, source):
        target.parent.mkdir(parents=True)
        foreign = self.root / "foreign"
        foreign.mkdir()
        foreign_file = foreign / "personal.lua"
        foreign_file.write_text("-- Foreign project\n")

        # Keep a dangling prior backup to ensure suffix allocation uses lexists.
        first_backup = target.with_name(target.name + ".luna-backup")
        first_backup.symlink_to("prior-missing-target")
        for index, kind in enumerate(("file", "directory", "foreign-link", "dangling-link"), start=1):
            with self.subTest(step=step, kind=kind):
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
                    old_link = target.readlink()

                # --force remains accepted, but ordinary runs also preserve conflicts.
                self.setup(step, *(("--force",) if index % 2 == 0 else ()))
                backup = target.with_name(target.name + f".luna-backup.{index}")
                self.assertTrue(target.is_symlink())
                self.assertEqual(target.resolve(), source)
                if kind == "file":
                    self.assertEqual(backup.read_text(), "-- Keep this file\n")
                elif kind == "directory":
                    self.assertFalse(backup.is_symlink())
                    self.assertEqual((backup / "personal.lua").read_text(), "-- Keep this project\n")
                else:
                    self.assertTrue(backup.is_symlink())
                    self.assertEqual(backup.readlink(), old_link)
                self.assertEqual(first_backup.readlink(), Path("prior-missing-target"))
                self.assertEqual(foreign_file.read_text(), "-- Foreign project\n")

        backups = sorted(target.parent.glob(target.name + ".luna-backup*"))
        self.setup(step)
        self.assertEqual(sorted(target.parent.glob(target.name + ".luna-backup*")), backups)
        self.assertEqual(target.with_name(target.name + ".luna-backup.1").read_text(), "-- Keep this file\n")

    def test_foreign_hyprland_directory_link_is_backed_up_as_a_link(self):
        foreign = self.root / "foreign hypr"
        foreign.mkdir()
        (foreign / "hyprland.lua").write_text("-- Foreign configuration\n")
        (foreign / "personal.lua").write_text("-- Personal include\n")
        self.config.mkdir()
        hypr = self.config / "hypr"
        hypr.symlink_to(os.path.relpath(foreign, self.config))
        original_link = hypr.readlink()

        self.setup("config")
        backup = self.config / "hypr.luna-backup"
        self.assertTrue(backup.is_symlink())
        self.assertEqual(backup.readlink(), original_link)
        self.assertFalse(hypr.is_symlink())
        self.assertTrue((hypr / "hyprland.lua").is_symlink())
        self.assertEqual((foreign / "hyprland.lua").read_text(), "-- Foreign configuration\n")
        self.assertEqual((foreign / "personal.lua").read_text(), "-- Personal include\n")


if __name__ == "__main__":
    unittest.main()
