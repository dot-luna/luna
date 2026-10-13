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
                        XDG_DATA_HOME=str(self.data), XDG_STATE_HOME=str(self.state), XDG_CONFIG_HOME=str(self.root / "config"),
                        TEST_ROOT=str(self.root), REAL_FC_SCAN=self.fc_scan)

        # Every package mutation is recorded, never sent to the host package manager.
        backend = '''#!/usr/bin/python3
import json, os, pathlib, subprocess, sys
root = pathlib.Path(os.environ["TEST_ROOT"])
tool = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with (root / "commands.jsonl").open("a") as log:
    log.write(json.dumps([tool, *args]) + "\\n")
if tool == "realpath":
    os.execv("/usr/bin/realpath", ["/usr/bin/realpath", *args])
elif tool == "id":
    print("1000")
elif tool == "sudo":
    os.execvp(args[0], args)
elif tool == "fc-cache":
    pass
elif tool == "qs":
    pass
elif tool == "fc-list" and "%{family[0]}" in " ".join(args):
    print("Test UI\\t")
    print("Test Mono\\t100")
    print("Test UI\\t")
elif tool == "fc-list":
    print("/mock/package.ttf\\tPackaged Font\\tRegular")
    for path in (root / "data/fonts").rglob("*.ttf"):
        family = subprocess.check_output([os.environ["REAL_FC_SCAN"], "--format", "%{family}", str(path)], text=True)
        print(str(path) + "\\t" + family + "\\tRegular")
elif "-Ss" in args:
    if os.environ.get("TEST_EMPTY_SEARCH"):
        sys.exit(1)
    if tool != "pacman" and os.environ.get("TEST_AUR_FAILURE"):
        sys.exit(2)
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
        for name in ("pacman", "yay", "sudo", "id", "fc-cache", "fc-list", "realpath", "qs"):
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

    def test_json_search_preserves_sources_and_empty_results(self):
        result = json.loads(self.run_cli("search", "test", "--aur", "--json").stdout)
        self.assertEqual([row["repository"] for row in result["results"]], ["extra", "aur"])
        self.assertEqual(result["results"][0]["name"], "ttf-test")
        self.assertFalse(result["results"][0]["installed"])
        self.assertEqual(result["warning"], "")
        self.env["TEST_EMPTY_SEARCH"] = "1"
        result = json.loads(self.run_cli("search", "missing", "--aur", "--json").stdout)
        self.assertEqual(result["results"], [])

    def test_json_search_keeps_repository_results_when_aur_fails(self):
        self.env["TEST_AUR_FAILURE"] = "1"
        result = json.loads(self.run_cli("search", "test", "--aur", "--json").stdout)
        self.assertEqual([row["repository"] for row in result["results"]], ["extra"])
        self.assertIn("AUR search unavailable", result["warning"])

    def test_menu_install_confirms_and_waits_without_changing_cli(self):
        for package, source in [("ttf-menu", "extra"), ("ttf-menu-aur", "aur")]:
            result = subprocess.run(
                ["lua", "-E", str(REPO / "src/launcher/install-font.lua"), package, source],
                env=self.env, input="\n", text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Installation complete.", result.stdout)
            self.assertIn("Press Enter to close", result.stdout)
        self.assertTrue(any("--noconfirm" in call for call in self.calls("pacman")))
        self.assertIn("--noconfirm", self.calls("yay")[-1])
        self.assertIn("--answerdiff", self.calls("yay")[-1])
        self.run_cli("install", "ttf-interactive")
        last_install = [call for call in self.calls("pacman") if "-Syu" in call][-1]
        self.assertNotIn("--noconfirm", last_install)

    def test_menu_failure_reports_error_and_waits(self):
        result = subprocess.run(
            ["lua", "-E", str(REPO / "src/launcher/install-font.lua"), "../bad", "extra"],
            env=self.env, input="\n", text=True, capture_output=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Installation failed", result.stderr)
        self.assertIn("Press Enter to close", result.stdout)
        self.assertEqual(self.calls("pacman"), [])

    def test_removal_list_json_and_menu_local_removal(self):
        self.run_cli("install", self.copy_font(self.root / "menu-local.ttf"))
        local_path = self.managed_files()[0]
        rows = json.loads(self.run_cli("list", "--json").stdout)["results"]
        package = next(row for row in rows if row["target"] == "ttf-installed")
        self.assertEqual(package["repository"], "pacman")
        local = next(row for row in rows if row["target"] == str(local_path))
        self.assertEqual(local["repository"], "local")
        self.assertNotIn("/mock/package.ttf", [row["target"] for row in rows])
        result = subprocess.run(
            ["lua", "-E", str(REPO / "src/launcher/remove-font.lua"), str(local_path)],
            env=self.env, input="\n", text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Removal complete.", result.stdout)
        self.assertIn("Press Enter to close", result.stdout)
        self.assertNotIn("Remove these fonts?", result.stdout)
        self.assertFalse(local_path.exists())

    def test_menu_package_removal_auto_confirms_and_reports_failure(self):
        result = subprocess.run(
            ["lua", "-E", str(REPO / "src/launcher/remove-font.lua"), "ttf-installed"],
            env=self.env, input="\n", text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        removal = next(call for call in self.calls("pacman") if "-R" in call)
        self.assertIn("--noconfirm", removal)
        self.assertNotIn("-Rns", removal)
        result = subprocess.run(
            ["lua", "-E", str(REPO / "src/launcher/remove-font.lua"), "/etc/does-not-exist"],
            env=self.env, input="\n", text=True, capture_output=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Removal failed:", result.stderr)
        self.assertIn("Press Enter to close", result.stdout)

    def test_menu_batch_mixed_install_and_preflight(self):
        adapter = str(REPO / "src/launcher/install-font.lua")
        result = subprocess.run(
            ["lua", "-E", adapter, "ttf-repo", "extra", "ttf-aur", "aur", "ttf-second", "extra"],
            env=self.env, input="\n", text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        installs = [call for call in self.calls("pacman") if "-Syu" in call]
        self.assertEqual(len(installs), 1)
        self.assertEqual(installs[0][-2:], ["ttf-repo", "ttf-second"])
        self.assertEqual(self.calls("yay")[-1][-1], "ttf-aur")
        result = subprocess.run(
            ["lua", "-E", adapter, "ttf-not-installed", "extra", "../bad", "aur"],
            env=self.env, input="\n", text=True, capture_output=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "installed/ttf-not-installed").exists())

    def test_menu_batch_removal_package_and_local(self):
        self.run_cli("install", self.copy_font(self.root / "batch.ttf"))
        local_path = self.managed_files()[0]
        result = subprocess.run(
            ["lua", "-E", str(REPO / "src/launcher/remove-font.lua"), "ttf-installed", str(local_path)],
            env=self.env, input="\n", text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(local_path.exists())
        self.assertTrue(any("-R" in call and "ttf-installed" in call for call in self.calls("pacman")))

    def test_local_families_group_within_folder_and_remove_exact_files(self):
        first = self.copy_font(self.data / "fonts/family/regular.ttf")
        second = self.copy_font(self.data / "fonts/family/bold.ttf")
        separate = self.copy_font(self.data / "fonts/another-copy/regular.ttf")
        rows = json.loads(self.run_cli("list", "--json").stdout)["results"]
        local = [row for row in rows if row["repository"] == "local"]
        self.assertEqual(len(local), 2)
        grouped = next(row for row in local if str(first) in row["targets"])
        self.assertEqual(set(grouped["targets"]), {str(first), str(second)})
        self.assertEqual(grouped["fileCount"], 2)
        other = next(row for row in local if str(separate) in row["targets"])
        self.assertEqual(grouped["name"], other["name"])
        self.assertNotEqual(grouped["selectionKey"], other["selectionKey"])
        result = subprocess.run(
            ["lua", "-E", str(REPO / "src/launcher/remove-font.lua"), *grouped["targets"]],
            env=self.env, input="\n", text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(first.exists())
        self.assertFalse(second.exists())
        self.assertTrue(separate.exists())

    def test_large_local_removal_checks_only_matching_paths(self):
        selected = [self.copy_font(self.data / f"fonts/selected/{index}.ttf") for index in range(24)]
        untouched = [self.copy_font(self.data / f"fonts/other/{index}.ttf") for index in range(24)]
        result = subprocess.run(
            ["lua", "-E", str(REPO / "src/launcher/remove-font.lua"), *map(str, selected)],
            env=self.env, input="\n", text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        checks = [call for call in self.calls("realpath") if "-e" in call]
        # One preflight and one fresh safety check per selected file; no unrelated files.
        self.assertEqual(len(checks), len(selected) * 2)
        self.assertEqual({call[-1] for call in checks}, set(map(str, selected)))
        self.assertTrue(all(path.exists() for path in untouched))
        self.assertFalse(any(path.exists() for path in selected))
        self.assertIn("Checking selected fonts", result.stdout)
        self.assertIn("Refreshing font cache", result.stdout)
        self.assertIn("Removal complete.", result.stdout)

    def test_font_preferences_validate_roles_and_persist(self):
        ui = json.loads(self.run_cli("families", "ui").stdout)["results"]
        self.assertEqual(len(ui), 2)
        mono = json.loads(self.run_cli("families", "mono").stdout)["results"]
        self.assertEqual([entry["family"] for entry in mono], ["Test Mono", "Test UI"])
        self.run_cli("set", "mono", "Missing Font", success=False)
        self.assertFalse((self.root / "config/luna/fonts.json").exists())
        self.run_cli("set", "mono", "Test UI")
        self.run_cli("set", "ui", "Test UI")
        self.run_cli("set", "mono", "Test Mono")
        expected = {"ui": "Test UI", "mono": "Test Mono"}
        self.assertEqual(json.loads((self.root / "config/luna/fonts.json").read_text()), expected)
        self.assertEqual(json.loads((self.root / "config/luna/theme.json").read_text())["fonts"], expected)
        listed = json.loads(self.run_cli("families", "ui").stdout)["results"]
        self.assertTrue(next(entry for entry in listed if entry["family"] == "Test UI")["current"])
        script = "local r=dofile(arg[1]..'/lib/theme/resolved.lua')(arg[1]); print(r.encode(r.resolve({fonts={ui='Theme Font',mono='Other'}})))"
        result = subprocess.run(["lua", "-E", "-", str(REPO)], input=script, env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["fonts"], expected)

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
