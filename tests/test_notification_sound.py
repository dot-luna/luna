"""Exercise sound scheduling with an offscreen shell and a silent mock player."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import time
import unittest


REPO = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("qs"), "Quickshell required")
class NotificationSoundTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna-sound-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "notifications").symlink_to(REPO / "src/luna-bar/notifications", target_is_directory=True)
        (self.root / "shell.qml").write_text('''import QtQuick
import Quickshell
import Quickshell.Io
import "notifications"
ShellRoot {
    NotificationSound { id: sound }
    IpcHandler {
        target: "test"
        function ping(): string { return "ready"; }
        function play(urgency: int): void { sound.play(urgency); }
        function burst(values: string): void { values.split(":").forEach(value => sound.play(Number(value))); }
        function enable(value: bool): void { sound.enabled = value; }
    }
}
''')
        runtime = self.root / "runtime"
        runtime.mkdir(mode=0o700)
        tools = self.root / "tools"
        tools.mkdir()
        player = tools / "canberra-gtk-play"
        player.write_text(textwrap.dedent('''\
            #!/usr/bin/python3
            import fcntl, json, os, signal, sys, time
            from pathlib import Path
            root = Path(os.environ["LUNA_SOUND_TEST_ROOT"])
            def record(event):
                with (root / "calls").open("a") as log:
                    log.write(json.dumps({"event": event, "time": time.monotonic(), "args": sys.argv[1:],
                        "injected": [name for name in ("LD_LIBRARY_PATH", "LD_PRELOAD") if name in os.environ]}) + "\\n")
            lock = (root / "player.lock").open("w")
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                record("overlap")
                sys.exit(1)
            def cancel(*args):
                record("cancelled")
                sys.exit(0)
            signal.signal(signal.SIGTERM, cancel)
            options = json.loads((root / "options").read_text())
            record("start")
            print("mock player stdout", flush=True)
            print("mock player stderr", file=sys.stderr, flush=True)
            time.sleep(options["duration"])
            record("end")
            sys.exit(options["exit"])
        '''))
        player.chmod(0o755)
        self.options(duration=0.05)
        self.environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", XDG_RUNTIME_DIR=str(runtime),
                                QS_NO_RELOAD_POPUP="1", PATH=str(tools) + ":" + os.environ["PATH"],
                                LUNA_SOUND_TEST_ROOT=str(self.root), LD_LIBRARY_PATH=str(self.root / "libraries"),
                                LD_PRELOAD="")
        self.environment.pop("WAYLAND_DISPLAY", None)
        self.log = (self.root / "shell.log").open("w+")
        self.addCleanup(self.log.close)
        self.process = subprocess.Popen(["qs", "-p", str(self.root)], env=self.environment,
                                        stdout=self.log, stderr=subprocess.STDOUT)
        self.addCleanup(self.stop)
        self.until(lambda: self.ipc("ping", check=False).returncode == 0)

    def stop(self):
        self.process.terminate()
        self.process.wait(timeout=5)

    def options(self, duration=0.05, exit_code=0):
        (self.root / "options").write_text(json.dumps({"duration": duration, "exit": exit_code}))

    def ipc(self, method, *arguments, check=True):
        return subprocess.run(["qs", "ipc", "-p", str(self.root), "call", "test", method,
                               *map(str, arguments)], env=self.environment,
                              capture_output=True, text=True, check=check, timeout=3)

    def calls(self, event="start"):
        path = self.root / "calls"
        entries = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        return [entry for entry in entries if entry["event"] == event]

    def until(self, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            if self.process.poll() is not None:
                break
            time.sleep(0.02)
        self.log.flush()
        self.fail("Sound condition did not become true: " + (self.root / "shell.log").read_text())

    def test_priority_events_volumes_and_environment_are_per_playback(self):
        for index, (event, volume) in enumerate((("message-new-instant", "-18"), ("message", "-12"),
                                               ("dialog-warning", "-6"))):
            self.ipc("play", index)
            self.until(lambda: len(self.calls("end")) == index + 1)
            playback = self.calls()[index]
            self.assertEqual(playback["args"], ["--id=" + event, "--volume=" + volume, "--loop=1"])
            self.assertEqual(playback["injected"], [])
        self.assertEqual(self.calls("overlap"), [])
        self.assertNotIn("mock player", (self.root / "shell.log").read_text())

    def test_burst_coalesces_to_one_highest_priority_sound(self):
        self.ipc("burst", ":".join(map(str, [0, 1, 2, 0, 1] * 100)))
        self.until(lambda: len(self.calls("end")) == 1)
        time.sleep(0.9)
        self.assertEqual(len(self.calls()), 1)
        self.assertIn("--id=dialog-warning", self.calls()[0]["args"])

    def test_cooldown_keeps_a_bounded_pending_burst(self):
        self.ipc("play", 1)
        self.until(lambda: len(self.calls()) == 1)
        self.ipc("burst", ":".join(map(str, [0, 1] * 100)))
        self.until(lambda: len(self.calls("end")) == 2)
        first, second = self.calls()
        self.assertGreaterEqual(second["time"] - first["time"], 0.75)
        time.sleep(0.85)
        self.assertEqual(len(self.calls()), 2)
        self.assertEqual(self.calls("overlap"), [])

    def test_critical_bypasses_lower_priority_cooldown_without_overlap(self):
        self.options(duration=0.35)
        self.ipc("play", 1)
        self.until(lambda: len(self.calls()) == 1)
        self.ipc("burst", "0:2:1")
        self.until(lambda: len(self.calls()) == 2)
        first, critical = self.calls()
        self.assertGreaterEqual(critical["time"] - first["time"], 0.33)
        self.assertLess(critical["time"] - first["time"], 0.75)
        self.assertIn("--id=dialog-warning", critical["args"])
        self.ipc("burst", "2:2:2")
        self.until(lambda: len(self.calls("end")) == 3)
        self.assertGreaterEqual(self.calls()[2]["time"] - critical["time"], 0.75)
        self.assertEqual(self.calls("overlap"), [])

    def test_disabling_cancels_pending_and_active_sound_without_replay(self):
        self.ipc("play", 1)
        self.ipc("enable", "false")
        time.sleep(0.2)
        self.assertEqual(self.calls(), [])
        self.options(duration=2)
        self.ipc("enable", "true")
        self.ipc("play", 1)
        self.until(lambda: len(self.calls()) == 1)
        self.ipc("play", 2)
        self.ipc("enable", "false")
        self.until(lambda: len(self.calls("cancelled")) == 1)
        self.ipc("play", 2)
        self.ipc("enable", "true")
        time.sleep(0.9)
        self.assertEqual(len(self.calls()), 1)

    def test_player_failures_warn_once_and_leave_later_sounds_available(self):
        self.options(exit_code=1)
        self.ipc("play", 0)
        self.until(lambda: len(self.calls("end")) == 1)
        self.ipc("play", 2)
        self.until(lambda: len(self.calls("end")) == 2)
        time.sleep(0.05)
        output = (self.root / "shell.log").read_text()
        self.assertEqual(output.count("Could not play a Luna notification sound."), 1)
        self.assertNotIn("mock player", output)


if __name__ == "__main__":
    unittest.main()
