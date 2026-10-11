"""Exercise the font CLI with real font parsing and isolated package managers."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]


class FontCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna fonts '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.mock = self.root / "bin"
        self.mock.mkdir()
        (self.root / "installed").mkdir()
        self.data = self.root / "data"
        self.state = self.root / "state"
        self.log = self.root / "commands.jsonl"
        self.fc_scan = shutil.which("fc-scan")

        # System fonts supply valid binary fixtures without checking fonts into Git.
        fonts = list(Path("/usr/share/fonts").rglob("*.ttf"))
        if len(fonts) < 2 or not self.fc_scan:
            self.skipTest("Two installed TTF fonts and fc-scan are needed")
        self.fixtures = fonts[:2]
        self.env = dict(os.environ, PATH=str(self.mock) + ":" + os.environ["PATH"],
                        XDG_DATA_HOME=str(self.data), XDG_STATE_HOME=str(self.state),
                        TEST_ROOT=str(self.root), REAL_FC_SCAN=self.fc_scan)

        # Every package mutation is recorded, never sent to the host package manager.
        backend = '''#!/usr/bin/python3
import json, os, pathlib, subprocess, sys
root = pathlib.Path(os.environ["TEST_ROOT"])
tool = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with (root / "commands.jsonl").open("a") as log:
    log.write(json.dumps([tool, *args]) + "\\n")
if tool == "id":
    print("1000")
elif tool == "sudo":
    os.execvp(args[0], args)
elif tool == "fc-cache":
    pass
elif tool == "fc-list":
    print("/mock/package.ttf\\tPackaged Font\\tRegular")
    for path in (root / "data/fonts").rglob("*.ttf"):
        family = subprocess.check_output([os.environ["REAL_FC_SCAN"], "--format", "%{family}", str(path)], text=True)
        print(str(path) + "\\t" + family + "\\tRegular")
elif "-Ss" in args:
    if tool == "pacman":
        print("extra/ttf-test 1.0\\n    A test font\\nextra/unrelated 1.0\\n    Unrelated utility")
    else:
        print("aur/ttf-aur-test 1.0\\n    Another font")
elif "-Ql" in args:
    print("ttf-installed /mock/package.ttf")
elif "-Qlq" in args:
    print("/mock/package.ttf")
elif "-Qm" in args:
    sys.exit(1)
elif "-Q" in args:
    sys.exit(0 if args[-1] == "ttf-installed" or (root / "installed" / args[-1]).exists() else 1)
elif "-S" in args or "-Syu" in args:
    for name in args[args.index("--") + 1:]:
        (root / "installed" / name).touch()
elif "-R" in args:
    for name in args[args.index("--") + 1:]:
        (root / "installed" / name).unlink(missing_ok=True)
else:
    sys.exit(2)
'''
        for name in ("pacman", "yay", "sudo", "id", "fc-cache", "fc-list"):
            path = self.mock / name
            path.write_text(backend)
            path.chmod(0o755)

    def run_cli(self, *args, input=None, success=True):
        result = subprocess.run([str(REPO / "bin/luna"), "font", *map(str, args)],
                                env=self.env, cwd=self.root, input=input,
                                text=True, capture_output=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def calls(self, tool):
        if not self.log.exists():
            return []
        return [entry for line in self.log.read_text().splitlines()
                if (entry := json.loads(line))[0] == tool]

    def managed_files(self):
        return [path for path in (self.data / "fonts/luna").glob("*") if path.is_file()]

    def copy_font(self, path, index=0):
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.fixtures[index], path)
        return path

    def test_search_defaults_to_pacman_and_opt_in_aur(self):
        result = self.run_cli("search", "test")
        self.assertIn("[extra] ttf-test", result.stdout)
        self.assertNotIn("unrelated", result.stdout)
        self.assertEqual(self.calls("yay"), [])
        result = self.run_cli("search", "test", "--aur")
        self.assertLess(result.stdout.index("[extra]"), result.stdout.index("[aur]"))

    def test_batch_packages_skip_force_and_aur(self):
        self.run_cli("install", "ttf-one", "ttf-two")
        installs = [call for call in self.calls("pacman") if "-Syu" in call]
        self.assertEqual(installs[-1][-2:], ["ttf-one", "ttf-two"])
        self.run_cli("install", "ttf-one")
        self.assertEqual(len([call for call in self.calls("pacman") if "-Syu" in call]), 1)
        self.run_cli("install", "ttf-one", "--force")
        self.assertNotIn("--needed", self.calls("pacman")[-2])
        self.run_cli("install", "ttf-aur-one", "ttf-aur-two", "--aur")
        self.assertIn("--aur", self.calls("yay")[-1])

    def test_local_folder_recursion_batch_and_duplicates(self):
        folder = self.root / "family folder"
        self.copy_font(folder / "regular.ttf")
        self.copy_font(folder / "nested/bold.ttf", 1)
        (folder / "notes.txt").write_text("ignore this")
        self.run_cli("install", folder)
        self.assertEqual(len(self.managed_files()), 1)
        self.run_cli("install", "-r", folder)
        self.assertEqual(len(self.managed_files()), 2)
        result = self.run_cli("install", folder / "regular.ttf", folder / "nested/bold.ttf")
        self.assertEqual(result.stdout.count("Already installed [local]"), 2)
        self.assertEqual(len(self.calls("fc-cache")), 3)

    def test_mixed_install_and_invalid_input_preflight(self):
        valid = self.copy_font(self.root / "font's regular.ttf")
        invalid = self.root / "invalid.ttf"
        invalid.write_text("not a font")
        self.run_cli("install", "ttf-test", valid, invalid, success=False)
        self.assertFalse((self.root / "installed" / "ttf-test").exists())
        self.assertEqual(self.managed_files(), [])
        self.run_cli("install", "ttf-test", valid)
        self.assertTrue((self.root / "installed" / "ttf-test").exists())
        self.assertEqual(len(self.managed_files()), 1)

    def test_list_sources_and_local_batch_removal(self):
        folder = self.root / "bundle"
        self.copy_font(folder / "one.ttf")
        self.copy_font(folder / "two.ttf", 1)
        self.run_cli("install", folder)
        result = self.run_cli("list")
        self.assertIn("pacman:ttf-installed", result.stdout)
        self.assertIn("local\t", result.stdout)
        self.run_cli("remove", "one.ttf", "two.ttf", input="n\n")
        self.assertEqual(len(self.managed_files()), 2)
        self.run_cli("remove", "one.ttf", "two.ttf", input="yes\n")
        self.assertEqual(len(self.managed_files()), 0)

    def test_manual_fonts_and_ambiguous_removal(self):
        first = self.copy_font(self.data / "fonts/first/shared.ttf")
        second = self.copy_font(self.data / "fonts/second/shared.ttf", 1)
        result = self.run_cli("remove", "shared.ttf", input="y\n", success=False)
        self.assertIn("Ambiguous", result.stderr)
        self.run_cli("remove", first, "unknown", input="y\n", success=False)
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())
        self.run_cli("remove", first, input="y\n")
        self.assertFalse(first.exists())
        self.assertTrue(second.exists())

    def test_filename_collision_force_and_no_records(self):
        first = self.copy_font(self.root / "first/shared.ttf")
        second = self.copy_font(self.root / "second/shared.ttf", 1)
        self.run_cli("install", first, second, success=False)
        self.assertEqual(self.managed_files(), [])
        self.run_cli("install", first)
        installed = self.managed_files()[0]
        original = installed.read_bytes()
        self.run_cli("install", second, success=False)
        self.assertEqual(installed.read_bytes(), original)
        self.run_cli("install", second, "--force")
        self.assertEqual(installed.read_bytes(), second.read_bytes())
        self.assertFalse(self.state.exists())

    def test_package_and_local_removal_in_one_batch(self):
        self.run_cli("install", self.copy_font(self.root / "local.ttf"))
        self.run_cli("remove", "ttf-installed", "local.ttf", input="y\n")
        self.assertEqual(self.managed_files(), [])
        self.assertTrue(any("-R" in call for call in self.calls("pacman")))


if __name__ == "__main__":
    unittest.main()
