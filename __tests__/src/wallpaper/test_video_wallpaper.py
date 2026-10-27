"""Test video controller readiness, IPC, and cleanup without launching mpvpaper.

Run from the repository root:
    python3 -m unittest discover -s __tests__/src/wallpaper -p test_video_wallpaper.py -v

The real QML controller runs offscreen against a fake player on a local Unix
socket. These tests verify process arguments and lifecycle, not video quality or
Wayland layer placement.
"""

import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import textwrap
import time
import unittest


ROOT = Path(__file__).resolve().parents[3]


@unittest.skipUnless(shutil.which("qs"), "Quickshell required")
class VideoWallpaperTests(unittest.TestCase):
    def setUp(self):
        """Build a private controller harness and put a fake mpvpaper first on PATH."""
        self.temp = tempfile.TemporaryDirectory(prefix="luna-video-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.renderer = self.root / "shell"
        self.renderer.mkdir()

        # Copy the production controller and expose only test controls through a small shell.
        for name in ("VideoWallpaper.qml", "Video.js"):
            shutil.copyfile(ROOT / "src/wallpaper/src" / name, self.renderer / name)
        (self.renderer / "shell.qml").write_text('''import QtQuick
import Quickshell
import Quickshell.Io
ShellRoot {
    property string failure: ""
    property var video: videoLoader.item
    Loader {
        id: videoLoader
        sourceComponent: VideoWallpaper {
            active: false
            outputName: "DP-1"
            startupTimeout: 1800
            onFailed: function(message) { failure = message; }
        }
    }
    IpcHandler {
        target: "test"
        function state(): string {
            if (!video) return "{}";
            return JSON.stringify({status: video.status, error: failure,
                directory: video.privateDirectory, connected: video.connectedOnce});
        }
        function start(path: string, fit: string): void {
            video.sourcePath = path;
            video.fit = fit;
            video.active = true;
        }
        function pause(value: bool): void { video.paused = value; }
        function stop(): void { video.active = false; }
        function destroy(): void { videoLoader.active = false; }
    }
}
''')

        # The stub records argv and mpv commands. Marker files inject delays, crashes,
        # disconnects, and events without requiring media files or a compositor.
        tools = self.root / "bin"
        tools.mkdir()
        stub = tools / "mpvpaper"
        stub.write_text(textwrap.dedent('''\
            #!/usr/bin/python3
            import json, os, pathlib, signal, socket, sys, time
            root = pathlib.Path(os.environ["TEST_VIDEO_ROOT"])
            with (root / "launches").open("a") as file:
                file.write(json.dumps({"args": sys.argv[1:], "pid": os.getpid(),
                    "cwd": os.getcwd(), "home": os.environ["HOME"]}) + "\\n")
            if (root / "crash").exists(): sys.exit(3)
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind("ipc")
            server.listen(1)
            client, _ = server.accept()
            client.settimeout(0.05)
            data = b""
            while True:
                if (root / "disconnect").exists(): client.close(); time.sleep(10)
                if (root / "event").exists():
                    client.sendall((root / "event").read_bytes() + b"\\n")
                    (root / "event").unlink()
                try: chunk = client.recv(4096)
                except socket.timeout: continue
                if not chunk: break
                data += chunk
                while b"\\n" in data:
                    line, data = data.split(b"\\n", 1)
                    message = json.loads(line)
                    with (root / "commands").open("a") as file:
                        file.write(json.dumps(message) + "\\n")
                    result = {"request_id": message["request_id"], "error": "success"}
                    if message["command"][:1] == ["get_property"]:
                        result["data"] = None if (root / "hold").exists() else {"w": 3840, "h": 2160}
                    client.sendall(json.dumps(result).encode() + b"\\n")
        '''))
        stub.chmod(0o755)

        # Keep sockets, config, and logs private and make desktop endpoints unusable.
        runtime = self.root / "runtime"
        runtime.mkdir(mode=0o700)
        self.env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QS_NO_RELOAD_POPUP="1",
                        XDG_RUNTIME_DIR=str(runtime), HOME=str(self.root / "home"),
                        XDG_CONFIG_HOME=str(self.root / "config"), XDG_DATA_HOME=str(self.root / "data"),
                        XDG_CACHE_HOME=str(self.root / "cache"), XDG_STATE_HOME=str(self.root / "state"),
                        WAYLAND_DISPLAY="luna-video-test-no-display", DISPLAY="",
                        PATH=str(tools) + ":" + os.environ["PATH"], TEST_VIDEO_ROOT=str(self.root))
        self.env.pop("HYPRLAND_INSTANCE_SIGNATURE", None)
        self.log = (self.root / "shell.log").open("w+")
        self.addCleanup(self.log.close)

        # A separate process group lets cleanup terminate the harness and its children.
        self.process = subprocess.Popen(["qs", "-p", str(self.renderer)], env=self.env,
                                        stdout=self.log, stderr=subprocess.STDOUT, start_new_session=True)
        self.addCleanup(self.stop_process)
        self.until(lambda: self.ipc("state", check=False).returncode == 0)

    def stop_process(self):
        """Reap the isolated shell and any fake players left by a failed test."""
        if self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            self.process.wait(timeout=5)
        for launch in self.rows("launches"):
            try:
                os.kill(launch["pid"], signal.SIGKILL)
            except ProcessLookupError:
                pass

    def ipc(self, method, *arguments, check=True):
        """Call the private harness, encoding booleans as QML's textual IPC arguments."""
        values = [str(value).lower() if isinstance(value, bool) else str(value) for value in arguments]
        return subprocess.run(["qs", "ipc", "-p", str(self.renderer), "call", "test", method, *values],
                              env=self.env, text=True, capture_output=True, timeout=3, check=check)

    def state(self):
        """Read controller status and the socket directory exposed by the harness."""
        return json.loads(self.ipc("state").stdout)

    def rows(self, name):
        """Read append-only JSON records written by the fake player."""
        path = self.root / name
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def until(self, predicate, timeout=4):
        """Wait for an asynchronous controller result, reporting its log on failure."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            if self.process.poll() is not None:
                break
            time.sleep(0.025)
        self.fail("Video test condition failed: " + (self.root / "shell.log").read_text())

    def start(self, fit="fill"):
        """Use a shell-looking path to verify that media paths remain literal argv values."""
        source = str(self.root / 'wallpaper with spaces;$(touch forbidden).mp4')
        self.ipc("start", source, fit)
        return source

    # Readiness requires decoded video dimensions, not just a running process or socket.
    def test_ready_requires_video_parameters_and_preserves_original_media(self):
        (self.root / "hold").touch()
        source = self.start()
        self.until(lambda: self.state()["connected"])
        self.assertEqual(self.state()["status"], "loading")
        launch = self.rows("launches")[0]
        self.assertEqual(launch["args"][-2:], ["DP-1", source])
        self.assertEqual(launch["args"][:2], ["--layer", "bottom"])
        options = launch["args"][3]
        for option in ("config=no", "load-scripts=no", "loop-file=inf", "audio=no", "hwdec=auto"):
            self.assertIn(option, options)

        # No frame-rate or filter override should silently reduce source quality.
        self.assertNotIn("fps=", options)
        self.assertNotIn("vf=", options)
        self.assertEqual(launch["cwd"], launch["home"])
        self.assertEqual(Path(launch["cwd"]).stat().st_mode & 0o777, 0o700)
        (self.root / "hold").unlink()
        self.until(lambda: self.state()["status"] == "ready")
        self.assertFalse((self.root / "forbidden").exists())

    def test_pause_resume_and_intentional_stop_clean_up(self):
        self.start()
        self.until(lambda: self.state()["status"] == "ready")
        directory = Path(self.state()["directory"])
        self.ipc("pause", True)
        self.until(lambda: any(row["command"] == ["set_property", "pause", True] for row in self.rows("commands")))
        self.ipc("pause", False)
        self.until(lambda: self.rows("commands")[-1]["command"] == ["set_property", "pause", False])
        self.ipc("stop")
        self.until(lambda: not directory.exists())
        self.assertEqual(self.state()["error"], "")

    # Backend failures must become errors and release owned runtime resources.
    def test_socket_disconnect_fails_and_cleans_up(self):
        self.start()
        self.until(lambda: self.state()["status"] == "ready")
        directory = Path(self.state()["directory"])
        (self.root / "disconnect").touch()
        self.until(lambda: self.state()["status"] == "error")
        self.until(lambda: not directory.exists())
        self.assertIn("IPC", self.state()["error"])

    def test_startup_timeout_fails_without_video_parameters(self):
        (self.root / "hold").touch()
        self.start()
        self.until(lambda: self.state()["status"] == "error")
        self.assertIn("timeout", self.state()["error"])
        self.until(lambda: not self.state()["directory"])

    def test_early_player_crash_fails(self):
        (self.root / "crash").touch()
        self.start()
        self.until(lambda: self.state()["status"] == "error")
        self.assertIn("exited (3)", self.state()["error"])

    def test_unsupported_video_fit_uses_center(self):
        # Image-only tiling and unknown values should use a normal video fit, not reject playback.
        for fit in ("tile", "unknown", "toString"):
            with self.subTest(fit=fit):
                self.start(fit)
                self.until(lambda: self.state()["status"] == "ready")
                self.assertIn("video-unscaled=yes", self.rows("launches")[-1]["args"][3])
                self.assertEqual(self.state()["error"], "")
                directory = Path(self.state()["directory"])
                self.ipc("stop")
                self.until(lambda: not directory.exists())

    def test_decode_error_event_fails_after_ready(self):
        self.start()
        self.until(lambda: self.state()["status"] == "ready")
        (self.root / "event").write_text(json.dumps({"event": "end-file", "reason": "error", "error": "decode failed"}))
        self.until(lambda: self.state()["status"] == "error")
        self.assertIn("decode failed", self.state()["error"])

    def test_invalid_ipc_data_fails(self):
        self.start()
        self.until(lambda: self.state()["status"] == "ready")
        (self.root / "event").write_text("not json")
        self.until(lambda: self.state()["status"] == "error")
        self.assertIn("invalid IPC", self.state()["error"])

    # Settings changes and component destruction must clean up the previous player.
    def test_changing_fit_restarts_only_the_owned_player(self):
        self.start("fill")
        self.until(lambda: self.state()["status"] == "ready")
        old_directory = Path(self.state()["directory"])
        self.start("center")
        self.until(lambda: len(self.rows("launches")) == 2 and self.state()["status"] == "ready")
        self.until(lambda: not old_directory.exists())
        self.assertIn("video-unscaled=yes", self.rows("launches")[-1]["args"][3])
        self.assertEqual(self.state()["error"], "")

    def test_destroying_component_removes_its_socket_directory(self):
        self.start()
        self.until(lambda: self.state()["status"] == "ready")
        directory = Path(self.state()["directory"])
        self.ipc("destroy")
        self.until(lambda: not directory.exists())
        self.assertEqual(self.state(), {})

    def test_fit_modes_use_distinct_player_sizing(self):
        for fit, expected in (("fit", "panscan=0"), ("stretch", "keepaspect=no"), ("center", "video-unscaled=yes")):
            with self.subTest(fit=fit):
                self.start(fit)
                self.until(lambda: self.state()["status"] == "ready")
                self.assertIn(expected, self.rows("launches")[-1]["args"][3])
                directory = Path(self.state()["directory"])
                self.ipc("stop")
                self.until(lambda: not directory.exists())


if __name__ == "__main__":
    unittest.main()
