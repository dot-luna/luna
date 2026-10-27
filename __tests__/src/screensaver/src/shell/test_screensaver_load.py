"""Load bundled and example shells on real Wayland with every surface hidden."""

import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[5]


@unittest.skipUnless(shutil.which("qs") and shutil.which("dbus-run-session")
                     and os.getenv("WAYLAND_DISPLAY"), "Quickshell and a Wayland session required")
class ScreensaverLoadTests(unittest.TestCase):
    def test_native_shells_load_without_visible_windows(self):
        display = Path(os.environ["WAYLAND_DISPLAY"])
        if not display.is_absolute():
            display = Path(os.environ["XDG_RUNTIME_DIR"]) / display
        theme = {
            "fonts": {"ui": "Sans", "mono": "Monospace"},
            "colors": {"background": "#1a1b26", "foreground": "#a9b1d6", "bright_foreground": "#c0caf5",
                       "muted": "#565f89", "accent": "#bb9af7", "accent_foreground": "#1a1b26",
                       "lighter_background": "#24283b", "selection": "#414868", "selection_foreground": "#c0caf5"},
            "hyprland": {"decoration": {"rounding": 0}, "general": {"border_size": 1, "gaps_out": 4}},
        }
        for entrypoint in ("src/shell/shell.qml", "examples/blank/shell.qml", "examples/orbit/shell.qml"):
            with self.subTest(shell=entrypoint), tempfile.TemporaryDirectory(prefix="luna-screensaver-load-") as directory:
                root = Path(directory)
                for name in ("runtime", "home", "config", "cache"):
                    (root / name).mkdir(mode=0o700)
                module = root / "qml/Luna"
                module.mkdir(parents=True)
                (module / "qmldir").write_text("module Luna\nsingleton Theme 1.0 Theme.qml\n"
                                              "singleton ScreensaverSession 1.0 ScreensaverSession.qml\n"
                                              "ScreensaverSurface 1.0 ScreensaverSurface.qml\n")
                (module / "Theme.qml").symlink_to(REPO / "src/qml/Luna/Theme.qml")
                (module / "ScreensaverSession.qml").symlink_to(REPO / "src/screensaver/src/shell/ScreensaverSession.qml")
                source = (REPO / "src/screensaver/src/shell/ScreensaverSurface.qml").read_text()
                # Validate real layer-shell types without ever mapping a window.
                source = source.replace("visible: !!screen", "visible: false")
                (module / "ScreensaverSurface.qml").write_text(source)
                shell = (REPO / "src/screensaver" / entrypoint).read_text()
                shell = shell.replace("ShellRoot {", '''ShellRoot {
    Timer {
        interval: 150
        running: true
        onTriggered: { console.log("LUNA_SCREENSAVER_LOAD_OK"); Qt.quit(); }
    }''', 1)
                (root / "shell.qml").write_text(shell)
                environment = dict(os.environ, HOME=str(root / "home"), QT_QPA_PLATFORM="wayland",
                                   QT_NO_XDG_DESKTOP_PORTAL="1", QT_QPA_PLATFORMTHEME="",
                                   WAYLAND_DISPLAY=str(display), XDG_RUNTIME_DIR=str(root / "runtime"),
                                   XDG_CONFIG_HOME=str(root / "config"), XDG_CACHE_HOME=str(root / "cache"),
                                   QML_IMPORT_PATH=str(root / "qml"), QS_NO_RELOAD_POPUP="1",
                                   LUNA_UI_THEME=json.dumps(theme), LUNA_SCREENSAVER_CONTROLLER="",
                                   LUNA_SCREENSAVER_TOKEN="", LUNA_SCREENSAVER_SETTINGS='{"settings":{"orbit_seconds":42}}',
                                   DBUS_SYSTEM_BUS_ADDRESS="unix:path=/nonexistent-luna-test-system-bus")
                for name in ("DBUS_SESSION_BUS_ADDRESS", "QML2_IMPORT_PATH", "HYPRLAND_INSTANCE_SIGNATURE"):
                    environment.pop(name, None)
                process = subprocess.Popen(["dbus-run-session", "--", "qs", "--no-color", "-p", str(root)],
                                           env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                           text=True, start_new_session=True)
                try:
                    output, _ = process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    output, _ = process.communicate(timeout=5)
                    self.fail("Invisible load timed out:\n" + output)
                finally:
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                self.assertEqual(process.returncode, 0, output)
                self.assertIn("LUNA_SCREENSAVER_LOAD_OK", output)
                for error in ("ReferenceError", "TypeError", "Binding loop", "Unable to assign", "ERROR:", "WARN"):
                    self.assertNotIn(error, output)


if __name__ == "__main__":
    unittest.main()
