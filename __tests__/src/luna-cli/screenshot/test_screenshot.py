"""Exercise captures with fake Wayland tools; never read the real desktop or clipboard."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[4]
WORKER = REPO / "src/luna-cli/screenshot/screenshot.py"
SPEC = importlib.util.spec_from_file_location("screenshot", WORKER)
screenshot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(screenshot)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")


FAKE_TOOL = '''#!/usr/bin/env python3
import base64, json, os, pathlib, sys, time
root = pathlib.Path(os.environ["SCREENSHOT_TEST_ROOT"])
name = pathlib.Path(sys.argv[0]).name
with (root / "calls").open("a") as log:
    log.write(json.dumps([name] + sys.argv[1:]) + "\\n")
if name == "slurp":
    if os.environ.get("SLURP_BLOCK"):
        (root / "slurp-started").touch()
        while not pathlib.Path(os.environ["SLURP_BLOCK"]).exists():
            time.sleep(0.01)
    print(os.environ.get("SLURP_RESULT", "-50,30 640x480"))
    if os.environ.get("SLURP_ERROR"):
        print(os.environ["SLURP_ERROR"], file=sys.stderr)
    sys.exit(int(os.environ.get("SLURP_STATUS", "0")))
elif name == "hyprctl":
    defaults = {"layers": {}, "monitors": [{"name": "DP-1", "focused": False}, {"name": "eDP-1", "focused": True, "scale": 1.5, "transform": 1}], "activewindow": {"at": [-500, 40], "size": [800, 600], "mapped": True}}
    print(os.environ.get("HYPR_" + sys.argv[-1].upper(), json.dumps(defaults[sys.argv[-1]])))
elif name == "grim":
    data = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")
    pathlib.Path(sys.argv[-1]).write_bytes(b"partial" if os.environ.get("GRIM_PARTIAL") else data)
    if os.environ.get("GRIM_FAIL"):
        print("capture failed", file=sys.stderr)
        sys.exit(1)
elif name == "wl-copy":
    (root / "clipboard").write_bytes(sys.stdin.buffer.read())
    if os.environ.get("CLIPBOARD_FAIL"):
        print("clipboard unavailable", file=sys.stderr)
        sys.exit(1)
'''


class ScreenshotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna screenshot '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        tools = self.root / "tools"
        tools.mkdir()
        for name in ("grim", "slurp", "wl-copy", "hyprctl", "qs", "notify-send"):
            tool = tools / name
            tool.write_text(FAKE_TOOL)
            tool.chmod(0o755)
        self.environment = dict(os.environ, HOME=str(self.home), XDG_RUNTIME_DIR=str(self.root / "runtime"),
                                PATH=str(tools) + ":" + os.environ["PATH"], SCREENSHOT_TEST_ROOT=str(self.root))
        self.environment.pop("LUNA_SCREENSHOT_DIR", None)
        self.directory = self.home / "Pictures" / "Screenshots"

    def cli(self, *args, **environment):
        return subprocess.run([str(REPO / "bin/luna"), "screenshot", *args],
                              env=dict(self.environment, **environment), text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)

    def calls(self, tool=None):
        path = self.root / "calls"
        calls = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        return [call for call in calls if tool is None or call[0] == tool]

    def saved(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        path = Path(result.stdout.strip())
        self.assertEqual(path.parent, self.directory)
        self.assertEqual(path.suffix, ".png")
        self.assertEqual(path.read_bytes(), PNG)
        self.assertEqual((self.root / "clipboard").read_bytes(), PNG)
        return path

    def test_default_region_saves_and_copies_without_shell_expansion(self):
        path = self.saved(self.cli())
        self.assertEqual(self.calls("grim")[0], ["grim", "-t", "png", "-g", "-50,30 640x480", str(path)])
        self.assertEqual(self.calls("wl-copy")[0], ["wl-copy", "--type", "image/png"])
        self.assertEqual(self.calls("qs")[0], ["qs", "ipc", "-p", str(REPO / "src/launcher"), "call", "launcher", "close"])
        order = [call[0] for call in self.calls()]
        self.assertLess(order.index("qs"), order.index("slurp"))
        self.assertLess(order.index("slurp"), order.index("grim"))
        notice = self.calls("notify-send")[0]
        self.assertIn(f"--hint=string:image-path:{path}", notice)
        self.assertIn("--app-name=Luna Screenshot", notice)
        self.assertLess(order.index("wl-copy"), order.index("notify-send"))

    def test_screen_selects_focused_output_without_recalculating_scale(self):
        path = self.saved(self.cli("screen"))
        self.assertEqual(self.calls("grim")[0], ["grim", "-t", "png", "-o", "eDP-1", str(path)])
        self.assertFalse(self.calls("slurp"))

    def test_window_uses_active_window_geometry_with_negative_coordinates(self):
        path = self.saved(self.cli("window"))
        self.assertEqual(self.calls("grim")[0], ["grim", "-t", "png", "-g", "-500,40 800x600", str(path)])

    def test_all_captures_without_output_or_geometry_restriction(self):
        path = self.saved(self.cli("all"))
        self.assertEqual(self.calls("grim")[0], ["grim", "-t", "png", str(path)])
        self.assertEqual(self.calls("hyprctl"), [["hyprctl", "-j", "layers"]])

    def test_escape_cancels_silently_without_screenshot_files(self):
        for message in ("", "selection cancelled"):
            with self.subTest(message=message):
                result = self.cli(SLURP_STATUS="1", SLURP_ERROR=message, SLURP_RESULT="")
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))
                self.assertFalse(self.directory.exists())
                self.assertFalse(self.calls("grim"))
                self.assertFalse(self.calls("wl-copy"))
                self.assertFalse(self.calls("notify-send"))

    def test_slurp_failure_is_reported_instead_of_being_treated_as_cancel(self):
        result = self.cli(SLURP_STATUS="1", SLURP_ERROR="failed to connect to display")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("failed to connect to display", result.stderr)
        self.assertFalse(self.directory.exists())

    def test_invalid_region_cannot_become_a_grim_argument(self):
        result = self.cli(SLURP_RESULT="0,0 0x400; echo bad")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No usable screenshot region", result.stderr)
        self.assertFalse(self.calls("grim"))

    def test_capture_failure_cleans_partial_file_and_preserves_existing_images(self):
        self.directory.mkdir(parents=True)
        existing = self.directory / "existing.png"
        existing.write_bytes(PNG)
        result = self.cli("all", GRIM_FAIL="1", GRIM_PARTIAL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("capture failed", result.stderr)
        self.assertEqual(list(self.directory.iterdir()), [existing])
        self.assertFalse(self.calls("wl-copy"))

    def test_invalid_png_is_removed_even_if_grim_reports_success(self):
        result = self.cli("all", GRIM_PARTIAL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(self.directory.iterdir()), [])
        self.assertFalse(self.calls("wl-copy"))

    def test_clipboard_failure_keeps_saved_image_and_reports_its_path(self):
        result = self.cli("all", CLIPBOARD_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        files = list(self.directory.iterdir())
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].read_bytes(), PNG)
        self.assertIn(str(files[0]), result.stderr)
        self.assertIn("copying to the clipboard failed: clipboard unavailable", result.stderr)

    def test_missing_window_and_monitor_do_not_capture(self):
        for mode, environment in [("window", {"HYPR_ACTIVEWINDOW": "{}"}), ("screen", {"HYPR_MONITORS": "[]"})]:
            with self.subTest(mode=mode):
                result = self.cli(mode, **environment)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.calls("grim"))
                self.assertFalse(self.directory.exists())

    def test_geometry_rejects_zero_size_malformed_arrays_and_boolean_coordinates(self):
        for position, size in [([], [20, 30]), ([1, 2], [0, 10]), ([True, 2], [20, 30]), ([1.5, 2], [20, 30]), ([1, 2], [10, -1])]:
            with self.subTest(position=position, size=size), self.assertRaises(ValueError):
                screenshot.geometry(position, size)

    def test_repeated_timestamps_still_get_distinct_paths(self):
        with patch.dict(os.environ, self.environment, clear=True), patch.object(screenshot, "datetime") as clock:
            clock.now.return_value.strftime.return_value = "same-timestamp"
            first = screenshot.capture("all")
            second = screenshot.capture("all")
        self.assertNotEqual(first, second)
        self.assertEqual(first.read_bytes(), PNG)
        self.assertEqual(second.read_bytes(), PNG)

    def test_custom_directory_preserves_spaces_and_apostrophes(self):
        directory = self.root / "custom screenshots ' folder"
        result = self.cli("all", LUNA_SCREENSHOT_DIR=str(directory))
        self.assertEqual(result.returncode, 0, result.stderr)
        path = Path(result.stdout.strip())
        self.assertEqual(path.parent, directory)
        self.assertEqual(path.read_bytes(), PNG)

    def test_concurrent_request_cannot_start_another_selection(self):
        release = self.root / "release-slurp"
        first = subprocess.Popen([sys.executable, str(WORKER), "region"],
                                 env=dict(self.environment, SLURP_BLOCK=str(release)),
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 5
            while not (self.root / "slurp-started").exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue((self.root / "slurp-started").exists())
            second = self.cli("region")
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("already in progress", second.stderr)
            self.assertEqual(len(self.calls("slurp")), 1)
            release.touch()
            stdout, stderr = first.communicate(timeout=5)
            self.assertEqual(first.returncode, 0, stderr)
            self.assertEqual(Path(stdout.strip()).read_bytes(), PNG)
        finally:
            release.touch()
            if first.poll() is None:
                first.kill()
            first.communicate(timeout=5)

    def test_launcher_waits_for_removal_and_always_allows_animation_to_settle(self):
        layer = {"monitor": {"levels": {"2": [{"namespace": "luna-launcher"}]}}}
        with patch.object(screenshot.subprocess, "run"), patch.object(screenshot, "hyprland", side_effect=[layer, {}]), patch.object(screenshot.time, "sleep") as sleep:
            screenshot.hide_launcher()
        self.assertEqual(sleep.call_args_list[0].args, (0.2,))
        self.assertIn(((0.05,),), sleep.call_args_list)

    def test_visible_launcher_has_a_bounded_failure(self):
        layer = [{"namespace": "luna-menu-dismiss"}]
        with patch.object(screenshot.subprocess, "run"), patch.object(screenshot, "hyprland", return_value=layer), patch.object(screenshot.time, "sleep"), patch.object(screenshot.time, "monotonic", side_effect=[0, 2]):
            with self.assertRaisesRegex(ValueError, "menu did not close"):
                screenshot.hide_launcher()

    def test_clipboard_subprocess_does_not_inherit_pipes(self):
        path = self.root / "image.png"
        path.write_bytes(PNG)
        with patch.object(screenshot.subprocess, "run") as run:
            run.return_value.returncode = 0
            screenshot.copy_image(path)
        self.assertEqual(run.call_args.kwargs["stdout"], subprocess.DEVNULL)
        self.assertNotIn(run.call_args.kwargs["stderr"], (None, subprocess.PIPE))
        self.assertNotIn(run.call_args.kwargs["stdin"], (None, subprocess.PIPE))


if __name__ == "__main__":
    unittest.main()
