"""Install harmless Git-app fixtures into temporary homes without system setup."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
ORIGIN = "https://github.com/dot-luna/whatly.git"


@unittest.skipIf(os.geteuid() == 0, "Git app setup requires a normal user")
@unittest.skipUnless(Path("/usr/bin/lua").is_file() and shutil.which("git"), "Lua and Git are required")
class GitAppSetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna git apps '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home with spaces"
        self.home.mkdir()
        self.checkout = self.root / "luna checkout"
        self.remote = self.root / "app remote"
        self.destination = self.home / ".local/src/whatly"
        self.bin = self.root / "tools"
        self.bin.mkdir()
        self.git = shutil.which("git")
        self.env = dict(os.environ, HOME=str(self.home),
                        PATH=str(self.bin) + ":" + os.environ["PATH"],
                        GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=str(self.root / "gitconfig"),
                        GIT_TERMINAL_PROMPT="0", TEST_GIT=self.git, TEST_ROOT=str(self.root),
                        TEST_PYTHON=sys.executable, NO_COLOR="1")
        for name in ("BASH_ENV", "ENV", "TEST_INSTALL_STATUS", "TEST_SKIP_EXECUTABLE",
                     "TEST_NONEXECUTABLE", "TEST_ROOT_USER"):
            self.env.pop(name, None)

        for name in ("scripts/setup/git-apps.lua", "lib/common.lua"):
            target = self.checkout / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, target)
        (self.checkout / "packages").mkdir()
        (self.checkout / "src/luna-cli").mkdir(parents=True)
        self.entry = dict(name="whatly", source="git", url=ORIGIN, ref="main",
                          script="scripts/install.sh", executable="whatly")
        self.write_manifest(self.entry)

        backend = f"#!{sys.executable}\n" + '''
import json, os, pathlib, sys
tool = pathlib.Path(sys.argv[0]).name
if tool == "id":
    assert sys.argv[1:] == ["-u"]
    print("0" if os.environ.get("TEST_ROOT_USER") == "1" else os.geteuid())
else:
    with (pathlib.Path(os.environ["TEST_ROOT"]) / "git-calls.jsonl").open("a") as output:
        output.write(json.dumps(sys.argv[1:]) + "\\n")
    os.execv(os.environ["TEST_GIT"], ["git", *sys.argv[1:]])
'''
        for name in ("git", "id"):
            target = self.bin / name
            target.write_text(backend)
            target.chmod(0o755)

        # This installer records its invocation and writes only a tiny executable.
        # It performs no dependency installation or native compilation.
        (self.root / "app-installer.py").write_text('''
import json, os, pathlib, sys
root = pathlib.Path(os.environ["TEST_ROOT"])
with (root / "installs.jsonl").open("a") as output:
    output.write(json.dumps({"cwd": os.getcwd(), "args": sys.argv[1:]}) + "\\n")
assert len(sys.argv) == 4 and sys.argv[1] == "--prefix" and sys.argv[3] == "--non-interactive"
print("Fixture app installer output", flush=True)
status = int(os.environ.get("TEST_INSTALL_STATUS", "0"))
if status:
    sys.exit(status)
if os.environ.get("TEST_SKIP_EXECUTABLE") != "1":
    binary = pathlib.Path(sys.argv[2]) / "bin" / pathlib.Path.cwd().name
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text("#!/bin/sh\\nexit 0\\n")
    binary.chmod(0o644 if os.environ.get("TEST_NONEXECUTABLE") == "1" else 0o755)
''')

        self.git_run("init", "--quiet", "--initial-branch=main", str(self.remote))
        self.git_run("-C", str(self.remote), "config", "user.name", "Git App Test")
        self.git_run("-C", str(self.remote), "config", "user.email", "git-app@example.invalid")
        (self.remote / "scripts").mkdir()
        (self.remote / "scripts/install.sh").write_text(
            '#!/usr/bin/env bash\nexec "$TEST_PYTHON" "$TEST_ROOT/app-installer.py" "$@"\n')
        self.git_run("-C", str(self.remote), "add", ".")
        self.git_run("-C", str(self.remote), "commit", "--quiet", "-m", "Fixture installer")
        self.git_run("config", "--global", f"url.{self.remote.as_uri()}.insteadOf", ORIGIN)

    def write_manifest(self, *entries):
        rows = ["    { " + ", ".join(f"{key} = {json.dumps(value)}" for key, value in entry.items()) + " },"
                for entry in entries]
        (self.checkout / "packages/packages.git.lua").write_text("return {\n" + "\n".join(rows) + "\n}\n")

    def git_run(self, *arguments):
        result = subprocess.run([self.git, *arguments], env=self.env, cwd=self.root,
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout.strip()

    def setup(self, *arguments):
        return subprocess.run(["/usr/bin/lua", "-E", str(self.checkout / "scripts/setup/git-apps.lua"), *arguments],
                              env=self.env, cwd=self.root, input="", text=True,
                              capture_output=True, timeout=15)

    def records(self, name):
        path = self.root / name
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def clones(self):
        return [call for call in self.records("git-calls.jsonl") if call[0] == "clone"]

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("[OK] Git app ready: whatly", result.stdout)

    def assert_failed(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Git app setup failed", result.stderr)

    def test_clone_runs_app_installer_with_user_prefix_and_submodule_flag(self):
        result = self.setup()
        self.assert_success(result)
        self.assertEqual(self.records("installs.jsonl"), [{
            "cwd": str(self.destination),
            "args": ["--prefix", str(self.home / ".local"), "--non-interactive"],
        }])
        self.assertEqual(self.clones(), [["clone", "--recurse-submodules", "--branch", "main",
                                         "--single-branch", "--", ORIGIN, str(self.destination)]])
        self.assertTrue(os.access(self.home / ".local/bin/whatly", os.X_OK))
        self.assertIn("Fixture app installer output", result.stdout)

    def test_reinstall_discards_local_changes_and_switches_requested_ref(self):
        self.assert_success(self.setup())
        (self.destination / "personal-file").write_text("Old local changes\n")
        self.git_run("-C", str(self.remote), "switch", "--quiet", "-c", "feature/app")
        (self.remote / "version").write_text("feature\n")
        self.git_run("-C", str(self.remote), "add", ".")
        self.git_run("-C", str(self.remote), "commit", "--quiet", "-m", "Feature app")
        self.write_manifest(dict(self.entry, ref="feature/app"))
        self.assert_success(self.setup("--force"))
        self.assertEqual(self.git_run("-C", str(self.destination), "branch", "--show-current"), "feature/app")
        self.assertFalse((self.destination / "personal-file").exists())
        self.assertEqual((self.destination / "version").read_text(), "feature\n")
        self.assertEqual(len(self.clones()), 2)
        self.assertEqual(list(self.home.rglob("*.luna-backup*")), [])

    def test_reinstall_gets_new_remote_commits(self):
        self.assert_success(self.setup())
        (self.remote / "version").write_text("updated\n")
        self.git_run("-C", str(self.remote), "add", ".")
        self.git_run("-C", str(self.remote), "commit", "--quiet", "-m", "New release")
        self.assert_success(self.setup())
        self.assertEqual((self.destination / "version").read_text(), "updated\n")
        self.assertEqual(len(self.clones()), 2)

    def test_tag_checkout_is_supported(self):
        self.git_run("-C", str(self.remote), "tag", "-a", "v1.0", "-m", "Release")
        self.write_manifest(dict(self.entry, ref="v1.0"))
        self.assert_success(self.setup())
        self.assertEqual(self.git_run("-C", str(self.destination), "branch", "--show-current"), "")
        self.assertEqual(self.git_run("-C", str(self.destination), "describe", "--tags", "--exact-match"), "v1.0")

    def test_submodules_are_initialized(self):
        submodule = self.root / "submodule"
        self.git_run("init", "--quiet", str(submodule))
        self.git_run("-C", str(submodule), "config", "user.name", "Git App Test")
        self.git_run("-C", str(submodule), "config", "user.email", "git-app@example.invalid")
        (submodule / "resource").write_text("Fixture submodule\n")
        self.git_run("-C", str(submodule), "add", ".")
        self.git_run("-C", str(submodule), "commit", "--quiet", "-m", "Submodule fixture")
        # This isolated config permits local fixture submodules only for the test.
        self.git_run("config", "--global", "protocol.file.allow", "always")
        self.git_run("-C", str(self.remote), "submodule", "add", "--quiet", str(submodule), "vendor/helper")
        self.git_run("-C", str(self.remote), "commit", "--quiet", "-m", "Include submodule")
        self.assert_success(self.setup())
        self.assertEqual((self.destination / "vendor/helper/resource").read_text(), "Fixture submodule\n")

    def test_existing_files_directories_and_symlinks_are_replaced(self):
        self.destination.parent.mkdir(parents=True)
        external = self.root / "external directory"
        external.mkdir()
        (external / "personal-file").write_text("Keep external\n")
        for kind in ("file", "directory", "symlink", "dangling"):
            with self.subTest(kind=kind):
                if self.destination.exists():
                    shutil.rmtree(self.destination)
                if kind == "file":
                    self.destination.write_text("Old file\n")
                elif kind == "directory":
                    self.destination.mkdir()
                    (self.destination / "personal-file").write_text("Old directory\n")
                else:
                    target = external if kind == "symlink" else self.root / "missing-target"
                    self.destination.symlink_to(target, target_is_directory=True)
                self.assert_success(self.setup())
                self.assertFalse(self.destination.is_symlink())
                self.assertTrue((self.destination / ".git").is_dir())
                self.assertEqual((external / "personal-file").read_text(), "Keep external\n")

    def test_entire_manifest_is_validated_before_replacing_any_checkout(self):
        self.destination.mkdir(parents=True)
        marker = self.destination / "personal-file"
        marker.write_text("Do not delete on invalid manifest\n")
        other_entry = dict(self.entry, name="other-app", executable="other-app")
        invalid_entries = [dict(other_entry, name=name) for name in
                           ("../elsewhere", "/absolute", ".", "..", "-option", "luna", "luna-cli")]
        invalid_entries += [dict(other_entry, script=script) for script in
                            ("/tmp/install.sh", "../install.sh", "scripts/../install.sh", "scripts//install.sh")]
        invalid_entries += [dict(other_entry, source="pacman"),
                            dict(other_entry, executable="../bad"),
                            dict(other_entry, ref="bad..ref"),
                            dict(other_entry, url="-bad-url"),
                            self.entry]
        for entry in invalid_entries:
            with self.subTest(entry=entry):
                self.write_manifest(self.entry, entry)
                self.assert_failed(self.setup())
                self.assertEqual(marker.read_text(), "Do not delete on invalid manifest\n")
                self.assertEqual(self.clones(), [])
                self.assertEqual(self.records("installs.jsonl"), [])

    def test_invalid_home_and_root_are_rejected_before_writes(self):
        for home in ("", "relative/home", "/", "//", str(self.root / "missing-home")):
            with self.subTest(home=home):
                self.env["HOME"] = home
                self.assert_failed(self.setup())
                self.assertFalse(self.destination.exists())
                self.assertEqual(self.clones(), [])
        self.env["HOME"] = str(self.home)
        self.env["TEST_ROOT_USER"] = "1"
        result = self.setup()
        self.assert_failed(result)
        self.assertIn("normal user", result.stderr)
        self.assertEqual(self.clones(), [])

    def test_current_luna_checkout_is_protected_even_with_app_name(self):
        self.destination.parent.mkdir(parents=True)
        self.checkout.rename(self.destination)
        self.checkout = self.destination
        result = self.setup()
        self.assert_failed(result)
        self.assertIn("overlaps Luna", result.stderr)
        self.assertTrue((self.checkout / "scripts/setup/git-apps.lua").is_file())
        self.assertEqual(self.clones(), [])

    def test_parent_symlink_cannot_redirect_deletion_inside_luna(self):
        self.destination.parent.parent.mkdir(parents=True)
        self.destination.parent.symlink_to(self.checkout, target_is_directory=True)
        marker = self.checkout / "whatly"
        marker.write_text("Protect checkout files\n")
        result = self.setup()
        self.assert_failed(result)
        self.assertIn("overlaps Luna", result.stderr)
        self.assertEqual(marker.read_text(), "Protect checkout files\n")
        self.assertEqual(self.clones(), [])

    def test_missing_ref_or_installer_stops_before_app_installation(self):
        self.write_manifest(dict(self.entry, ref="missing-branch"))
        self.assert_failed(self.setup())
        self.assertEqual(self.records("installs.jsonl"), [])
        self.write_manifest(self.entry)
        self.git_run("-C", str(self.remote), "rm", "scripts/install.sh")
        self.git_run("-C", str(self.remote), "commit", "--quiet", "-m", "Remove installer")
        self.assert_failed(self.setup())
        self.assertEqual(self.records("installs.jsonl"), [])

    def test_installer_symlink_cannot_escape_checkout(self):
        external = self.root / "external-installer.sh"
        external.write_text('touch "$TEST_ROOT/escaped-installer"\n')
        (self.remote / "scripts/install.sh").unlink()
        (self.remote / "scripts/install.sh").symlink_to(external)
        self.git_run("-C", str(self.remote), "add", ".")
        self.git_run("-C", str(self.remote), "commit", "--quiet", "-m", "Escaping installer")
        result = self.setup()
        self.assert_failed(result)
        self.assertIn("inside its checkout", result.stderr)
        self.assertFalse((self.root / "escaped-installer").exists())

    def test_failed_app_installation_stops_later_apps(self):
        self.write_manifest(self.entry, dict(self.entry, name="second-app", executable="second-app"))
        self.env["TEST_INSTALL_STATUS"] = "37"
        result = self.setup()
        self.assert_failed(result)
        self.assertIn("37", result.stderr)
        self.assertEqual(len(self.records("installs.jsonl")), 1)
        self.assertEqual(len(self.clones()), 1)
        self.assertFalse((self.home / ".local/src/second-app").exists())

    def test_missing_or_nonexecutable_result_is_failure(self):
        for setting in ("TEST_SKIP_EXECUTABLE", "TEST_NONEXECUTABLE"):
            with self.subTest(setting=setting):
                self.env[setting] = "1"
                result = self.setup()
                self.assert_failed(result)
                self.assertIn("did not install its executable", result.stderr)
                self.env.pop(setting)

    def test_help_and_bad_options_do_not_touch_installation(self):
        result = self.setup("--help")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("--force", result.stdout)
        self.assertNotEqual(self.setup("--unknown").returncode, 0)
        self.assertFalse(self.destination.exists())
        self.assertEqual(self.clones(), [])


if __name__ == "__main__":
    unittest.main()
