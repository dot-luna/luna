"""Check isolated mpv deployment and the settings an installed mpv actually loads."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]


class SetupMpvTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna mpv '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.checkout = self.root / "checkout"
        for name in ("scripts/setup/mpv.sh", "scripts/setup/mpv-config.py", "lib/common.sh"):
            destination = self.checkout / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, destination)
        self.source = self.checkout / "apps/mpv"
        shutil.copytree(REPO / "apps/mpv", self.source)
        self.config_home = self.home / ".config"
        self.active = self.config_home / "mpv"
        self.destination = self.config_home / "luna/mpv"
        self.env = dict(os.environ, HOME=str(self.home), XDG_CONFIG_HOME=str(self.config_home))
        for name in ("LUNA_CONFIG_DIR", "MPV_HOME"):
            self.env.pop(name, None)

    def setup(self, *arguments, entry=None):
        return subprocess.run(["bash", str(entry or self.checkout / "scripts/setup/mpv.sh"), *arguments],
                              env=self.env, cwd=self.root, input="", capture_output=True,
                              text=True, timeout=10)

    def assert_installed(self, result, destination=None):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for name in ("mpv.conf", "input.conf"):
            path = (destination or self.destination) / name
            self.assertFalse(path.is_symlink())
            self.assertEqual(path.read_bytes(), (self.source / name).read_bytes())

    def report(self):
        script = self.root / "report.lua"
        script.write_text('''
local utils = require("mp.utils")
mp.add_timeout(0, function()
    local output = assert(io.open(os.getenv("MPV_TEST_REPORT"), "w"))
    output:write(utils.format_json({
        speed = mp.get_property_number("speed"),
        fullscreen = mp.get_property_bool("fullscreen"),
        osc = mp.get_property_bool("options/osc"),
        bindings = mp.get_property_native("input-bindings"),
    }))
    output:close()
    mp.commandv("quit")
end)
''')
        report = self.root / "report.json"
        result = subprocess.run(
            [shutil.which("mpv"), "--idle=yes", "--vo=null", "--ao=null", "--load-scripts=no",
             "--terminal=no", "--script=" + str(script)], cwd=self.root,
            env=dict(self.env, MPV_TEST_REPORT=str(report)), capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = json.loads(report.read_text())
        data["bindings"] = {binding["key"]: binding["cmd"] for binding in data["bindings"]
                            if not binding["is_weak"]}
        return data

    def test_default_deployment_and_ignored_arguments_are_idempotent(self):
        self.env.pop("XDG_CONFIG_HOME")
        entry = self.root / "setup mpv"
        entry.symlink_to(self.checkout / "scripts/setup/mpv.sh")
        self.assert_installed(self.setup("--help", "--unknown", entry=entry))
        originals = {name: (self.active / name).read_bytes() for name in ("mpv.conf", "input.conf")}
        before = {name: (self.active / name).stat().st_mtime_ns for name in originals}
        self.assert_installed(self.setup())
        for name, original in originals.items():
            self.assertEqual((self.active / name).read_bytes(), original)
            self.assertEqual((self.active / name).stat().st_mtime_ns, before[name])
        self.assertIn(b"UP add volume 5\nDOWN add volume -5\n", originals["input.conf"])
        self.assertEqual(list(self.home.rglob("*.luna-backup*")), [])

    def test_personal_bytes_modes_and_symlinks_survive_default_refresh(self):
        actual = self.root / "personal"
        actual.mkdir()
        self.config_home.mkdir()
        self.active.symlink_to(actual)
        originals = {"mpv.conf": b"# Personal caf\xc3\xa9\r\nspeed=1.25",
                     "input.conf": b"# Personal bindings\r\nUP add volume 2"}
        for name, content in originals.items():
            target = self.root / (name + ".personal")
            target.write_bytes(content)
            target.chmod(0o640)
            (actual / name).symlink_to(target)
        for _ in range(2):
            self.assert_installed(self.setup())
            for name, original in originals.items():
                path = self.active / name
                self.assertTrue(path.is_symlink())
                self.assertTrue(path.read_bytes().endswith(original))
                self.assertEqual(path.stat().st_mode & 0o777, 0o640)
                self.assertEqual(path.read_bytes().count(b"# >>> Luna mpv >>>"), 1)
        (self.source / "input.conf").write_text("# Updated controls\nUP add volume 7")
        self.assert_installed(self.setup())
        self.assert_installed(self.setup())
        self.assertIn(b"UP add volume 7\n", (self.active / "input.conf").read_bytes())
        self.assertTrue((self.active / "input.conf").read_bytes().endswith(originals["input.conf"]))

    def test_existing_legacy_configuration_is_used_without_creating_xdg_config(self):
        legacy = self.home / ".mpv"
        legacy.mkdir()
        (legacy / "mpv.conf").write_text("speed=1.25\n")
        (legacy / "input.conf").write_text("UP add volume 2\n")
        self.assert_installed(self.setup())
        self.assertFalse(self.active.exists())
        self.assertIn(b"fullscreen=yes", (legacy / "mpv.conf").read_bytes())
        self.assertIn(b"DOWN add volume -5", (legacy / "input.conf").read_bytes())

    def test_mpv_home_and_custom_luna_directory(self):
        self.env["MPV_HOME"] = str(self.root / "custom mpv")
        self.env["LUNA_CONFIG_DIR"] = str(self.root / "custom luna")
        self.assert_installed(self.setup(), Path(self.env["LUNA_CONFIG_DIR"]) / "mpv")
        self.assertTrue((Path(self.env["MPV_HOME"]) / "mpv.conf").is_file())
        self.assertTrue((Path(self.env["MPV_HOME"]) / "input.conf").is_file())
        self.assertFalse(self.active.exists())

    def test_relative_configuration_directories_are_rejected(self):
        for name in ("XDG_CONFIG_HOME", "LUNA_CONFIG_DIR", "MPV_HOME"):
            with self.subTest(name=name):
                previous = self.env.get(name)
                self.env[name] = "relative config"
                self.assertNotEqual(self.setup().returncode, 0)
                self.assertFalse(self.destination.exists())
                if previous is None:
                    self.env.pop(name)
                else:
                    self.env[name] = previous

    def test_missing_source_and_directory_conflicts_preserve_existing_files(self):
        self.assert_installed(self.setup())
        before = (self.destination / "mpv.conf").read_bytes()
        original_input = (self.source / "input.conf").read_bytes()
        (self.source / "input.conf").unlink()
        self.assertNotEqual(self.setup().returncode, 0)
        self.assertEqual((self.destination / "mpv.conf").read_bytes(), before)
        (self.source / "input.conf").write_bytes(original_input)
        (self.source / "mpv.conf").write_text("speed=2\n")
        (self.destination / "input.conf").unlink()
        (self.destination / "input.conf").mkdir()
        self.assertNotEqual(self.setup().returncode, 0)
        self.assertEqual((self.destination / "mpv.conf").read_bytes(), before)

    def test_destination_directory_symlink_is_rejected(self):
        self.destination.parent.mkdir(parents=True)
        foreign = self.root / "foreign"
        foreign.mkdir()
        self.destination.symlink_to(foreign)
        self.assertNotEqual(self.setup().returncode, 0)
        self.assertEqual(list(foreign.iterdir()), [])

    def test_destination_file_symlinks_are_replaced_without_touching_targets(self):
        self.destination.mkdir(parents=True)
        foreign = self.root / "personal.conf"
        foreign.write_text("Keep personal contents\n")
        for name in ("mpv.conf", "input.conf"):
            (self.destination / name).symlink_to(foreign)
        self.assert_installed(self.setup())
        self.assertEqual(foreign.read_text(), "Keep personal contents\n")

    def test_checkout_and_active_destination_overlap_are_rejected(self):
        for directory in (self.checkout / "apps", self.config_home):
            with self.subTest(directory=directory):
                self.env["LUNA_CONFIG_DIR"] = str(directory)
                self.assertNotEqual(self.setup().returncode, 0)
                self.assertFalse(self.active.exists())

    def test_personal_symlink_into_installed_config_is_rejected_before_changes(self):
        self.assert_installed(self.setup())
        before = (self.destination / "mpv.conf").read_bytes()
        (self.active / "mpv.conf").unlink()
        (self.active / "mpv.conf").symlink_to(self.destination / "mpv.conf")
        (self.source / "mpv.conf").write_text("speed=2\n")
        self.assertNotEqual(self.setup().returncode, 0)
        self.assertEqual((self.destination / "mpv.conf").read_bytes(), before)

    def test_malformed_managed_block_fails_before_installing(self):
        self.active.mkdir(parents=True)
        original = b"# >>> Luna mpv >>>\nspeed=1.25\n"
        (self.active / "mpv.conf").write_bytes(original)
        self.assertNotEqual(self.setup().returncode, 0)
        self.assertEqual((self.active / "mpv.conf").read_bytes(), original)
        self.assertFalse(self.destination.exists())

    def test_custom_input_file_is_preserved_with_actionable_warning(self):
        self.active.mkdir(parents=True)
        custom = self.root / "custom-input.conf"
        custom.write_text("UP add volume 3\n")
        (self.active / "mpv.conf").write_text('input-conf="' + str(custom) + '"\n')
        result = self.setup()
        self.assert_installed(result)
        self.assertIn("input-conf settings override Luna's volume bindings", result.stderr)
        self.assertEqual(custom.read_text(), "UP add volume 3\n")

    @unittest.skipUnless(shutil.which("mpv"), "mpv is required for playback configuration validation")
    def test_real_mpv_loads_defaults_and_personal_overrides(self):
        self.assert_installed(self.setup())
        report = self.report()
        self.assertEqual(report["speed"], 1.75)
        self.assertTrue(report["fullscreen"])
        self.assertFalse(report["osc"])
        self.assertEqual(report["bindings"]["UP"], "add volume 5")
        self.assertEqual(report["bindings"]["DOWN"], "add volume -5")
        with (self.active / "mpv.conf").open("a") as config:
            config.write("speed=1.25\nfullscreen=no\nosc=yes\n")
        with (self.active / "input.conf").open("a") as config:
            config.write("UP add volume 2\n")
        self.assert_installed(self.setup())
        report = self.report()
        self.assertEqual(report["speed"], 1.25)
        self.assertFalse(report["fullscreen"])
        self.assertTrue(report["osc"])
        self.assertEqual(report["bindings"]["UP"], "add volume 2")

    @unittest.skipUnless(shutil.which("mpv"), "mpv is required for playback configuration validation")
    def test_real_mpv_uses_legacy_settings_and_input_fallback_with_xdg_directory(self):
        legacy = self.home / ".mpv"
        legacy.mkdir()
        self.active.mkdir(parents=True)
        (legacy / "mpv.conf").write_text("speed=1.25\n")
        (legacy / "input.conf").write_text("UP add volume 2\n")
        (self.active / "mpv.conf").write_text("speed=1.5\n")
        self.assert_installed(self.setup())
        self.assertEqual((self.active / "mpv.conf").read_text(), "speed=1.5\n")
        self.assertFalse((self.active / "input.conf").exists())
        report = self.report()
        self.assertEqual(report["speed"], 1.5)
        self.assertTrue(report["fullscreen"])
        self.assertEqual(report["bindings"]["UP"], "add volume 2")
        self.assertEqual(report["bindings"]["DOWN"], "add volume -5")

    @unittest.skipUnless(shutil.which("mpv"), "mpv is required for playback configuration validation")
    def test_real_mpv_configuration_accepts_unusual_paths(self):
        self.env["LUNA_CONFIG_DIR"] = str(self.root / "Luna caf\u00e9 # $HOME % \' \" \\ configs")
        self.assert_installed(self.setup(), Path(self.env["LUNA_CONFIG_DIR"]) / "mpv")
        self.assertEqual(self.report()["speed"], 1.75)


if __name__ == "__main__":
    unittest.main()
