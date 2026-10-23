"""Exercise final package cleanup using fake pacman and sudo only."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]


@unittest.skipUnless(Path("/usr/bin/lua").is_file(), "Reading the package manifest requires Lua")
class SetupCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna cleanup '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.checkout = self.root / "checkout"
        for name in ("scripts/setup/cleanup.sh", "lib/common.sh", "packages/packages.lua"):
            target = self.checkout / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, target)

        # Keep every package operation inside the fixture, including calls via sudo.
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for name in ("bash", "readlink", "dirname"):
            (self.bin / name).symlink_to(shutil.which(name))
        backend = f"#!{sys.executable}\n" + '''
import json, os, pathlib, sys
root = pathlib.Path(os.environ["TEST_PACKAGE_ROOT"])
tool = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with (root / "calls.jsonl").open("a") as output:
    output.write(json.dumps([tool, *args]) + "\\n")
if tool == "sudo":
    assert args[0] == "pacman", args
    os.execv(str(root / "bin/pacman"), ["pacman", *args[1:]])
state_file = root / "packages.json"
state = json.loads(state_file.read_text())
if args[:2] == ["-Qq", "--"]:
    assert len(args) == 3, args
    sys.exit(0 if args[2] in state else 1)
if args == ["-Rs", "--print", "--print-format", "%n", "--", "dolphin"]:
    assert "nautilus" in state, "Removal planning ran without Nautilus installed"
    if os.environ.get("TEST_PLAN_FAIL"):
        sys.exit(22)
    print(os.environ.get("TEST_CANDIDATES", "dolphin\\nunused-kde-library"))
elif args == ["-Qqe"]:
    if os.environ.get("TEST_EXPLICIT_FAIL"):
        sys.exit(23)
    print(os.environ.get("TEST_EXPLICIT", "dolphin\\npersonal-editor"))
elif args[:3] == ["-R", "--noconfirm", "--"]:
    assert "nautilus" in state, "Removal ran without Nautilus installed"
    selected = args[3:]
    assert selected and selected[0] == "dolphin", args
    if os.environ.get("TEST_REMOVE_FAIL") or (len(selected) > 1 and os.environ.get("TEST_SHARED_DEPENDENCY")):
        sys.exit(24)
    state_file.write_text(json.dumps([name for name in state if name not in selected]))
else:
    sys.exit("Unexpected package operation: " + repr(args))
'''
        for name in ("pacman", "sudo"):
            target = self.bin / name
            target.write_text(backend)
            target.chmod(0o755)
        self.state = self.root / "packages.json"
        self.state.write_text(json.dumps(["nautilus", "dolphin", "unused-kde-library"]))
        self.log = self.root / "calls.jsonl"
        self.env = dict(os.environ, HOME=str(self.home), PATH=str(self.bin),
                        TEST_PACKAGE_ROOT=str(self.root), BASH_ENV="", NO_COLOR="1")
        for name in ("TEST_PLAN_FAIL", "TEST_CANDIDATES", "TEST_EXPLICIT", "TEST_EXPLICIT_FAIL",
                     "TEST_REMOVE_FAIL", "TEST_SHARED_DEPENDENCY"):
            self.env.pop(name, None)

    def setup(self, *arguments, entry=None):
        script = entry or self.checkout / "scripts/setup/cleanup.sh"
        return subprocess.run([str(self.bin / "bash"), str(script), *arguments], env=self.env,
                              cwd=self.root, input="", capture_output=True, text=True, timeout=10)

    def calls(self, tool="pacman"):
        if not self.log.exists():
            return []
        return [call[1:] for line in self.log.read_text().splitlines()
                if (call := json.loads(line))[0] == tool]

    def removals(self):
        return [call for call in self.calls() if call[0] == "-R"]

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_existing_nautilus_without_dolphin_needs_no_package_changes(self):
        self.state.write_text(json.dumps(["nautilus"]))
        self.assert_success(self.setup())
        self.assertEqual(self.calls("sudo"), [])
        self.assertEqual(self.calls(), [["-Qq", "--", "nautilus"], ["-Qq", "--", "dolphin"]])

    def test_cleanup_protects_manifest_explicit_packages_and_personal_data(self):
        packages = ["dolphin", "unused-kde-library", "ripgrep", "polkit-kde-agent", "qt6-svg", "personal-editor"]
        self.state.write_text(json.dumps(["nautilus", *packages]))
        self.env["TEST_CANDIDATES"] = "\n".join(packages)
        config = self.home / ".config/dolphinrc"
        config.parent.mkdir()
        config.write_text("# Personal Dolphin preferences\n")
        data = self.home / ".local/share/dolphin/view_properties"
        data.parent.mkdir(parents=True)
        data.write_bytes(b"Personal data")
        result = self.setup("--help", "--unknown", "extra")
        self.assert_success(result)
        plan = ["-Rs", "--print", "--print-format", "%n", "--", "dolphin"]
        self.assertLess(self.calls().index(["-Qq", "--", "nautilus"]), self.calls().index(plan))
        self.assertFalse(any(call[0].startswith("-S") for call in self.calls()))
        self.assertEqual(self.removals(), [["-R", "--noconfirm", "--", "dolphin", "unused-kde-library"]])
        self.assertEqual(set(json.loads(self.state.read_text())),
                         {"nautilus", "ripgrep", "polkit-kde-agent", "qt6-svg", "personal-editor"})
        self.assertEqual(config.read_text(), "# Personal Dolphin preferences\n")
        self.assertEqual(data.read_bytes(), b"Personal data")

    def test_rerun_after_removal_does_not_repeat_package_changes(self):
        self.assert_success(self.setup())
        previous = self.calls("sudo")
        self.assert_success(self.setup())
        self.assertEqual(self.calls("sudo"), previous)

    def test_missing_nautilus_skips_cleanup_without_installing_anything(self):
        self.state.write_text(json.dumps(["dolphin"]))
        result = self.setup()
        self.assert_success(result)
        self.assertIn("Nautilus is not installed; keeping Dolphin", result.stderr)
        self.assertEqual(self.calls(), [["-Qq", "--", "nautilus"]])
        self.assertEqual(self.calls("sudo"), [])
        self.assertEqual(json.loads(self.state.read_text()), ["dolphin"])

    def test_failed_metadata_queries_fall_back_to_dolphin_only(self):
        for failure in ("TEST_PLAN_FAIL", "TEST_EXPLICIT_FAIL"):
            with self.subTest(failure=failure):
                self.log.unlink(missing_ok=True)
                self.state.write_text(json.dumps(["nautilus", "dolphin", "unused-kde-library"]))
                self.env[failure] = "1"
                result = self.setup()
                self.assert_success(result)
                self.assertIn("Could not verify unused dependencies", result.stderr)
                self.assertEqual(self.removals(), [["-R", "--noconfirm", "--", "dolphin"]])
                self.assertIn("unused-kde-library", json.loads(self.state.read_text()))
                self.env.pop(failure)

    def test_missing_manifest_falls_back_to_dolphin_only(self):
        (self.checkout / "packages/packages.lua").unlink()
        result = self.setup()
        self.assert_success(result)
        self.assertIn("Could not verify unused dependencies", result.stderr)
        self.assertEqual(self.removals(), [["-R", "--noconfirm", "--", "dolphin"]])

    def test_invalid_candidate_output_cannot_become_a_removal_option(self):
        self.env["TEST_CANDIDATES"] = "dolphin\nunused-kde-library\n--nodeps"
        result = self.setup()
        self.assert_success(result)
        self.assertIn("Could not verify unused dependencies", result.stderr)
        self.assertEqual(self.removals(), [["-R", "--noconfirm", "--", "dolphin"]])

    def test_protected_package_dependency_causes_dolphin_only_retry(self):
        self.env["TEST_SHARED_DEPENDENCY"] = "1"
        result = self.setup()
        self.assert_success(result)
        self.assertIn("retrying Dolphin removal alone", result.stderr)
        self.assertEqual(self.removals(), [["-R", "--noconfirm", "--", "dolphin", "unused-kde-library"],
                                          ["-R", "--noconfirm", "--", "dolphin"]])
        self.assertEqual(set(json.loads(self.state.read_text())), {"nautilus", "unused-kde-library"})

    def test_removal_failure_warns_without_claiming_success(self):
        self.env["TEST_REMOVE_FAIL"] = "1"
        result = self.setup()
        self.assert_success(result)
        self.assertIn("Dolphin removal failed", result.stderr)
        self.assertNotIn("Dolphin removed", result.stdout)
        self.assertIn("dolphin", json.loads(self.state.read_text()))

    def test_missing_optional_package_tools_skip_without_changes(self):
        for name in ("pacman", "sudo"):
            with self.subTest(command=name):
                target = self.bin / name
                saved = self.bin / f"saved-{name}"
                target.rename(saved)
                try:
                    result = self.setup()
                    self.assert_success(result)
                    self.assertIn(f"{name} is unavailable", result.stderr)
                    self.assertEqual(self.calls(), [])
                    self.assertEqual(self.calls("sudo"), [])
                finally:
                    saved.rename(target)

    def test_symlink_entry_uses_its_real_checkout_manifest(self):
        self.env["TEST_CANDIDATES"] = "dolphin\nripgrep"
        entry = self.root / "application cleanup"
        entry.symlink_to(self.checkout / "scripts/setup/cleanup.sh")
        self.assert_success(self.setup(entry=entry))
        self.assertEqual(self.removals(), [["-R", "--noconfirm", "--", "dolphin"]])


if __name__ == "__main__":
    unittest.main()
