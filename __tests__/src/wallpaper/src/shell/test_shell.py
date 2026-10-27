"""Test TOML loading, media routing, and image rendering without using the desktop.

Run from the repository root:
    python3 -m unittest discover -s __tests__/src/wallpaper/src/shell -p test_shell.py -v

Tests copy the production shell into a temporary directory, replace its layer
window for offscreen Qt, and stub video playback. They do not verify Wayland
placement or real video rendering.
"""

import json
import os
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import tempfile
import textwrap
import time
import unittest
import zlib


ROOT = Path(__file__).resolve().parents[5]

# Added only to the copied shell: expose renderer state and inject activity/errors
# through IPC without adding test-only methods to production QML.
INSPECTOR = '''
    IpcHandler {
        target: "test"
        function state(): string {
            const windows = [];
            const images = [];
            const videos = [];
            const seen = [];
            function visit(item) {
                if (!item || seen.indexOf(item) !== -1) return;
                seen.push(item);
                if (item.objectName === "fake-video") videos.push({source: item.sourcePath});
                if (item.source !== undefined && item.sourceSize !== undefined) {
                    images.push({source: String(item.source), status: item.status,
                        width: item.sourceSize.width, height: item.sourceSize.height,
                        displayWidth: item.width, displayHeight: item.height,
                        scale: item.parent.scale, opacity: item.parent.opacity, z: item.parent.z,
                        frameCount: item.frameCount || 0, currentFrame: item.currentFrame || 0,
                        playing: item.playing || false, paused: item.paused || false});
                }
                if (item.contentItem) visit(item.contentItem);
                for (const child of (item.children || [])) visit(child);
            }
            windows.push({visible: surface.visible, color: String(surface.color),
                width: surface.width, height: surface.height, dpr: surface.screen.devicePixelRatio});
            visit(surface);
            return JSON.stringify({path: shell.configPath, config: shell.config,
                status: shell.configStatus, kind: surface.kind, windows: windows, images: images, videos: videos,
                settings: surface.settings, screens: Quickshell.screens.map(screen => screen.name)});
        }
        function reload(): string {
            wallpaperApi.reload();
            return wallpaperApi.status();
        }
        function outputActive(value: bool): void {
            surface.monitor = {lastIpcObject: {dpmsStatus: value}};
        }
        function lateDecodeError(): void {
            surface.decoded(surface.frontSlot, Image.Error);
        }
    }
'''


@unittest.skipUnless(all(shutil.which(tool) for tool in ("qs", "dbus-run-session", "ffprobe")),
                     "Quickshell, dbus-run-session, and FFmpeg required")
