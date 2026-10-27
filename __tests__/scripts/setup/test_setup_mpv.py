"""Check isolated mpv deployment and the settings an installed mpv actually loads."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import wave

from __tests__.scripts.setup.app_fixture import copy_app_setup


REPO = Path(__file__).resolve().parents[3]


class SetupMpvTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna mpv '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.checkout = self.root / "checkout"
        copy_app_setup(self.checkout)
        self.source = self.checkout / "apps/mpv/config"
        self.config_home = self.home / ".config"
        self.active = self.config_home / "mpv"
        self.destination = self.config_home / "luna/mpv"
        self.env = dict(os.environ, HOME=str(self.home), XDG_CONFIG_HOME=str(self.config_home),
                        XDG_STATE_HOME=str(self.home / ".local/state"),
                        XDG_CACHE_HOME=str(self.home / ".cache"))
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

    def run_mpv(self, source, *arguments):
        script = self.root / "report.lua"
        script.write_text('''
local utils = require("mp.utils")
local function report(data)
    local output = assert(io.open(os.getenv("MPV_TEST_REPORT"), "w"))
    output:write(utils.format_json(data))
    output:close()
end
''' + source)
        report = self.root / "report.json"
        report.unlink(missing_ok=True)
        result = subprocess.run(
            [shutil.which("mpv"), "--idle=yes", "--vo=null", "--ao=null", "--load-scripts=no",
             "--terminal=no", "--script=" + str(script), *arguments], cwd=self.root,
            env=dict(self.env, MPV_TEST_REPORT=str(report)), capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(report.read_text())

    def report(self):
        data = self.run_mpv('''
mp.add_timeout(0, function()
    report({
        speed = mp.get_property_number("speed"),
        fullscreen = mp.get_property_bool("fullscreen"),
        osc = mp.get_property_bool("options/osc"),
        hwdec = mp.get_property("options/hwdec"),
        osd_scale_by_window = mp.get_property_bool("options/osd-scale-by-window"),
        osd_font_size = mp.get_property_number("options/osd-font-size"),
        osd_bar_w = mp.get_property_number("options/osd-bar-w"),
        osd_bar_h = mp.get_property_number("options/osd-bar-h"),
        osd_bar_align_y = mp.get_property_number("options/osd-bar-align-y"),
        bindings = mp.get_property_native("input-bindings"),
    })
    mp.commandv("quit")
end)
''')
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

    def test_personal_link_through_installed_config_is_rejected_before_publish(self):
        self.active.mkdir(parents=True)
        self.destination.mkdir(parents=True)
        external = self.root / "external-mpv.conf"
        external.write_text("# Preserve external config\n")
        installed = self.destination / "mpv.conf"
        installed.symlink_to(external)
        (self.active / "mpv.conf").symlink_to(installed)
        self.assertNotEqual(self.setup().returncode, 0)
        self.assertTrue(installed.is_symlink())
        self.assertEqual(external.read_text(), "# Preserve external config\n")

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
        self.assertIn("input-conf settings override Luna's key bindings", result.stderr)
        self.assertEqual(custom.read_text(), "UP add volume 3\n")

    @unittest.skipUnless(shutil.which("mpv"), "mpv is required for playback configuration validation")
    def test_real_mpv_loads_defaults_and_personal_overrides(self):
        self.assert_installed(self.setup())
        report = self.report()
        self.assertEqual(report["speed"], 2)
        self.assertTrue(report["fullscreen"])
        self.assertFalse(report["osc"])
        self.assertEqual(report["hwdec"], "auto-safe")
        self.assertFalse(report["osd_scale_by_window"])
        self.assertEqual(report["osd_font_size"], 24)
        self.assertEqual(report["osd_bar_w"], 50)
        self.assertEqual(report["osd_bar_h"], 1)
        self.assertAlmostEqual(report["osd_bar_align_y"], 0.8)
        self.assertEqual(report["bindings"]["UP"], "add volume 5")
        self.assertEqual(report["bindings"]["DOWN"], "add volume -5")
        with (self.active / "mpv.conf").open("a") as config:
            config.write("speed=1.25\nfullscreen=no\nosc=yes\nosd-font-size=30\n")
        with (self.active / "input.conf").open("a") as config:
            config.write("UP add volume 2\n")
        self.assert_installed(self.setup())
        report = self.report()
        self.assertEqual(report["speed"], 1.25)
        self.assertFalse(report["fullscreen"])
        self.assertTrue(report["osc"])
        self.assertEqual(report["osd_font_size"], 30)
        self.assertEqual(report["bindings"]["UP"], "add volume 2")

    @unittest.skipUnless(shutil.which("mpv"), "mpv is required for playback configuration validation")
    def test_real_mpv_bracket_keys_change_speed_by_quarter_steps(self):
        self.assert_installed(self.setup())
        report = self.run_mpv('''
mp.add_timeout(0, function()
    local speeds = {mp.get_property_number("speed")}
    mp.commandv("keypress", "]")
    mp.add_timeout(0.05, function()
        speeds[#speeds + 1] = mp.get_property_number("speed")
        mp.commandv("keypress", "[")
        mp.add_timeout(0.05, function()
            speeds[#speeds + 1] = mp.get_property_number("speed")
            report(speeds)
            mp.commandv("quit")
        end)
    end)
end)
''')
        self.assertEqual(report, [2, 2.25, 2])

    @unittest.skipUnless(shutil.which("mpv"), "mpv is required for playback configuration validation")
    def test_real_mpv_resumes_position_speed_and_volume_after_quit_or_first_close(self):
        self.assert_installed(self.setup())
        # A small local silence file exercises real seeks and watch-later state
        # without touching the user's media, audio device, or desktop windows.
        media = self.root / "resume sample.wav"
        with wave.open(str(media), "wb") as output:
            output.setparams((1, 1, 8000, 0, "NONE", "not compressed"))
            output.writeframes(b"\x80" * 8000 * 30)

        snapshot = '''
mp.register_event("file-loaded", function()
    mp.add_timeout(0.1, function()
        report({position = mp.get_property_number("time-pos"),
                speed = mp.get_property_number("speed"),
                volume = mp.get_property_number("volume")})
        mp.commandv("quit")
    end)
end)
'''
        for close in ('mp.commandv("quit")', 'mp.commandv("keypress", "CLOSE_WIN")',
                      'mp.commandv("keypress", "Meta+w")'):
            with self.subTest(close=close):
                before = self.run_mpv('''
mp.register_event("file-loaded", function()
    mp.set_property_number("speed", 2.75)
    mp.set_property_number("volume", 37)
    mp.commandv("seek", "12", "absolute+exact")
    mp.add_timeout(0.1, function()
        report({position = mp.get_property_number("time-pos"),
                speed = mp.get_property_number("speed"),
                volume = mp.get_property_number("volume")})
        ''' + close + '''
    end)
end)
''', "--pause=yes", str(media))
                self.assertAlmostEqual(before["position"], 12, delta=0.25)
                self.assertEqual(before["speed"], 2.75)
                self.assertEqual(before["volume"], 37)

                after = self.run_mpv(snapshot, "--pause=yes", str(media))
                # Audio buffering can round a paused seek by a fraction of a second.
                self.assertAlmostEqual(after["position"], before["position"], delta=0.25)
                self.assertEqual(after["speed"], 2.75)
                self.assertEqual(after["volume"], 37)

        # Remember settings per file, while keeping explicit launch overrides usable.
        other = self.root / "another sample.wav"
        shutil.copyfile(media, other)
        fresh = self.run_mpv(snapshot, "--pause=yes", str(other))
        self.assertEqual(fresh["speed"], 2)
        self.assertEqual(fresh["volume"], 100)
        overridden = self.run_mpv(snapshot, "--pause=yes", "--speed=1.5", "--volume=42", str(media))
        self.assertEqual(overridden["speed"], 1.5)
        self.assertEqual(overridden["volume"], 42)

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
        self.assertEqual(self.report()["speed"], 2)


if __name__ == "__main__":
    unittest.main()
