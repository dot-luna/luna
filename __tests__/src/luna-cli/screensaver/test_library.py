"""Exercise named shell commands with a private library and recording-only controller."""

import importlib.util
import json
from pathlib import Path
import subprocess
import tomllib
import unittest


REPO = Path(__file__).resolve().parents[4]
SPEC = importlib.util.spec_from_file_location(
    "screensaver_library_fixture", REPO / "__tests__/src/screensaver/src/test_runtime.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
ScreensaverFixture = MODULE.ScreensaverFixture
SHELL = "import Quickshell\nShellRoot {}\n"


class ScreensaverLibraryCliTests(ScreensaverFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.library = self.root / "data/luna/screensavers"
        self.package = self.root / "source clock"
        self.package.mkdir()
        (self.package / "shell.qml").write_text(SHELL)
        (self.package / "assets").mkdir()
        (self.package / "assets/stars.txt").write_text("stars")
        (self.package / ".git").mkdir()
        (self.package / ".git/config").write_text("not part of the renderer")
        self.single = self.root / "aurora.qml"
        self.single.write_text(SHELL)

    def command(self, *args, ok=True, answer=""):
        result = subprocess.run(
            [str(REPO / "bin/luna"), "screensaver", *map(str, args)],
            cwd=self.root, env=self.env, input=answer, text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return result

    def test_install_copies_packages_and_single_files_without_selecting_or_launching(self):
        result = self.command("install", self.package, "--name", "my-clock")
        self.assertEqual(result.stdout, "Screensaver installed: my-clock\n")
        installed = self.library / "my-clock"
        self.assertEqual((installed / "shell.qml").read_text(), SHELL)
        self.assertEqual((installed / "assets/stars.txt").read_text(), "stars")
        self.assertFalse((installed / ".git").exists())
        self.command("install", self.single)
        self.assertEqual([path.name for path in (self.library / "aurora").iterdir()], ["shell.qml"])
        self.assertFalse(self.config.exists())
        self.assertFalse(self.starts())
        self.assertTrue((self.package / "shell.qml").exists())

    def test_list_and_directory_include_bundled_shells_without_starting(self):
        self.assertEqual(self.command("dir").stdout, str(self.library) + "\n")
        self.assertFalse(self.library.exists())
        self.assertEqual(set(self.command("list").stdout.splitlines()),
                         {"* clock (bundled)", "  blank (bundled)", "  orbit (bundled)"})
        self.command("install", self.single)
        self.assertIn("  aurora\n", self.command("list").stdout)
        self.assertFalse(self.starts())

    def test_set_installed_and_bundled_shells_preserves_awake_and_hidden_state(self):
        self.command("install", self.single)
        result = self.cli("awake", "on")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.command("set", "aurora").stdout, "Screensaver set: aurora\n")
        self.assertEqual(tomllib.loads(self.config.read_text())["renderer"]["shell"],
                         str(self.library / "aurora/shell.qml"))
        state = json.loads((self.root / "state").read_text())
        self.assertTrue(state["stayAwake"])
        self.assertFalse(state["active"])
        self.assertIn("* aurora\n", self.command("list").stdout)
        self.command("set", "blank")
        self.assertIn("* blank (bundled)", self.command("list").stdout)
        self.command("set", "orbit")
        self.assertIn("* orbit (bundled)", self.command("list").stdout)
        self.command("set", "clock")
        self.assertEqual(tomllib.loads(self.config.read_text())["renderer"]["shell"], "")
        self.assertEqual(len(self.starts()), 1)
        self.assertFalse(any(call[-1] in ("show", "shutdown") for call in self.calls()))

    def test_set_path_starts_hidden_and_failed_apply_restores_selection(self):
        self.command("set", self.single)
        self.assertEqual(tomllib.loads(self.config.read_text())["renderer"]["shell"], str(self.single))
        self.assertFalse(json.loads((self.root / "state").read_text())["active"])
        self.env["TEST_FAIL_METHOD"] = "configure"
        result = self.command("set", "blank", ok=False)
        self.assertEqual(result.stdout, "")
        self.assertEqual(tomllib.loads(self.config.read_text())["renderer"]["shell"], str(self.single))

    def test_remove_requires_confirmation_and_yes_supports_multiple_names(self):
        self.command("install", self.package, "--name", "my-clock")
        self.command("install", self.single)
        for answer in ("", "n\n"):
            result = self.command("remove", "my-clock", answer=answer)
            self.assertIn("  my-clock\n", result.stdout)
            self.assertIn("Removal cancelled.", result.stdout)
            self.assertTrue((self.library / "my-clock").exists())
        result = self.command("remove", "my-clock", "missing", ok=False, answer="yes\n")
        self.assertNotIn("Continue?", result.stdout)
        self.assertTrue((self.library / "my-clock").exists())
        result = self.command("remove", "my-clock", "aurora", "-y")
        self.assertNotIn("Continue?", result.stdout)
        self.assertIn("Screensaver removed: my-clock", result.stdout)
        self.assertIn("Screensaver removed: aurora", result.stdout)
        self.assertFalse((self.library / "my-clock").exists())
        self.assertFalse((self.library / "aurora").exists())
        self.assertTrue((self.package / "shell.qml").exists())
        self.assertTrue(self.single.exists())

    def test_interactive_yes_removes_and_selected_or_bundled_shells_are_protected(self):
        self.command("install", self.single)
        self.command("set", "aurora")
        result = self.command("remove", "aurora", "--yes", ok=False)
        self.assertNotIn("Continue?", result.stdout)
        self.assertTrue((self.library / "aurora").exists())
        for name in ("clock", "blank", "orbit"):
            self.command("remove", name, "-y", ok=False)
            self.command("install", self.single, "--name", name, "--force", ok=False)
        self.command("set", "clock")
        self.assertIn("Screensaver removed: aurora",
                      self.command("remove", "aurora", answer="yes\n").stdout)
        self.assertFalse((self.library / "aurora").exists())

    def test_force_replaces_only_inactive_package(self):
        self.command("install", self.single)
        self.single.write_text(SHELL + "// Updated visual\n")
        self.command("install", self.single, ok=False)
        self.assertEqual((self.library / "aurora/shell.qml").read_text(), SHELL)
        self.command("install", self.single, "--force")
        updated = (self.library / "aurora/shell.qml").read_text()
        self.assertIn("Updated visual", updated)
        self.command("set", "aurora")
        self.single.write_text(SHELL + "// Unapplied visual\n")
        self.command("install", self.single, "--force", ok=False)
        self.assertEqual((self.library / "aurora/shell.qml").read_text(), updated)

    def test_missing_arguments_do_not_install_select_or_remove(self):
        for args in (("install",), ("set",), ("remove",), ("install", self.single, "--name")):
            self.command(*args, ok=False)
        self.assertFalse(self.config.exists())
        self.assertFalse(self.library.exists())
        self.assertFalse(self.calls())

    def test_invalid_sources_and_names_fail_without_success_output(self):
        empty = self.root / "empty"
        empty.mkdir()
        for args in ((empty,), (self.root / "missing.qml",),
                     (self.single, "--name", "../escape"),
                     (self.single, "--name", "bad name")):
            result = self.command("install", *args, ok=False)
            self.assertEqual(result.stdout, "")
        self.assertFalse(self.library.exists())
        self.assertFalse(self.config.exists())
        self.assertFalse(self.starts())


if __name__ == "__main__":
    unittest.main()