class WallpaperShellTests(unittest.TestCase):
    def setUp(self):
        """Prepare a disposable shell, private user directories, and a native-size PNG."""
        self.temp = tempfile.TemporaryDirectory(prefix="luna wallpaper ' ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.renderer = self.root / "src/wallpaper/src/shell"

        # Instrument a private copy so tests cannot alter the user's installed shell.
        shutil.copytree(ROOT / "src/wallpaper/src", self.renderer.parent)
        shutil.copytree(ROOT / "lib", self.root / "lib")
        shell = self.renderer / "shell.qml"
        # Preserve the checkout layout so Lua uses the production defaults and schema.
        self.defaults = self.root / "apps/luna-wallpaper/config/wallpaper.toml"
        self.defaults.parent.mkdir(parents=True)
        shutil.copy(ROOT / "apps/luna-wallpaper/config/wallpaper.toml", self.defaults)
        source = shell.read_text()
        self.assertTrue(source.rstrip().endswith("}"))
        source = source.replace('target: "wallpaper"', 'id: wallpaperApi\n        target: "wallpaper"', 1)
        shell.write_text(source.rstrip()[:-1] + INSPECTOR + "}\n")

        # Offscreen Qt has no layer-shell backend; keep the real renderer in an ordinary window.
        surface = self.renderer / "WallpaperSurface.qml"
        source = surface.read_text().replace("PanelWindow {", "FloatingWindow {\n    implicitWidth: 800\n    implicitHeight: 600", 1)
        source = "\n".join(line for line in source.splitlines() if not line.strip().startswith((
            "anchors {", "exclusionMode:", "WlrLayershell.")))
        source = source.replace("readonly property var monitor: hasHyprland ? Hyprland.monitorFor(screen) : null",
                                "property var monitor: null")
        surface.write_text(source)

        # Video process behavior has its own tests; routing tests must never start a real player.
        (self.renderer / "VideoWallpaper.qml").write_text('''import QtQuick
Item {
    objectName: "fake-video"
    property string sourcePath: ""
    property string outputName: ""
    property string fit: ""
    property string backgroundColor: "#000000"
    property bool paused: false
    property bool active: false
    property string status: "loading"
    signal failed(string message)
    Component.onCompleted: status = "ready"
}
''')

        # Remove desktop endpoints and keep config, logs, and caches inside the fixture.
        runtime = self.root / "runtime"
        runtime.mkdir(mode=0o700)
        home = self.root / "home"
        home.mkdir()
        self.env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QS_NO_RELOAD_POPUP="1",
                        HOME=str(home), XDG_RUNTIME_DIR=str(runtime),
                        XDG_CONFIG_HOME=str(self.root / "config"),
                        XDG_CONFIG_DIRS=str(self.root / "system-config"),
                        XDG_CACHE_HOME=str(self.root / "cache"),
                        XDG_DATA_HOME=str(self.root / "data"),
                        XDG_STATE_HOME=str(self.root / "state"),
                        DBUS_SYSTEM_BUS_ADDRESS="unix:path=/nonexistent-luna-wallpaper-test-bus")
        for name in ("LUNA_WALLPAPER_CONFIG", "WAYLAND_DISPLAY", "DISPLAY",
                     "HYPRLAND_INSTANCE_SIGNATURE", "QT_LOGGING_RULES"):
            self.env.pop(name, None)
        self.log_path = self.root / "shell.log"
        self.process = None
        self.addCleanup(self.stop)

        # Larger than the test window: decoded dimensions reveal accidental downsampling.
        # Spaces and quotes also exercise paths without shell interpolation.
        self.image_path = self.root / "wallpaper ' image.png"
        def chunk(kind, data):
            return struct.pack("!I", len(data)) + kind + data + struct.pack("!I", zlib.crc32(kind + data))
        header = struct.pack("!IIBBBBB", 1600, 900, 8, 2, 0, 0, 0)
        pixels = zlib.compress((b"\x00" + b"\xff\x00\x00" * 1600) * 900)
        self.image_path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
                                    + chunk(b"IDAT", pixels) + chunk(b"IEND", b""))

    def write_config(self, path=None, extra=""):
        """Write explicit test settings; the renderer must never create this file itself."""
        path = path or Path(self.env["XDG_CONFIG_HOME"]) / "luna/wallpaper.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[wallpaper]\nsource = " + json.dumps(str(self.image_path))
                        + '\nfit = "fit"\nbackground_color = "#102030"\n' + extra)
        return path

    def write_animation(self, path):
        """Create two 50 ms GIF frames without a loop extension or imaging dependency."""
        header = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff"
        def frame(pixel):
            return (b"\x21\xf9\x04\x00\x05\x00\x00\x00\x2c\x00\x00\x00\x00"
                    b"\x01\x00\x01\x00\x00\x02\x02" + bytes((pixel, 1)) + b"\x00")
        path.write_bytes(header + frame(0x44) + frame(0x4c) + b"\x3b")
        return path

    def mock_probe(self, records):
        """Override ffprobe with per-path metadata, delays, and failures for routing tests."""
        directory = self.root / "tools"
        directory.mkdir(exist_ok=True)
        (self.root / "probe-options.json").write_text(json.dumps(records))
        executable = directory / "ffprobe"
        executable.write_text(textwrap.dedent('''\
            #!/usr/bin/python3
            import json, os, pathlib, sys, time
            root = pathlib.Path(os.environ["LUNA_WALLPAPER_PROBE_TEST"])
            path = sys.argv[sys.argv.index("-i") + 1]
            with (root / "probe-calls").open("a") as calls:
                calls.write(path + "\\n")
            options = json.loads((root / "probe-options.json").read_text())[path]
            time.sleep(options.get("delay", 0))
            print(options.get("output", json.dumps(options.get("metadata", {}))))
            sys.exit(options.get("exit", 0))
        '''))
        executable.chmod(0o755)
        self.env["PATH"] = str(directory) + ":" + os.environ["PATH"]
        self.env["LUNA_WALLPAPER_PROBE_TEST"] = str(self.root)

    def hold_config_reads(self):
        """Gate copied TOML reads to make reload cancellation races deterministic."""
        parser = self.root / "lib/toml.lua"
        source = parser.read_text().replace('import json, os, pathlib, stat, subprocess, sys, tempfile',
                                            'import json, os, pathlib, stat, subprocess, sys, tempfile, time')
        marker = '    # Merge tables recursively;'
        source = source.replace(marker, '''    gate = pathlib.Path(str(path) + '.hold')
    if gate.exists():
        with pathlib.Path(str(path) + '.pids').open('a') as readers:
            readers.write(str(os.getpid()) + '\\n')
        pathlib.Path(str(path) + '.read').write_text(json.dumps(document.unwrap()))
        while gate.exists(): time.sleep(0.01)

''' + marker)
        parser.write_text(source)

    @staticmethod
    def reader_alive(pid):
        """Treat an exited child awaiting reaping as stopped too."""
        try:
            state = (Path('/proc') / str(pid) / 'stat').read_text().split(') ', 1)[1][0]
            return state != 'Z'
        except FileNotFoundError:
            return False

    def start(self, wait_loaded=True):
        """Launch only the isolated shell and optionally wait for its initial config read."""
        self.stop()
        self.log = self.log_path.open("w")
        self.process = subprocess.Popen(["dbus-run-session", "--", "qs", "-p", str(self.renderer)],
                                        env=self.env, stdout=self.log, stderr=subprocess.STDOUT,
                                        start_new_session=True)
        self.until(lambda: self.ipc("state", target="test", check=False).stdout.startswith("{"))
        if wait_loaded:
            self.until(lambda: self.state()["status"] in ("ready", "error"))
        return self.state()

    def stop(self):
        """End the private session and its children before removing temporary files."""
        if self.process is None:
            return
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        self.process.wait(timeout=5)
        self.log.close()
        self.process = None

    def ipc(self, method, *arguments, target="wallpaper", check=True):
        """Address the copied shell by path so IPC cannot target the user's shell."""
        return subprocess.run(["qs", "ipc", "-p", str(self.renderer), "call", target,
                               method, *arguments], env=self.env, capture_output=True,
                              text=True, timeout=3, check=check)

    def select(self, source):
        """Edit only the fixture's user file, then explicitly reload the copied shell."""
        path = self.state()["path"]
        subprocess.run(["/usr/bin/lua", "-E", "-", str(ROOT), path, str(source)],
                       input='local root, path, source = arg[1], arg[2], arg[3]\n'
                             'local json = dofile(root .. "/lib/json.lua")\n'
                             'local toml = dofile(root .. "/lib/toml.lua")(dofile(root .. "/lib/common.lua"), json)\n'
                             'toml.update(path, {wallpaper = {source = source}})\n',
                       env=self.env, text=True, capture_output=True, check=True, timeout=5)
        return self.ipc("reload", target="test")

    def state(self):
        """Read the test-only snapshot of config, media, and window state."""
        return json.loads(self.ipc("state", target="test").stdout)

    def until(self, predicate):
        """Bound asynchronous waits and include the shell log when an expectation fails."""
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if predicate():
                return
            if self.process.poll() is not None:
                break
            time.sleep(0.02)
        self.fail("Wallpaper condition failed: " + self.log_path.read_text())

    def assert_dark(self, state):
        """Require a visible black fallback rather than a missing wallpaper window."""
        self.assertTrue(state["windows"])
        self.assertEqual(len(state["windows"]), 1)
        self.assertTrue(all(window["visible"] and window["color"] == "#000000"
                            for window in state["windows"]))

    # Config precedence, validation errors, and explicit reloads.
    def test_explicit_config_path_preserves_nested_options_and_original_files(self):
        path = self.write_config(self.root / "custom ' wallpaper.toml", '''
[playback]
pause_when_output_inactive = true
[transition]
type = "none"
duration_ms = 0
[outputs."not-connected".wallpaper]
fit = "center"
''')
        self.write_config().write_text("this config must not be read")
        self.env["LUNA_WALLPAPER_CONFIG"] = str(path)
        original_config = path.read_bytes()
        original_image = self.image_path.read_bytes()
        state = self.start()
        self.assertEqual(state["status"], "ready")
        self.assertEqual(state["path"], str(path))
        self.assertEqual(state["config"]["wallpaper"]["source"], str(self.image_path))

        # Keep future monitor options in parsed data, but use global settings today.
        self.assertEqual(state["config"]["outputs"]["not-connected"]["wallpaper"]["fit"], "center")
        output = state["settings"]
        self.assertEqual(output["wallpaper"]["fit"], "fit")
        self.assertEqual(output["wallpaper"]["source"], str(self.image_path))
        self.assertEqual(output["wallpaper"]["background_color"], "#102030")
        self.assertTrue(output["playback"]["pause_when_output_inactive"])
        self.until(lambda: any(image["status"] == 1 for image in self.state()["images"]))
        images = [image for image in self.state()["images"] if image["status"] == 1]
        self.assertTrue(all((image["width"], image["height"]) == (1600, 900) for image in images))
        self.assertEqual(path.read_bytes(), original_config)
        self.assertEqual(self.image_path.read_bytes(), original_image)

    def test_empty_override_uses_xdg_config_home(self):
        path = self.write_config()
        self.env["LUNA_WALLPAPER_CONFIG"] = ""
        state = self.start()
        self.assertEqual(state["path"], str(path))
        self.assertEqual(state["status"], "ready")

    def test_empty_or_unset_xdg_config_home_uses_home(self):
        path = self.write_config(Path(self.env["HOME"]) / ".config/luna/wallpaper.toml")
        for value in (None, ""):
            with self.subTest(xdg_config_home=value):
                if value is None:
                    self.env.pop("XDG_CONFIG_HOME", None)
                else:
                    self.env["XDG_CONFIG_HOME"] = value
                state = self.start()
                self.assertEqual(state["path"], str(path))
                self.assertEqual(state["status"], "ready")
                self.stop()

    def test_missing_invalid_and_unreadable_config_stay_dark_and_log_to_disk(self):
        path = Path(self.env["XDG_CONFIG_HOME"]) / "luna/wallpaper.toml"
        for failure in ("missing", "invalid", "directory"):
            with self.subTest(failure=failure):
                if failure == "invalid":
                    path.parent.mkdir(parents=True)
                    path.write_text("[wallpaper\n")
                elif failure == "directory":
                    path.unlink()
                    path.mkdir()
                state = self.start()
                self.assertEqual(state["status"], "error")
                self.assertIsNone(state["config"])
                self.assert_dark(state)

                # Read Quickshell's file log, not just this test's captured stdout.
                result = subprocess.run(["qs", "log", "-p", str(self.renderer), "--no-color"],
                                        env=self.env, text=True, capture_output=True, timeout=3, check=True)
                self.assertIn("WARN", result.stdout)
                self.assertIn("Wallpaper config " + str(path), result.stdout)
                if failure == "missing":
                    self.assertFalse(path.exists())
                    self.assertFalse(path.parent.exists())
                self.stop()

    def test_config_changes_are_loaded_only_after_manual_reload(self):
        path = self.write_config()
        first = self.start()["config"]
        process = self.process.pid
        path.write_text(path.read_text().replace('fit = "fit"', 'fit = "tile"'))
        time.sleep(0.35)
        self.assertEqual(self.state()["config"], first)
        self.assertEqual(self.ipc("reload", target="test").stdout.strip(), "loading")
        self.until(lambda: self.ipc("status").stdout.strip() == "ready")
        self.assertEqual(self.state()["config"]["wallpaper"]["fit"], "tile")
        self.assertEqual(self.process.pid, process)

    def test_reload_applies_disk_settings(self):
        path = self.write_config()
        self.start()
        self.until(lambda: self.ipc("status").stdout.strip() == "ready")

        replacement = self.root / "replacement.png"
        replacement.write_bytes(self.image_path.read_bytes())
        content = path.read_text().replace(str(self.image_path), str(replacement))
        content = content.replace('fit = "fit"', 'fit = "stretch"').replace("#102030", "#405060")
        path.write_text(content)
        self.ipc("reload")
        self.until(lambda: self.ipc("status").stdout.strip() == "ready")
        state = self.state()
        self.assertEqual(state["settings"]["wallpaper"], {
            "source": str(replacement), "fit": "stretch", "background_color": "#405060"})
        self.assertEqual(state["windows"][0]["color"], "#405060")
        self.until(lambda: len(self.state()["images"]) == 1)
        self.assertTrue(self.state()["images"][0]["source"].endswith("/replacement.png"))
        self.assertEqual(path.read_text(), content)

    def test_reload_failure_clears_media_then_recovers(self):
        path = self.write_config()
        content = path.read_text()
        self.start()
        self.until(lambda: self.ipc("status").stdout.strip() == "ready")
        path.write_text("[wallpaper\n")
        self.ipc("reload")
        self.until(lambda: self.ipc("status").stdout.strip() == "error")
        state = self.state()
        self.assertIsNone(state["config"])
        self.assert_dark(state)
        self.assertEqual(state["images"], [])
        result = subprocess.run(["qs", "log", "-p", str(self.renderer), "--no-color"],
                                env=self.env, text=True, capture_output=True, timeout=3, check=True)
        self.assertIn("Wallpaper config " + str(path), result.stdout)

        path.write_text(content)
        self.ipc("reload")
        self.until(lambda: self.ipc("status").stdout.strip() == "ready")
        self.assertEqual(self.state()["settings"]["wallpaper"]["source"], str(self.image_path))

    def test_file_edits_after_read_begins_need_another_explicit_reload(self):
        path = self.write_config()
        self.hold_config_reads()
        self.start()
        hold = Path(str(path) + ".hold")
        read = Path(str(path) + ".read")
        hold.touch()
        self.addCleanup(hold.unlink, missing_ok=True)
        path.write_text(path.read_text().replace('fit = "fit"', 'fit = "tile"'))
        self.ipc("reload")
        self.until(read.exists)
        self.assertEqual(self.ipc("status").stdout.strip(), "loading")
        path.write_text(path.read_text().replace(json.dumps(str(self.image_path)), '""'))
        hold.unlink()
        self.until(lambda: self.ipc("status").stdout.strip() == "ready")
        self.assertEqual(self.state()["settings"]["wallpaper"]["source"], str(self.image_path))
        self.ipc("reload")
        self.until(lambda: self.ipc("status").stdout.strip() == "ready")
        self.assertEqual(self.state()["settings"]["wallpaper"], {
            "source": "", "fit": "tile", "background_color": "#102030"})

    def test_repeated_reload_cancels_older_reads(self):
        path = self.write_config()
        self.hold_config_reads()
        self.start()
        hold = Path(str(path) + ".hold")
        read = Path(str(path) + ".read")
        hold.touch()
        self.addCleanup(hold.unlink, missing_ok=True)
        self.ipc("reload")
        self.until(read.exists)

        # The latest request must reread the new file and discard earlier parser results.
        content = path.read_text().replace('fit = "fit"', 'fit = "center"').replace("#102030", "#708090")
        path.write_text(content)
        read.unlink()
        for _ in range(4):
            self.ipc("reload")
        self.until(read.exists)
        self.assertEqual(json.loads(read.read_text())["wallpaper"]["fit"], "center")
        pids = [int(pid) for pid in Path(str(path) + ".pids").read_text().splitlines()]
        self.assertGreaterEqual(len(pids), 2)
        self.until(lambda: all(not self.reader_alive(pid) for pid in pids[:-1]))
        self.assertTrue(self.reader_alive(pids[-1]))
        hold.unlink()
        self.until(lambda: self.ipc("status").stdout.strip() == "ready")
        state = self.state()
        self.assertEqual(state["settings"]["wallpaper"], {
            "source": str(self.image_path), "fit": "center", "background_color": "#708090"})
        self.assertNotIn("Could not run the config reader", self.log_path.read_text())

    def test_reader_timeout_stops_children_and_recovers_after_reload(self):
        path = self.write_config()
        self.hold_config_reads()
        shell = self.renderer / "shell.qml"
        shell.write_text(shell.read_text().replace('"10s"', '"1s"'))
        hold = Path(str(path) + ".hold")
        hold.touch()
        self.addCleanup(hold.unlink, missing_ok=True)
        self.start(wait_loaded=False)
        self.until(Path(str(path) + ".read").exists)
        pid = int(Path(str(path) + ".pids").read_text().strip())
        self.until(lambda: self.ipc("status").stdout.strip() == "error")
        self.until(lambda: not self.reader_alive(pid))
        self.assert_dark(self.state())
        self.assertIn("Config reader timed out", self.log_path.read_text())

        hold.unlink()
        self.ipc("reload")
        self.until(lambda: self.ipc("status").stdout.strip() == "ready")

    def test_empty_config_uses_app_defaults_without_writing_them(self):
        self.write_config().write_text("")
        state = self.start()
        self.assertEqual(state["status"], "ready")
        self.assertEqual(state["config"]["wallpaper"]["source"], "")
        self.assertEqual(state["config"]["wallpaper"]["fit"], "fill")
        self.assert_dark(state)
        self.assertFalse(any(image["source"] for image in state["images"]))

    def test_renderer_uses_the_shared_app_defaults(self):
        self.defaults.write_text(self.defaults.read_text().replace('fit = "fill"', 'fit = "tile"')
                                 .replace('duration_ms = 200', 'duration_ms = 77'))
        path = self.write_config()
        path.write_text(path.read_text().replace('fit = "fit"\n', ''))
        settings = self.start()["settings"]
        self.assertEqual(settings["wallpaper"]["fit"], "tile")
        self.assertEqual(settings["transition"]["duration_ms"], 77)
        self.assertNotIn('fit =', path.read_text())

    def test_invalid_values_and_section_types_fail_dark_without_rewriting(self):
        path = self.write_config()
        for invalid in ('[wallpaper]\nfit = "invalid"',
                        '[wallpaper]\nsource = 12',
                        '[transition]\nduration_ms = nan',
                        '[transition]\nduration_ms = 2026-10-27',
                        '[playback]\npause_when_output_inactive = "false"',
                        'wallpaper = []', 'playback = ["wrong"]', 'transition = 12'):
            with self.subTest(config=invalid):
                path.write_text(invalid + '\n')
                original = path.read_bytes()
                state = self.start()
                self.assertEqual(state["status"], "error")
                self.assertIsNone(state["config"])
                self.assertIsNone(state["settings"])
                self.assert_dark(state)
                self.assertEqual(state["images"], [])
                self.assertIn("Invalid wallpaper config", self.log_path.read_text())
                self.assertEqual(path.read_bytes(), original)
                self.stop()

    def test_unknown_options_remain_in_the_lua_result(self):
        path = self.write_config(extra='[future]\nvalues = [1, 2]\n')
        path.write_text('outputs = false\n' + path.read_text().replace('fit = "fit"', 'fit = "fit"\nextra = true'))
        before = path.read_bytes()
        state = self.start()
        self.assertEqual(state["status"], "ready")
        self.assertEqual(state["settings"], state["config"])
        self.assertEqual(state["settings"]["future"]["values"], [1, 2])
        self.assertTrue(state["settings"]["wallpaper"]["extra"])
        self.assertIs(state["settings"]["outputs"], False)
        self.assertEqual(path.read_bytes(), before)

    def test_unreadable_media_falls_back_to_dark_after_valid_config(self):
        self.write_config()
        self.image_path.write_bytes(b"not an image")
        self.assertEqual(self.start()["status"], "ready")
        self.until(lambda: self.ipc("status").stdout.strip() == "error")
        self.assert_dark(self.state())
        self.assertIn("Cannot decode " + str(self.image_path), self.log_path.read_text())

    # Image quality, animation playback, and asynchronous selection changes.
    def test_center_and_tile_keep_native_pixels_on_hidpi_outputs(self):
        self.env["QT_SCALE_FACTOR"] = "2"
        path = self.write_config()
        original = path.read_text()
        for fit in ("center", "tile"):
            with self.subTest(fit=fit):
                path.write_text(original.replace('fit = "fit"', 'fit = "' + fit + '"'))
                self.start()
                self.until(lambda: self.ipc("status").stdout.strip() == "ready")
                state = self.state()
                window = state["windows"][0]
                image = state["images"][0]

                # Logical scaling must cancel DPR so one source pixel stays one display pixel.
                self.assertEqual(window["dpr"], 2)
                self.assertEqual(image["scale"] * window["dpr"], 1)
                self.assertEqual(image["displayWidth"] * image["scale"], window["width"])
                self.assertEqual(image["displayHeight"] * image["scale"], window["height"])
                self.assertEqual((image["width"], image["height"]), (1600, 900))
                self.stop()

    def test_finite_animation_repeats_and_pauses_with_output_activity(self):
        self.image_path = self.write_animation(self.root / "finite.gif")
        self.write_config()
        self.start()
        self.until(lambda: any(image["frameCount"] == 2 and image["playing"] for image in self.state()["images"]))
        # This file has no looping extension; the renderer must restart it after its 100 ms run.
        time.sleep(0.4)
        self.assertTrue(self.state()["images"][0]["playing"])
        self.ipc("outputActive", "false", target="test")
        self.until(lambda: self.state()["images"][0]["paused"])
        frame_number = self.state()["images"][0]["currentFrame"]
        time.sleep(0.15)
        self.assertEqual(self.state()["images"][0]["currentFrame"], frame_number)
        self.ipc("outputActive", "true", target="test")
        self.until(lambda: not self.state()["images"][0]["paused"])

    def test_reloaded_selection_waits_for_new_media_fades_and_recovers_from_failure(self):
        path = self.write_config(extra='\n[transition]\ntype = "fade"\nduration_ms = 500\n')
        original = path.read_bytes()
        self.start()
        self.until(lambda: self.ipc("status").stdout.strip() == "ready")
        replacement = self.root / "new.png"
        replacement.write_bytes(self.image_path.read_bytes())

        # The old image being ready must not make a new selection report ready early.
        self.assertEqual(self.select(replacement).stdout.strip(), "loading")
        self.until(lambda: self.ipc("status").stdout.strip() == "ready")
        self.until(lambda: any(0 < image["opacity"] < 1 for image in self.state()["images"]))
        images = self.state()["images"]
        self.assertEqual(len(images), 2)

        # Keep the lower image opaque during the fade to avoid exposing the background.
        self.assertEqual(next(image["opacity"] for image in images if image["z"] == 0), 1)
        self.until(lambda: len(self.state()["images"]) == 1)
        self.assertEqual(self.select(self.root / "missing.png").stdout.strip(), "loading")
        self.until(lambda: self.ipc("status").stdout.strip() == "error")
        self.assert_dark(self.state())
        self.assertEqual(self.state()["images"], [])
        self.assertEqual(self.select(self.image_path).stdout.strip(), "loading")
        self.until(lambda: self.ipc("status").stdout.strip() == "ready")
        self.assertEqual(path.read_bytes(), original)

    def test_reload_recovers_after_user_creates_missing_config(self):
        self.assertEqual(self.start()["status"], "error")
        self.assertEqual(self.select(self.image_path).stdout.strip(), "loading")
        self.until(lambda: self.ipc("status").stdout.strip() == "ready")
        self.assertTrue(Path(self.state()["path"]).exists())

    def test_explicit_reload_replaces_pending_startup_read(self):
        config = self.write_config()
        # Delay before the existence check so the missing-file case also starts pending.
        reader = self.renderer.parent / "read.lua"
        reader.write_text(reader.read_text().replace('local ok, result = pcall(function()',
                            'local ok, result = pcall(function()\n    os.execute("/usr/bin/sleep 0.3")'))
        replacement = self.root / "early.png"
        replacement.write_bytes(self.image_path.read_bytes())
        for missing in (False, True):
            with self.subTest(config_missing=missing):
                if missing:
                    config.unlink()
                self.assertEqual(self.start(wait_loaded=False)["status"], "loading")
                self.select(replacement)
                self.until(lambda: self.state()["status"] in ("ready", "error"))
                self.until(lambda: self.ipc("status").stdout.strip() == "ready")
                self.assertEqual(self.state()["config"]["wallpaper"]["source"], str(replacement))
                if not missing:
                    self.assertEqual(self.state()["settings"]["wallpaper"]["fit"], "fit")
                    self.assertEqual(self.state()["settings"]["wallpaper"]["background_color"], "#102030")
                self.stop()

    def test_late_decoder_error_clears_already_visible_media(self):
        self.write_config()
        self.start()
        self.until(lambda: self.ipc("status").stdout.strip() == "ready")
        self.ipc("lateDecodeError", target="test")
        self.assertEqual(self.ipc("status").stdout.strip(), "error")
        self.assert_dark(self.state())
        self.assertEqual(self.state()["images"], [])

    # Content detection must not depend on extensions or accept stale probe results.
    def test_content_detection_loads_extensionless_images_and_animations(self):
        png = self.root / "photo"
        png.write_bytes(self.image_path.read_bytes())
        gif = self.write_animation(self.root / "animation")
        for path, kind in ((png, "image"), (gif, "animated")):
            with self.subTest(kind=kind):
                self.image_path = path
                self.write_config()
                self.start()
                self.until(lambda: self.ipc("status").stdout.strip() == "ready")
                state = self.state()
                self.assertEqual(state["kind"], kind)
                self.assertEqual(state["videos"], [])
                self.assertEqual(state["images"][0]["frameCount"], 2 if kind == "animated" else 1)
                self.stop()

    def test_metadata_routes_apng_and_video_without_starting_a_player(self):
        self.write_config()

        # APNG uses the video backend; the stub checks routing without relying on Qt codecs.
        for codec, format_name in (("apng", "apng"), ("h264", "mov,mp4,m4a,3gp,3g2,mj2")):
            with self.subTest(codec=codec):
                metadata = {"streams": [{"codec_name": codec}], "format": {"format_name": format_name}}
                self.mock_probe({str(self.image_path): {"metadata": metadata}})
                self.start()
                self.until(lambda: self.ipc("status").stdout.strip() == "ready")
                state = self.state()
                self.assertEqual(state["kind"], "video")
                self.assertEqual(state["images"], [])
                self.assertEqual(state["videos"], [{"source": str(self.image_path)}])
                self.stop()

    def test_video_is_released_before_probing_a_replacement_image(self):
        replacement = self.root / "replacement.png"
        replacement.write_bytes(self.image_path.read_bytes())
        self.mock_probe({
            str(self.image_path): {"metadata": {
                "streams": [{"codec_name": "h264"}], "format": {"format_name": "mov"}}},
            str(replacement): {"delay": 0.4, "metadata": {
                "streams": [{"codec_name": "png"}], "format": {"format_name": "png_pipe"}}}
        })
        self.write_config()
        self.start()
        self.until(lambda: self.ipc("status").stdout.strip() == "ready")
        self.assertEqual(self.state()["videos"], [{"source": str(self.image_path)}])

        # The previous player must not receive an unclassified source or report it ready.
        self.select(replacement)
        self.until(lambda: str(replacement) in (self.root / "probe-calls").read_text())
        self.assertEqual(self.state()["videos"], [])
        self.assertEqual(self.ipc("status").stdout.strip(), "loading")
        self.until(lambda: self.ipc("status").stdout.strip() == "ready")
        self.assertEqual(self.state()["kind"], "image")
        self.assertEqual(self.state()["videos"], [])

    def test_slow_old_probe_cannot_route_a_new_selection(self):
        replacement = self.root / "replacement"
        replacement.write_bytes(self.image_path.read_bytes())
        self.mock_probe({
            str(self.image_path): {"delay": 0.3, "metadata": {
                "streams": [{"codec_name": "apng"}], "format": {"format_name": "apng"}}},
            str(replacement): {"metadata": {
                "streams": [{"codec_name": "png"}], "format": {"format_name": "png_pipe"}}}
        })
        self.write_config()
        self.start()

        # Replace the source after the old probe starts, then allow its delayed reply to arrive.
        self.until(lambda: (self.root / "probe-calls").exists())
        self.select(replacement)
        self.until(lambda: self.ipc("status").stdout.strip() == "ready")
        time.sleep(0.4)
        state = self.state()
        self.assertEqual(state["kind"], "image")
        self.assertEqual(state["videos"], [])
        self.assertTrue(all(image["source"].endswith("/replacement") for image in state["images"]))

    def test_invalid_probe_metadata_stays_dark(self):
        self.mock_probe({str(self.image_path): {"output": "not json"}})
        self.write_config()
        self.start()
        self.until(lambda: self.ipc("status").stdout.strip() == "error")
        self.assert_dark(self.state())
        self.assertIn("Could not identify media", self.log_path.read_text())

    def test_missing_probe_reports_actionable_error_and_stays_dark(self):
        directory = self.root / "tools"
        directory.mkdir()
        for name in ("qs", "dbus-run-session", "dbus-daemon"):
            (directory / name).symlink_to(shutil.which(name))
        self.env["PATH"] = str(directory)
        self.write_config()
        self.start()
        self.until(lambda: self.ipc("status").stdout.strip() == "error")
        self.assert_dark(self.state())
        self.assertIn("install the ffmpeg package", self.log_path.read_text())


if __name__ == "__main__":
    unittest.main()
