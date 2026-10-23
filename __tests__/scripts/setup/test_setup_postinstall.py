"""Check default-theme setup with a fake CLI and disposable XDG directories."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]


@unittest.skipUnless(Path("/usr/bin/lua").is_file(), "The system Lua runtime is required")
class SetupPostinstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna postinstall '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home with spaces"
        self.home.mkdir()
        self.checkout = self.root / "checkout with spaces"
        for name in ("scripts/setup/postinstall.sh", "lib/common.sh"):
            target = self.checkout / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, target)
        self.script = self.checkout / "scripts/setup/postinstall.sh"
        self.bundle = self.checkout / "themes/bundled/tokyo-night"
        self.bundle.mkdir(parents=True)
        (self.bundle / "colors.lua").write_text("-- Fixture bundled colors\n")
        self.cli = self.checkout / "src/luna-cli/main.lua"
        self.cli.parent.mkdir(parents=True)

        # The real Lua interpreter only invokes this isolated Python fixture;
        # no production theme code or desktop-setting commands are loaded.
        self.cli.write_text('''
local function quote(value)
    return "'" .. value:gsub("'", "'\\\\''") .. "'"
end
local command = {
    quote(assert(os.getenv("TEST_PYTHON"))),
    quote(assert(os.getenv("TEST_POSTINSTALL_ROOT")) .. "/theme-cli.py"),
}
for index = -2, #arg do
    command[#command + 1] = quote(arg[index])
end
local ok, _, code = os.execute(table.concat(command, " "))
os.exit(ok and 0 or code or 1)
''')
        (self.root / "theme-cli.py").write_text('''
import json, os, pathlib, shutil, sys
root = pathlib.Path(os.environ["TEST_POSTINSTALL_ROOT"])
args = sys.argv[4:]
data = pathlib.Path(os.environ["XDG_DATA_HOME"])
config = pathlib.Path(os.environ["XDG_CONFIG_HOME"])
with (root / "calls.jsonl").open("a") as output:
    output.write(json.dumps({"interpreter": sys.argv[1], "lua_flag": sys.argv[2],
                            "script": sys.argv[3], "args": args,
                            "data": str(data), "config": str(config)}) + "\\n")
theme = data / "luna/themes/tokyo-night"
selection = config / "luna/theme"
if args[:2] == ["theme", "install"]:
    assert len(args) == 4 and args[3] == "--force", args
    assert pathlib.Path(args[2]) == pathlib.Path(sys.argv[3]).parents[2] / "themes/bundled/tokyo-night"
    if theme.is_symlink():
        sys.exit("Fixture installed theme cannot be a symlink")
    failure = int(os.environ.get("TEST_THEME_INSTALL_FAILURE", "0"))
    if failure:
        sys.exit(failure)
    if theme.exists():
        shutil.rmtree(theme)
    shutil.copytree(args[2], theme)
elif args == ["theme", "set", "tokyo-night", "--force"]:
    assert theme.is_dir()
    failure = int(os.environ.get("TEST_THEME_SET_FAILURE", "0"))
    if failure:
        sys.exit(failure)
    selection.parent.mkdir(parents=True, exist_ok=True)
    staged = selection.with_suffix(".tmp")
    staged.write_text("tokyo-night\\n")
    staged.replace(selection)
else:
    sys.exit("Unexpected fixture CLI invocation: " + repr(args))
''')
        self.env = dict(os.environ, HOME=str(self.home), TEST_POSTINSTALL_ROOT=str(self.root),
                        TEST_PYTHON=sys.executable, NO_COLOR="1")
        for name in ("BASH_ENV", "ENV", "XDG_DATA_HOME", "XDG_CONFIG_HOME",
                     "TEST_THEME_INSTALL_FAILURE", "TEST_THEME_SET_FAILURE"):
            self.env.pop(name, None)

    def setup(self, *arguments, script=None):
        return subprocess.run(["bash", str(script or self.script), *arguments], env=self.env,
                              cwd=self.root, input="", capture_output=True, text=True, timeout=10)

    def records(self):
        log = self.root / "calls.jsonl"
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def clear_records(self):
        (self.root / "calls.jsonl").unlink(missing_ok=True)

    def data_home(self):
        return Path(self.env.get("XDG_DATA_HOME") or self.home / ".local/share")

    def config_home(self):
        return Path(self.env.get("XDG_CONFIG_HOME") or self.home / ".config")

    def installed_theme(self):
        return self.data_home() / "luna/themes/tokyo-night"

    def selection(self):
        return self.config_home() / "luna/theme"

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for record in self.records():
            self.assertEqual(record["interpreter"], "/usr/bin/lua")
            self.assertEqual(record["lua_flag"], "-E")
            self.assertEqual(record["script"], str(self.cli))
            self.assertEqual(record["data"], str(self.data_home()))
            self.assertEqual(record["config"], str(self.config_home()))

    def test_fresh_install_uses_bundle_then_selects_default(self):
        self.assert_success(self.setup())
        self.assertEqual([record["args"] for record in self.records()], [
            ["theme", "install", str(self.bundle), "--force"],
            ["theme", "set", "tokyo-night", "--force"],
        ])
        self.assertEqual((self.installed_theme() / "colors.lua").read_bytes(),
                         (self.bundle / "colors.lua").read_bytes())
        self.assertEqual(self.selection().read_text(), "tokyo-night\n")

    def test_rerun_replaces_default_and_selection_but_keeps_other_themes(self):
        self.assert_success(self.setup())
        colors = self.installed_theme() / "colors.lua"
        colors.write_text("-- Personal theme edits\n")
        marker = self.installed_theme() / "personal-marker"
        marker.write_text("Old installed copy\n")
        other = self.installed_theme().parent / "other-theme"
        other.mkdir()
        (other / "colors.lua").write_text("-- Unrelated theme\n")
        self.selection().write_text("another-theme\n")
        self.clear_records()
        result = self.setup()
        self.assert_success(result)
        self.assertEqual([record["args"][1] for record in self.records()], ["install", "set"])
        self.assertEqual(colors.read_bytes(), (self.bundle / "colors.lua").read_bytes())
        self.assertFalse(marker.exists())
        self.assertEqual((other / "colors.lua").read_text(), "-- Unrelated theme\n")
        self.assertEqual(self.selection().read_text(), "tokyo-night\n")
        self.assertEqual(list(self.home.rglob("*.luna-backup*")), [])

    def test_existing_empty_and_invalid_selections_are_reset(self):
        for index, contents in enumerate(("other-theme\n", "", "invalid theme selection\n")):
            with self.subTest(contents=contents):
                self.env["XDG_DATA_HOME"] = str(self.root / f"data-{index}")
                self.env["XDG_CONFIG_HOME"] = str(self.root / f"config-{index}")
                self.selection().parent.mkdir(parents=True)
                self.selection().write_text(contents)
                self.clear_records()
                self.assert_success(self.setup())
                self.assertEqual([record["args"][1] for record in self.records()], ["install", "set"])
                self.assertEqual(self.selection().read_text(), "tokyo-night\n")
                self.assertTrue(self.installed_theme().is_dir())

    def test_selection_symlink_is_replaced_without_changing_external_target(self):
        external = self.root / "personal-selection"
        self.selection().parent.mkdir(parents=True)
        for dangling in (False, True):
            with self.subTest(dangling=dangling):
                self.selection().unlink(missing_ok=True)
                if dangling:
                    external.unlink()
                else:
                    external.write_text("other-theme\n")
                self.selection().symlink_to(external)
                self.clear_records()
                self.assert_success(self.setup())
                self.assertEqual([record["args"][1] for record in self.records()], ["install", "set"])
                self.assertFalse(self.selection().is_symlink())
                self.assertEqual(self.selection().read_text(), "tokyo-night\n")
                if dangling:
                    self.assertFalse(external.exists())
                else:
                    self.assertEqual(external.read_text(), "other-theme\n")

    def test_empty_xdg_values_use_home_defaults(self):
        self.env.update(XDG_DATA_HOME="", XDG_CONFIG_HOME="")
        self.assert_success(self.setup())
        self.assertEqual(self.selection().read_text(), "tokyo-night\n")
        self.assertTrue(self.installed_theme().is_dir())

    def test_xdg_overrides_are_exported_to_every_cli_call(self):
        self.env.update(XDG_DATA_HOME=str(self.root / "custom data"),
                        XDG_CONFIG_HOME=str(self.root / "custom config"))
        self.assert_success(self.setup())
        self.assertEqual(self.selection().read_text(), "tokyo-night\n")
        self.assertEqual(list(self.home.iterdir()), [])

    def test_relative_xdg_paths_warn_and_skip_before_cli_calls(self):
        for name in ("XDG_DATA_HOME", "XDG_CONFIG_HOME"):
            with self.subTest(variable=name):
                self.env[name] = "relative/path"
                result = self.setup()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("[WARN]", result.stderr)
                self.assertEqual(self.records(), [])
                self.assertEqual(list(self.home.iterdir()), [])
                self.assertFalse((self.root / "relative").exists())
                self.env.pop(name)

    def test_failed_install_does_not_select_a_theme(self):
        self.env["TEST_THEME_INSTALL_FAILURE"] = "37"
        result = self.setup()
        self.assertEqual(result.returncode, 37, result.stdout + result.stderr)
        self.assertEqual([record["args"][1] for record in self.records()], ["install"])
        self.assertFalse(self.selection().exists())
        self.assertFalse(self.installed_theme().exists())

    def test_failed_selection_returns_failure_and_keeps_installed_copy(self):
        self.env["TEST_THEME_SET_FAILURE"] = "41"
        result = self.setup()
        self.assertEqual(result.returncode, 41, result.stdout + result.stderr)
        self.assertEqual([record["args"][1] for record in self.records()], ["install", "set"])
        self.assertFalse(self.selection().exists())
        self.assertTrue(self.installed_theme().is_dir())

    def test_installed_theme_symlink_is_not_followed_or_replaced(self):
        external = self.root / "personal-theme"
        external.mkdir()
        colors = external / "colors.lua"
        colors.write_text("-- External theme\n")
        self.installed_theme().parent.mkdir(parents=True)
        self.installed_theme().symlink_to(external, target_is_directory=True)
        result = self.setup()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([record["args"][1] for record in self.records()], ["install"])
        self.assertTrue(self.installed_theme().is_symlink())
        self.assertEqual(colors.read_text(), "-- External theme\n")
        self.assertFalse(self.selection().exists())

    def test_extra_arguments_and_symlink_entry_use_the_same_checkout(self):
        link = self.root / "linked postinstall.sh"
        link.symlink_to(self.script)
        result = self.setup("--help", "-h", "--force", "--unknown", "main", script=link)
        self.assert_success(result)
        self.assertEqual([record["args"] for record in self.records()], [
            ["theme", "install", str(self.bundle), "--force"],
            ["theme", "set", "tokyo-night", "--force"],
        ])

    def test_real_cli_reinstalls_default_and_preserves_other_theme_copies(self):
        probe = subprocess.run(["/usr/bin/lua", "-E", "-e", "require('argparse')"],
                               env=self.env, capture_output=True, text=True, timeout=10)
        if probe.returncode != 0:
            self.skipTest("The real CLI requires system Lua argparse")

        # A closed PATH allows only file operations and the fake GSettings tool.
        # Neither a session command nor a downloader can reach the host desktop.
        tools = self.root / "safe tools"
        tools.mkdir()
        for name in ("bash", "sh", "readlink", "dirname", "realpath", "mkdir", "mktemp", "cp", "rm",
                     "file", "find", "cmp"):
            executable = shutil.which(name)
            self.assertIsNotNone(executable, name)
            (tools / name).symlink_to(executable)
        gsettings = tools / "gsettings"
        gsettings.write_text(f"#!{sys.executable}\n" + '''
import json, os, pathlib, sys
root = pathlib.Path(os.environ["TEST_POSTINSTALL_ROOT"])
args = sys.argv[1:]
assert args[1:3] == ["org.gnome.desktop.interface", "color-scheme"], args
with (root / "gsettings.jsonl").open("a") as output:
    output.write(json.dumps(args) + "\\n")
state = root / "gsettings-state"
if args[0] == "get":
    print(repr(state.read_text() if state.exists() else "default"))
elif args[0] == "writable":
    print("true")
elif args[0] == "set":
    state.write_text(args[3])
else:
    sys.exit("Unexpected GSettings command")
''')
        gsettings.chmod(0o755)
        self.env.update(PATH=str(tools), XDG_CACHE_HOME=str(self.root / "cache"),
                        XDG_STATE_HOME=str(self.root / "state"))
        self.env.pop("DBUS_SESSION_BUS_ADDRESS", None)

        result = self.setup(script=REPO / "scripts/setup/postinstall.sh")
        self.assert_success(result)
        colors = self.installed_theme() / "colors.lua"
        self.assertEqual(colors.read_bytes(), (REPO / "themes/bundled/tokyo-night/colors.lua").read_bytes())
        wallpaper = self.data_home() / "luna/wallpapers/hyprland-kath.png"
        bundled_wallpaper = REPO / "themes/bundled/tokyo-night/wallpapers/hyprland-kath.png"
        self.assertEqual(wallpaper.read_bytes(), bundled_wallpaper.read_bytes())
        resolved = self.config_home() / "luna/theme.json"
        self.assertEqual(json.loads(resolved.read_text())["name"], "tokyo-night")
        self.assertEqual(self.selection().read_text(), "tokyo-night\n")
        self.assertEqual((self.root / "gsettings-state").read_text(), "prefer-dark")

        colors.write_text(colors.read_text() + "\n-- Personal edits\n")
        marker = self.installed_theme() / "personal-marker"
        marker.write_text("Old installed copy\n")
        other = self.installed_theme().parent / "other-theme"
        other.mkdir()
        (other / "colors.lua").write_text("-- Unrelated theme\n")
        self.selection().write_text("another-theme\n")
        resolved.write_text('{"name": "another-theme"}\n')
        (self.root / "gsettings-state").write_text("prefer-light")
        self.assert_success(self.setup(script=REPO / "scripts/setup/postinstall.sh"))
        self.assertEqual(colors.read_bytes(), (REPO / "themes/bundled/tokyo-night/colors.lua").read_bytes())
        self.assertFalse(marker.exists())
        self.assertEqual((other / "colors.lua").read_text(), "-- Unrelated theme\n")
        self.assertEqual(self.selection().read_text(), "tokyo-night\n")
        self.assertEqual(json.loads(resolved.read_text())["name"], "tokyo-night")
        self.assertEqual((self.root / "gsettings-state").read_text(), "prefer-dark")
        self.assertEqual(wallpaper.read_bytes(), bundled_wallpaper.read_bytes())
        self.assertEqual(sorted(path.name for path in self.installed_theme().parent.iterdir()),
                         ["other-theme", "tokyo-night"])
        self.assertEqual(list(self.home.rglob("*.luna-backup*")), [])


if __name__ == "__main__":
    unittest.main()
