"""Exercise unattended package setup using isolated manifests and fake tools."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]
LUA = Path("/usr/bin/lua")


@unittest.skipUnless(LUA.is_file(), "The system Lua runtime is required")
class SetupPackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna packages '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.installed = self.root / "installed"
        self.installed.mkdir()
        (self.root / "tmp").mkdir()
        self.checkout = self.root / "checkout"
        for name in ("scripts/setup/install-deps.lua", "scripts/setup/1-setup-lua.sh",
                     "scripts/setup/2-install-core-deps.sh", "scripts/setup/4-setup-aur-helper.sh",
                     "scripts/setup/5-install-app-packages.sh", "scripts/setup/6-install-fonts.sh",
                     "lib/common.lua", "lib/common.sh"):
            destination = self.checkout / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, destination)
        (self.checkout / "packages").mkdir()
        (self.checkout / "packages/packages.lua").write_text('''return {
    core = { { name = "core-one", source = "pacman" } },
    main = {
        { name = "repo-one", source = "pacman" }, { name = "repo-two", source = "pacman" },
        { name = "aur-one", source = "aur" }, { name = "aur-two", source = "aur" },
    },
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
        for name in ("TEST_PACKAGE_FAILURE", "TEST_MAKEPKG_FAILURE", "TEST_SKIP_INSTALL", "TEST_SKIP_PACKAGES"):
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
        if name not in os.environ.get("TEST_SKIP_PACKAGES", "").split(","):
            (root / "installed" / name).touch()
print("Fixture " + tool + " package output")
'''
        for name in ("pacman", "yay", "paru", "sudo", "id", "git", "makepkg"):
            path = self.bin / name
            path.write_text(backend)
            path.chmod(0o755)

    def run_setup(self, step="install-deps.lua", *arguments, entry=None, cwd=None):
        command = [str(LUA), "-E"] if step.endswith(".lua") else [str(self.bin / "bash")]
        script = entry or self.checkout / "scripts/setup" / step
        return subprocess.run([*command, str(script), *arguments],
                              env=self.env, cwd=cwd or self.root, input="", capture_output=True,
                              text=True, timeout=10)

    def calls(self, tool):
        path = self.root / "calls.jsonl"
        if not path.exists():
            return []
        return [call for line in path.read_text().splitlines() if (call := json.loads(line))[0] == tool]

    def test_numbered_package_steps_select_their_group_from_any_directory_or_symlink(self):
        groups = {
            "2-install-core-deps.sh": {"core-one"},
            "5-install-app-packages.sh": {"repo-one", "repo-two", "aur-one", "aur-two"},
            "6-install-fonts.sh": {"font-one"},
        }
        for step, packages in groups.items():
            entry = self.root / ("linked " + step)
            entry.symlink_to(self.checkout / "scripts/setup" / step)
            for linked in (False, True):
                with self.subTest(step=step, linked=linked):
                    for installed in self.installed.iterdir():
                        installed.unlink()
                    result = self.run_setup(step, "--unknown", "extra", "--help", "core",
                                            entry=entry if linked else None)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual({path.name for path in self.installed.iterdir()}, packages)

    def test_numbered_package_steps_propagate_package_failure(self):
        self.env["TEST_PACKAGE_FAILURE"] = "7"
        for step in ("2-install-core-deps.sh", "5-install-app-packages.sh", "6-install-fonts.sh"):
            with self.subTest(step=step):
                result = self.run_setup(step)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("Dependency setup failed", result.stderr)
                self.assertNotIn("Dependencies ready", result.stdout)
                self.assertEqual(list(self.installed.iterdir()), [])

    def test_shared_installer_resolves_its_manifest_from_basename_or_external_symlink(self):
        entry = self.root / "linked installer.lua"
        entry.symlink_to(self.checkout / "scripts/setup/install-deps.lua")
        for script, cwd in ((entry, self.root), (Path("install-deps.lua"), self.checkout / "scripts/setup")):
            with self.subTest(entry=script):
                result = self.run_setup("install-deps.lua", "core", entry=script, cwd=cwd)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual({path.name for path in self.installed.iterdir()}, {"core-one"})

    def test_pacman_and_yay_install_without_confirmations_or_review_menus(self):
        result = self.run_setup("install-deps.lua", "main")
        self.assertEqual(result.returncode, 0, result.stderr)
        pacman = next(call for call in self.calls("pacman") if "-Syu" in call)
        self.assertIn("--noconfirm", pacman)
        self.assertIn("--needed", pacman)
        yay = self.calls("yay")[0]
        self.assertIn("--needed", yay)
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
        self.assertIn("--needed", paru)
        self.assertNotIn("--answerdiff", paru)

    def test_installed_core_packages_are_still_requested_for_updates(self):
        (self.installed / "core-one").touch()
        result = self.run_setup("install-deps.lua", "core")
        self.assertEqual(result.returncode, 0, result.stderr)
        operation = next(call for call in self.calls("pacman") if "-Syu" in call)
        self.assertIn("--noconfirm", operation)
        self.assertIn("--needed", operation)
        self.assertEqual(operation[operation.index("--") + 1:], ["core-one"])

    def test_fully_installed_repository_and_aur_groups_are_checked_for_updates(self):
        for name in ("repo-one", "repo-two", "aur-one", "aur-two"):
            (self.installed / name).touch()

        for helper in ("yay", "paru"):
            with self.subTest(helper=helper):
                if helper == "paru":
                    (self.bin / "yay").unlink()
                result = self.run_setup("install-deps.lua", "main")
                self.assertEqual(result.returncode, 0, result.stderr)
                pacman = [call for call in self.calls("pacman") if "-Syu" in call][-1]
                aur = self.calls(helper)[-1]
                self.assertEqual(pacman[pacman.index("--") + 1:], ["repo-one", "repo-two"])
                self.assertEqual(aur[aur.index("--") + 1:], ["aur-one", "aur-two"])
                self.assertIn("--needed", pacman)
                self.assertIn("--needed", aur)

    def test_mixed_installed_and_missing_packages_are_all_passed_to_the_managers(self):
        for name in ("repo-one", "aur-one"):
            (self.installed / name).touch()
        result = self.run_setup("install-deps.lua", "main")
        self.assertEqual(result.returncode, 0, result.stderr)
        pacman = next(call for call in self.calls("pacman") if "-Syu" in call)
        aur = self.calls("yay")[0]
        self.assertEqual(pacman[pacman.index("--") + 1:], ["repo-one", "repo-two"])
        self.assertEqual(aur[aur.index("--") + 1:], ["aur-one", "aur-two"])
        self.assertIn("--needed", pacman)
        self.assertIn("--needed", aur)
        for name in ("repo-one", "repo-two", "aur-one", "aur-two"):
            self.assertTrue((self.installed / name).exists())

    def test_first_known_group_is_selected_and_other_arguments_are_ignored(self):
        result = self.run_setup("install-deps.lua", "--help", "-h", "--force", "--unknown",
                                "unused", "core", "main", "fonts", "extra")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        operation = next(call for call in self.calls("pacman") if "-Syu" in call)
        self.assertIn("--needed", operation)
        self.assertEqual(operation[operation.index("--") + 1:], ["core-one"])
        self.assertEqual(self.calls("yay"), [])
        self.assertEqual([path.name for path in self.installed.iterdir()], ["core-one"])

    def test_no_known_group_is_a_successful_noop(self):
        for arguments in ((), ("--help", "-h", "--force", "--unknown", "unused")):
            with self.subTest(arguments=arguments):
                result = self.run_setup("install-deps.lua", *arguments)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("No package group selected", result.stdout + result.stderr)
                self.assertEqual(list(self.installed.iterdir()), [])
                self.assertFalse((self.root / "calls.jsonl").exists())

    def test_empty_selected_group_skips_package_tool_preflight(self):
        manifest = self.checkout / "packages/packages.lua"
        manifest.write_text(manifest.read_text().replace(
            'extra = { { name = "extra-one", source = "pacman" } },', 'extra = {},'))
        for tool in ("pacman", "yay", "paru"):
            (self.bin / tool).unlink()
        result = self.run_setup("install-deps.lua", "extra")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(list(self.installed.iterdir()), [])
        self.assertFalse((self.root / "calls.jsonl").exists())

    def test_malformed_unselected_groups_stop_before_installation(self):
        manifest = self.checkout / "packages/packages.lua"
        original = manifest.read_text()
        entry = '{ name = "extra-one", source = "pacman" }'
        for group in ("{ [2] = " + entry + " }", "{ [1] = " + entry + ", [3] = " + entry + " }",
                      "{ named = " + entry + " }", "{ true }", '"not a list"'):
            with self.subTest(group=group):
                (self.root / "calls.jsonl").unlink(missing_ok=True)
                for installed in self.installed.iterdir():
                    installed.unlink()
                manifest.write_text(original.replace("extra = { " + entry + " }", "extra = " + group))
                result = self.run_setup("install-deps.lua", "core")
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("Dependency setup failed", result.stderr)
                self.assertEqual(list(self.installed.iterdir()), [])
                self.assertFalse((self.root / "calls.jsonl").exists())

    def test_bootstrap_helpers_ignore_arguments_without_reinstalling_ready_dependencies(self):
        self.mock_system_lua_probe()
        for name in ("lua", "lua-argparse"):
            (self.installed / name).touch()
        for step in ("1-setup-lua.sh", "4-setup-aur-helper.sh"):
            with self.subTest(step=step):
                result = self.run_setup(step, "--help", "-h", "--force", "--unknown", "main")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(self.calls("pacman"), [])
                self.assertEqual(self.calls("makepkg"), [])

    def test_missing_aur_helper_skips_aur_but_installs_repository_packages(self):
        for tool in ("yay", "paru"):
            (self.bin / tool).unlink()
        result = self.run_setup("install-deps.lua", "main")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        operation = next(call for call in self.calls("pacman") if "-Syu" in call)
        self.assertEqual(operation[operation.index("--") + 1:], ["repo-one", "repo-two"])
        self.assertEqual(sorted(path.name for path in self.installed.iterdir()), ["repo-one", "repo-two"])
        self.assertIn("[WARN]", result.stdout + result.stderr)
        self.assertNotIn("Dependencies ready: main", result.stdout)

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

    def test_installed_targets_are_verified_in_one_query_per_source(self):
        result = self.run_setup("install-deps.lua", "main")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        queries = [call for call in self.calls("pacman") if call[1] == "-Q"]
        self.assertEqual(queries, [
            ["pacman", "-Q", "--", "repo-one", "repo-two"],
            ["pacman", "-Q", "--", "aur-one", "aur-two"],
        ])

    def test_partial_install_identifies_missing_target_and_stops_before_aur(self):
        self.env["TEST_SKIP_PACKAGES"] = "repo-two"
        result = self.run_setup("install-deps.lua", "main")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Package was not installed: repo-two", result.stderr)
        self.assertEqual(self.calls("yay"), [])
        self.assertNotIn("Dependencies ready", result.stdout)

    def mock_system_lua_probe(self):
        # Bash resolves this exact function name even for an absolute command.
        # The fake package install makes the second probe pass without modifying /usr.
        environment = self.root / "lua-probe-env"
        environment.write_text('''
/usr/bin/lua() {
    [[ -f "$TEST_PACKAGE_ROOT/installed/lua" && -f "$TEST_PACKAGE_ROOT/installed/lua-argparse" ]]
}
''')
        self.env["BASH_ENV"] = str(environment)

    def test_lua_bootstrap_disables_package_confirmations(self):
        self.mock_system_lua_probe()
        result = self.run_setup("1-setup-lua.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        operation = next(call for call in self.calls("pacman") if "-Syu" in call)
        self.assertIn("--noconfirm", operation)
        self.assertIn("--needed", operation)
        self.assertEqual(operation[-2:], ["lua", "lua-argparse"])

    def test_working_system_lua_skips_package_setup(self):
        self.mock_system_lua_probe()
        for name in ("lua", "lua-argparse"):
            (self.installed / name).touch()
        result = self.run_setup("1-setup-lua.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("already available", result.stdout)
        self.assertEqual(self.calls("pacman"), [])
        self.assertEqual(self.calls("sudo"), [])

    def test_lua_bootstrap_checks_runtime_after_successful_package_command(self):
        self.mock_system_lua_probe()
        self.env["TEST_SKIP_INSTALL"] = "1"
        result = self.run_setup("1-setup-lua.sh")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("system Lua cannot load argparse", result.stderr)
        self.assertTrue(any("-Syu" in call for call in self.calls("pacman")))
        self.assertNotIn("Lua and argparse are ready", result.stdout)

    @unittest.skipIf(os.geteuid() == 0, "AUR bootstrap requires a real non-root user")
    def test_missing_aur_build_prerequisites_warn_and_skip_without_installing(self):
        (self.bin / "yay").unlink()
        (self.bin / "paru").unlink()
        for name in ("pacman", "sudo", "git", "makepkg"):
            with self.subTest(tool=name):
                tool = self.bin / name
                hidden = self.bin / (name + "-hidden")
                tool.rename(hidden)
                try:
                    result = self.run_setup("4-setup-aur-helper.sh")
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn(name + " is unavailable", result.stderr)
                    self.assertIn("[WARN]", result.stderr)
                    self.assertFalse((self.root / "calls.jsonl").exists())
                    self.assertEqual(list((self.root / "tmp").iterdir()), [])
                finally:
                    hidden.rename(tool)

    @unittest.skipIf(os.geteuid() == 0, "AUR bootstrap requires a real non-root user")
    def test_aur_bootstrap_disables_pacman_and_makepkg_confirmations(self):
        (self.bin / "yay").unlink()
        (self.bin / "paru").unlink()
        result = self.run_setup("4-setup-aur-helper.sh")
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
        result = self.run_setup("4-setup-aur-helper.sh")
        self.assertEqual(result.returncode, 21, result.stderr)
        self.assertNotIn("AUR helper ready", result.stdout)
        self.assertEqual(list((self.root / "tmp").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
