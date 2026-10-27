"""Exercise mise tool setup without downloads or changes outside temporary homes."""

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
TOOLS = {"node": "lts", "bun": "latest", "pnpm": "latest", "python": "latest", "uv": "latest"}


@unittest.skipUnless(LUA.is_file(), "The system Lua runtime is required")
class MiseSetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna mise '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home with spaces"
        self.home.mkdir()
        self.checkout = self.root / "checkout"
        self.bin = self.root / "bin"
        self.bin.mkdir()

        for name in ("scripts/setup/3-install-dev-tools.lua", "packages/packages.mise.lua", "lib/common.lua", "lib/json.lua"):
            destination = self.checkout / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, destination)
        self.manifest = self.checkout / "packages/packages.mise.lua"

        # A restricted PATH prevents missing-helper cases from invoking the real mise.
        for name in ("sh", "bash", "dirname", "readlink", "realpath"):
            executable = shutil.which(name)
            if executable:
                (self.bin / name).symlink_to(executable)
        self.env = dict(os.environ, HOME=str(self.home), PATH=str(self.bin),
                        TEST_MISE_ROOT=str(self.root), TEST_PYTHON=sys.executable, NO_COLOR="1")
        for name in ("BASH_ENV", "ENV", "TEST_MISE_USE_FAILURE", "TEST_MISE_LS_FAILURE",
                     "TEST_MISE_REPORT", "TEST_MISE_ROOT_USER", "TEST_MISE_SHELL_FAILURE"):
            self.env.pop(name, None)

        backend = f"#!{sys.executable}\n" + '''
import json, os, pathlib, sys
root = pathlib.Path(os.environ["TEST_MISE_ROOT"])
tool = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
if tool == "id":
    assert args == ["-u"]
    print("0" if os.environ.get("TEST_MISE_ROOT_USER") == "1" else "1000")
    sys.exit(0)
with (root / "calls.jsonl").open("a") as output:
    output.write(json.dumps({"tool": tool, "args": args}) + "\\n")
if tool == "activation.py":
    sys.exit(int(os.environ.get("TEST_MISE_SHELL_FAILURE", "0")))
assert args[:2] == ["--cd", os.path.realpath(os.environ["HOME"])], args
if args[2] == "use":
    failure = int(os.environ.get("TEST_MISE_USE_FAILURE", "0"))
    if failure:
        sys.exit(failure)
    requested = dict(value.split("@", 1) for value in args[args.index("--") + 1:])
    (root / "requested.json").write_text(json.dumps(requested))
    print("Fixture mise install output")
elif args[2] == "ls":
    failure = int(os.environ.get("TEST_MISE_LS_FAILURE", "0"))
    if failure:
        sys.exit(failure)
    requested = json.loads((root / "requested.json").read_text())
    report = {name: [{"version": "1.2.3", "requested_version": version,
                     "installed": True, "active": True}] for name, version in requested.items()}
    print(os.environ.get("TEST_MISE_REPORT", json.dumps(report)))
else:
    sys.exit("Unexpected mise invocation: " + repr(args))
'''
        for name in ("mise", "id"):
            path = self.bin / name
            path.write_text(backend)
            path.chmod(0o755)
        (self.root / "activation.py").write_text(backend)
        (self.checkout / "scripts/setup/mise-shell.sh").write_text(
            '#!/usr/bin/env bash\nexec "$TEST_PYTHON" "$TEST_MISE_ROOT/activation.py" "$@"\n')

        self.config = self.home / ".config/mise/config.toml"
        self.config.parent.mkdir(parents=True)
        self.config.write_text('[tools]\nrust = "stable"\n\n[settings]\nexperimental = true\n')

    def setup(self, *arguments, cwd=None, script=None):
        script = script or self.checkout / "scripts/setup/3-install-dev-tools.lua"
        return subprocess.run([str(LUA), "-E", str(script), *arguments],
                              env=self.env, cwd=cwd or self.checkout, input="", text=True,
                              capture_output=True, timeout=10)

    def records(self):
        path = self.root / "calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def clear_records(self):
        (self.root / "calls.jsonl").unlink(missing_ok=True)

    def write_manifest(self, *entries):
        rows = ["    { " + ", ".join(f"{key} = {json.dumps(value)}" for key, value in entry.items()) + " },"
                for entry in entries]
        self.manifest.write_text("return {\n" + "\n".join(rows) + "\n}\n")

    def report(self):
        return {name: [{"version": "1.2.3", "requested_version": version, "installed": True, "active": True}]
                for name, version in TOOLS.items()}

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("[OK]", result.stdout)

    def assert_failed(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("[OK]", result.stdout)
        self.assertFalse(any(record["tool"] == "activation.py" for record in self.records()))

    def test_default_tools_are_installed_globally_then_verified_before_shell_setup(self):
        original_config = self.config.read_text()
        result = self.setup()
        self.assert_success(result)
        self.assertEqual(self.records(), [
            {"tool": "mise", "args": ["--cd", str(self.home), "use", "--global", "--yes", "--fuzzy", "--",
                                       "node@lts", "bun@latest", "pnpm@latest", "python@latest", "uv@latest"]},
            {"tool": "mise", "args": ["--cd", str(self.home), "ls", "--global", "--json"]},
            {"tool": "activation.py", "args": []},
        ])
        # The setup wrapper must leave existing global configuration edits to mise.
        self.assertEqual(self.config.read_text(), original_config)
        self.assertIn("Fixture mise install output", result.stdout)

    def test_manifest_can_pin_selected_tool_versions(self):
        self.write_manifest(dict(name="node", source="mise", version="22.3.0"),
                            dict(name="python", source="mise", version="3.13"))
        self.assert_success(self.setup())
        self.assertEqual(self.records()[0]["args"][-2:], ["node@22.3.0", "python@3.13"])

    def test_entry_point_supports_basename_and_external_symlink_invocations(self):
        self.assert_success(self.setup(cwd=self.checkout / "scripts/setup", script="3-install-dev-tools.lua"))
        linked_script = self.root / "linked mise.lua"
        linked_script.symlink_to(self.checkout / "scripts/setup/3-install-dev-tools.lua")
        self.assert_success(self.setup(cwd=self.home, script=linked_script))

    def test_invalid_home_paths_stop_before_installing(self):
        file_path = self.root / "not-a-home"
        file_path.write_text("Keep this file\n")
        for home in ("", "relative/home", "/", "//", "/tmp/..", str(file_path), str(self.root / "missing-home")):
            with self.subTest(home=home):
                self.env["HOME"] = home
                self.assert_failed(self.setup())
                self.assertEqual(self.records(), [])

    def test_home_symlink_uses_the_real_home_for_mise(self):
        alias = self.root / "home alias"
        alias.symlink_to(self.home, target_is_directory=True)
        self.env["HOME"] = str(alias)
        self.assert_success(self.setup())
        self.assertEqual(self.records()[0]["args"][:2], ["--cd", str(self.home)])

    def test_whole_manifest_is_validated_before_any_installation(self):
        valid = dict(name="node", source="mise", version="lts")
        other = dict(name="bun", source="mise", version="latest")
        invalid = [dict(other, name=value) for value in ("../tool", "-flag", "npm:tool", "two tools", "", 12)]
        invalid += [dict(other, version=value) for value in ("", "--flag", "latest;touch /tmp/oops", "$(id)", 12)]
        invalid += [dict(other, source="pacman"), valid, {"name": "bun", "source": "mise"}]
        for entry in invalid:
            with self.subTest(entry=entry):
                self.write_manifest(valid, entry)
                self.assert_failed(self.setup())
                self.assertEqual(self.records(), [])

    def test_non_list_sparse_and_malformed_manifests_are_rejected(self):
        entry = '{name="node", source="mise", version="lts"}'
        manifests = ["return false", "return 'node'", "return {true}", "return {",
                     "return {node=" + entry + "}", "return {[1]=" + entry + ", [3]=" + entry + "}"]
        for manifest in manifests:
            with self.subTest(manifest=manifest):
                self.manifest.write_text(manifest)
                self.assert_failed(self.setup())
                self.assertEqual(self.records(), [])

    def test_install_failure_stops_before_verification_and_shell_setup(self):
        self.env["TEST_MISE_USE_FAILURE"] = "37"
        result = self.setup()
        self.assert_failed(result)
        self.assertIn("37", result.stderr)
        self.assertEqual(len(self.records()), 1)

    def test_list_failure_stops_before_shell_setup(self):
        self.env["TEST_MISE_LS_FAILURE"] = "23"
        self.assert_failed(self.setup())
        self.assertEqual(len(self.records()), 2)

    def test_missing_or_inactive_tool_is_not_reported_as_installed(self):
        for field, value in (("installed", False), ("active", False), ("requested_version", "20"),
                             ("installed", "true"), ("active", "true")):
            with self.subTest(field=field, value=value):
                report = self.report()
                report["uv"][0][field] = value
                self.env["TEST_MISE_REPORT"] = json.dumps(report)
                self.clear_records()
                self.assert_failed(self.setup())
                self.assertEqual(len(self.records()), 2)
        report = self.report()
        del report["uv"]
        self.env["TEST_MISE_REPORT"] = json.dumps(report)
        self.clear_records()
        self.assert_failed(self.setup())

    def test_matching_record_can_follow_another_installed_version(self):
        report = self.report()
        report["node"].insert(0, {"version": "20.0.0", "requested_version": "20", "installed": True, "active": False})
        report["rust"] = [{"version": "1.90", "requested_version": "stable", "installed": True, "active": True}]
        self.env["TEST_MISE_REPORT"] = json.dumps(report)
        self.assert_success(self.setup())

    def test_invalid_verification_output_stops_before_shell_setup(self):
        for report in ("not-json", "null", "[]", "{}", '{"node":true}'):
            with self.subTest(report=report):
                self.env["TEST_MISE_REPORT"] = report
                self.clear_records()
                self.assert_failed(self.setup())

    def test_shell_setup_failure_is_propagated(self):
        self.env["TEST_MISE_SHELL_FAILURE"] = "41"
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("[OK]", result.stdout)
        self.assertIn("41", result.stderr)
        self.assertEqual(self.records()[-1]["tool"], "activation.py")

    def test_empty_manifest_does_not_install_or_change_shell_files(self):
        self.write_manifest()
        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.records(), [])

    def test_root_is_rejected_before_any_installation(self):
        self.env["TEST_MISE_ROOT_USER"] = "1"
        result = self.setup()
        self.assert_failed(result)
        self.assertIn("normal user", result.stderr)
        self.assertEqual(self.records(), [])

    def test_missing_required_command_stops_before_any_installation(self):
        for name in ("mise", "bash", "realpath"):
            with self.subTest(name=name):
                tool = self.bin / name
                hidden = self.bin / (name + "-hidden")
                tool.rename(hidden)
                try:
                    result = self.setup()
                    self.assert_failed(result)
                    self.assertIn(name, result.stderr)
                    self.assertEqual(self.records(), [])
                finally:
                    hidden.rename(tool)

    def test_arguments_are_ignored_without_forcing_mise_installation(self):
        original = self.config.read_bytes()
        result = self.setup("--help", "-h", "--force", "--unknown", "main")
        self.assert_success(result)
        self.assertEqual(self.records()[0]["args"], ["--cd", str(self.home), "use", "--global", "--yes", "--fuzzy",
                                                     "--", *[f"{name}@{version}" for name, version in TOOLS.items()]])
        self.assertEqual(self.records()[-1], {"tool": "activation.py", "args": []})
        self.assertEqual(self.config.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
