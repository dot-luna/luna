"""Exercise unattended package setup using isolated manifests and fake tools."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
LUA = Path("/usr/bin/lua")


@unittest.skipUnless(LUA.is_file(), "The system Lua runtime is required")
class SetupPackageTests(unittest.TestCase):
    def setUp(self):
        if subprocess.run([str(LUA), "-E", "-e", 'require("argparse")'], capture_output=True).returncode:
            self.skipTest("Lua argparse is required")
        self.temporary = tempfile.TemporaryDirectory(prefix="luna packages '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.installed = self.root / "installed"
        self.installed.mkdir()
        (self.root / "tmp").mkdir()
        self.checkout = self.root / "checkout"
        for name in ("scripts/setup/install-deps.lua", "scripts/setup/lua.sh", "scripts/setup/aur.sh",
                     "lib/common.lua", "lib/common.sh"):
            destination = self.checkout / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, destination)
        (self.checkout / "packages").mkdir()
        (self.checkout / "packages/packages.lua").write_text('''return {
    core = { { name = "core-one", source = "pacman" } },
    main = { { name = "repo-one", source = "pacman" }, { name = "aur-one", source = "aur" } },
    fonts = { { name = "font-one", source = "pacman" } },
    extra = { { name = "extra-one", source = "pacman" } },
}
''')

        # Restrict PATH so removing a mock helper never exposes a real package tool.
        for name in ("bash", "sh", "readlink", "dirname", "mktemp", "rm", "cat", "sed", "awk", "date", "env"):
            executable = shutil.which(name)
            if executable:
                (self.bin / name).symlink_to(executable)
        self.env = dict(os.environ, PATH=str(self.bin), HOME=str(self.root / "home"),
                        TMPDIR=str(self.root / "tmp"), TEST_PACKAGE_ROOT=str(self.root),
                        BASH_ENV="", NO_COLOR="1")
        for name in ("TEST_PACKAGE_FAILURE", "TEST_MAKEPKG_FAILURE", "TEST_SKIP_INSTALL"):
            self.env.pop(name, None)

        backend = f"#!{sys.executable}\n" + '''
import json, os, pathlib, shutil, sys
root = pathlib.Path(os.environ["TEST_PACKAGE_ROOT"])
tool = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with (root / "calls.jsonl").open("a") as output:
    output.write(json.dumps([tool, *args]) + "\\n")
if tool == "id":
    print("1000")
    sys.exit(0)
if tool == "sudo":
    if not args or args[0] != "pacman":
        sys.exit("Unexpected sudo invocation")
    os.execv(str(root / "bin/pacman"), args)
if tool == "git":
    if args[:3] != ["clone", "--", "https://aur.archlinux.org/yay.git"]:
        sys.exit("Unexpected git invocation")
    pathlib.Path(args[-1]).mkdir()
    sys.exit(0)
if tool == "makepkg":
    if args != ["-si", "--noconfirm"]:
        sys.exit("Unexpected makepkg invocation")
    failure = int(os.environ.get("TEST_MAKEPKG_FAILURE", "0"))
    if not failure:
        shutil.copy2(root / "bin/makepkg", root / "bin/yay")
    sys.exit(failure)
if tool == "pacman" and args[0] == "-Q":
    names = [name for name in args[1:] if name != "--"]
    sys.exit(0 if all((root / "installed" / name).exists() for name in names) else 1)
if "--noconfirm" not in args or "--" not in args:
    sys.exit("Package operation must disable confirmations: " + repr(args))
failure = int(os.environ.get("TEST_PACKAGE_FAILURE", "0"))
if failure:
    sys.exit(failure)
if not os.environ.get("TEST_SKIP_INSTALL"):
    for name in args[args.index("--") + 1:]:
        (root / "installed" / name).touch()
print("Fixture " + tool + " package output")
'''
        for name in ("pacman", "yay", "paru", "sudo", "id", "git", "makepkg"):
            path = self.bin / name
            path.write_text(backend)
            path.chmod(0o755)

    def run_setup(self, step="install-deps.lua", *arguments):
        command = [str(LUA), "-E"] if step.endswith(".lua") else [str(self.bin / "bash")]
        return subprocess.run([*command, str(self.checkout / "scripts/setup" / step), *arguments],
                              env=self.env, cwd=self.root, input="", capture_output=True,
                              text=True, timeout=10)

    def calls(self, tool):
        path = self.root / "calls.jsonl"
        if not path.exists():
            return []
        return [call for line in path.read_text().splitlines() if (call := json.loads(line))[0] == tool]

    def test_pacman_and_yay_install_without_confirmations_or_review_menus(self):
        result = self.run_setup("install-deps.lua", "main")
        self.assertEqual(result.returncode, 0, result.stderr)
        pacman = next(call for call in self.calls("pacman") if "-Syu" in call)
        self.assertIn("--noconfirm", pacman)
        self.assertIn("--needed", pacman)
        yay = self.calls("yay")[0]
        for flag in ("--noconfirm", "--answerclean", "--answerdiff", "--answeredit", "--noremovemake"):
            self.assertIn(flag, yay)
        for flag in ("--answerclean", "--answerdiff", "--answeredit"):
            self.assertEqual(yay[yay.index(flag) + 1], "None")
        self.assertIn("Dependencies ready: main", result.stdout)
        self.assertIn("  Fixture pacman package output", result.stdout)
        self.assertIn("  Fixture yay package output", result.stdout)

    def test_paru_uses_its_own_review_flags(self):
        (self.bin / "yay").unlink()
        result = self.run_setup("install-deps.lua", "main")
        self.assertEqual(result.returncode, 0, result.stderr)
        paru = self.calls("paru")[0]
        self.assertIn("--noconfirm", paru)
        self.assertIn("--skipreview", paru)
        self.assertIn("--noremovemake", paru)
        self.assertNotIn("--answerdiff", paru)

    def test_existing_packages_are_summarized_and_force_reinstalls(self):
        (self.installed / "core-one").touch()
        result = self.run_setup("install-deps.lua", "core")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("1 package already installed", result.stdout)
        self.assertNotIn("Enable Docker when ready", result.stdout)
        self.assertFalse(any("-Syu" in call for call in self.calls("pacman")))
        result = self.run_setup("install-deps.lua", "core", "--force")
        self.assertEqual(result.returncode, 0, result.stderr)
        operation = next(call for call in self.calls("pacman") if "-Syu" in call)
        self.assertIn("--noconfirm", operation)
        self.assertNotIn("--needed", operation)

    def test_package_failure_stops_before_aur(self):
        self.env["TEST_PACKAGE_FAILURE"] = "7"
        result = self.run_setup("install-deps.lua", "main")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Dependency setup failed", result.stderr)
        self.assertTrue(any("-Syu" in call for call in self.calls("pacman")))
        self.assertEqual(self.calls("yay"), [])
        self.assertNotIn("Dependencies ready", result.stdout)

    def test_successful_command_still_requires_installed_package(self):
        self.env["TEST_SKIP_INSTALL"] = "1"
        result = self.run_setup("install-deps.lua", "core")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Package was not installed", result.stderr)

    def test_lua_bootstrap_disables_package_confirmations(self):
        result = self.run_setup("lua.sh", "--force")
        self.assertEqual(result.returncode, 0, result.stderr)
        operation = next(call for call in self.calls("pacman") if "-Syu" in call)
        self.assertIn("--noconfirm", operation)
        self.assertEqual(operation[-2:], ["lua", "lua-argparse"])

    @unittest.skipIf(os.geteuid() == 0, "AUR bootstrap requires a real non-root user")
    def test_aur_bootstrap_disables_pacman_and_makepkg_confirmations(self):
        (self.bin / "yay").unlink()
        (self.bin / "paru").unlink()
        result = self.run_setup("aur.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        operation = next(call for call in self.calls("pacman") if "-Syu" in call)
        self.assertIn("--noconfirm", operation)
        self.assertEqual(self.calls("makepkg"), [["makepkg", "-si", "--noconfirm"]])
        self.assertEqual(list((self.root / "tmp").iterdir()), [])

    @unittest.skipIf(os.geteuid() == 0, "AUR bootstrap requires a real non-root user")
    def test_failed_aur_build_propagates_and_cleans_temporary_files(self):
        (self.bin / "yay").unlink()
        (self.bin / "paru").unlink()
        self.env["TEST_MAKEPKG_FAILURE"] = "21"
        result = self.run_setup("aur.sh")
        self.assertEqual(result.returncode, 21, result.stderr)
        self.assertNotIn("AUR helper ready", result.stdout)
        self.assertEqual(list((self.root / "tmp").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
