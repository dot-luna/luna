"""Exercise the production surface's input handling with offscreen Qt windows."""

import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[5]


@unittest.skipUnless(shutil.which("qs") and shutil.which("dbus-run-session"),
                     "Quickshell and D-Bus required")
class ScreensaverSurfaceTests(unittest.TestCase):
    def test_surface_input_and_output_state(self):
        with tempfile.TemporaryDirectory(prefix="luna-screensaver-surface-") as directory:
            root = Path(directory)
            for name in ("runtime", "home", "config", "cache", "state"):
                (root / name).mkdir(mode=0o700)
            (root / "repo").symlink_to(REPO, target_is_directory=True)
            module = root / "qml/Luna"
            module.mkdir(parents=True)
            (module / "qmldir").write_text("module Luna\nsingleton Theme 1.0 Theme.qml\n"
                                          "singleton ScreensaverSession 1.0 ScreensaverSession.qml\n")
            (module / "Theme.qml").write_text('''pragma Singleton
import QtQuick
QtObject { readonly property color background: "#1a1b26" }
''')
            # Fake only the IPC destination; exercise the real window/input helper.
            (module / "ScreensaverSession.qml").write_text('''pragma Singleton
import QtQuick
QtObject {
    property int readyCount: 0
    property int dismissCount: 0
    property string focusedScreen: "primary"
    readonly property var settings: ({orbit_seconds: 42})
    function ready() { readyCount++; }
    function dismiss() { dismissCount++; }
}
''')
            source = (REPO / "src/screensaver/src/shell/ScreensaverSurface.qml").read_text()
            # Offscreen Qt cannot create layer-shell windows. Replace only that
            # compositor boundary and give tests controllable monitor snapshots.
            source = source.replace("import QtQuick\n", "import QtQuick\nimport QtQuick.Window\n")
            source = source.replace("PanelWindow {", "Window {")
            source = re.sub(r"\bscreen\b", "outputScreen", source)
            source = source.replace("readonly property var monitor:", "property var monitor:")
            source = "\n".join(line for line in source.splitlines()
                               if not line.strip().startswith(("anchors { top: true;", "exclusionMode:",
                                                               "WlrLayershell.")))
            source = source.replace("    id: surface", '''    id: surface
    width: 640
    height: 360
    property var outputScreen: ({name: "primary"})
    readonly property bool backingWindowVisible: visible''')
            (root / "ScreensaverSurface.qml").write_text(source + "\n")
            (root / "shell.qml").write_text('''import QtQuick
import QtQuick.Window
import Quickshell
import "repo/__tests__/src/screensaver/src/shell" as Tests
ShellRoot {
    Component.onCompleted: Quickshell.watchFiles = false
    ScreensaverSurface {
        id: testSurface
        property int visualClicks: 0
        Component.onCompleted: requestActivate()
        MouseArea {
            objectName: "customVisual"
            anchors.fill: parent
            onClicked: testSurface.visualClicks++
        }
        Tests.ScreensaverSurfaceTests {
            anchors.fill: parent
            when: true
            surface: testSurface
        }
    }
    Timer { interval: 20000; running: true; onTriggered: Qt.exit(98) }
}
''')
            environment = dict(os.environ, HOME=str(root / "home"), QT_QPA_PLATFORM="offscreen",
                               QT_QUICK_BACKEND="software", XDG_RUNTIME_DIR=str(root / "runtime"),
                               XDG_CONFIG_HOME=str(root / "config"), XDG_CACHE_HOME=str(root / "cache"),
                               XDG_STATE_HOME=str(root / "state"), QML_IMPORT_PATH=str(root / "qml"),
                               QS_NO_RELOAD_POPUP="1",
                               DBUS_SYSTEM_BUS_ADDRESS="unix:path=/nonexistent-luna-test-system-bus")
            for name in ("WAYLAND_DISPLAY", "DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE",
                         "DBUS_SESSION_BUS_ADDRESS", "QML2_IMPORT_PATH"):
                environment.pop(name, None)
            process = subprocess.Popen(["dbus-run-session", "--", "qs", "--no-color", "-p", str(root)],
                                       env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, start_new_session=True)
            try:
                output, _ = process.communicate(timeout=25)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                output, _ = process.communicate(timeout=5)
                self.fail("Surface tests timed out:\n" + output)
            finally:
                # A crashed test may have spawned Quickshell's crash reporter.
                # Tear down only this private process group, including on failure.
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            self.assertEqual(process.returncode, 0, output)
            summary = re.search(r"LUNA_SCREENSAVER_SURFACE_TEST_RESULT (\{[^\n]+\})", output)
            self.assertIsNotNone(summary, output)
            counts = json.loads(summary.group(1))
            self.assertEqual(counts["failed"], 0, output)
            self.assertEqual(counts["skipped"], 0, output)
            tests = (Path(__file__).parent / "ScreensaverSurfaceTests.qml").read_text()
            expected = len(re.findall(r"function test_\w+\(", tests))
            self.assertEqual(counts["passed"], expected + 1, output)
            for error in ("ReferenceError", "TypeError", "Binding loop", "Unable to assign"):
                self.assertNotIn(error, output)


if __name__ == "__main__":
    unittest.main()
