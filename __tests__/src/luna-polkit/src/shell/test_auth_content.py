"""Run the production authentication card with fake flows and keyboard/mouse events.

Run from the repository root:
    python3 -m unittest discover -s __tests__/src/luna-polkit/src/shell -p test_auth_content.py -v
"""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[5]


@unittest.skipUnless(shutil.which("qs") and shutil.which("dbus-run-session"),
                     "Quickshell and dbus-run-session required")
class AuthenticationContentTests(unittest.TestCase):
    def test_authentication_content(self):
        with tempfile.TemporaryDirectory(prefix="luna-polkit-ui-") as directory:
            root = Path(directory)
            for name in ("runtime", "home", "config", "cache", "state"):
                (root / name).mkdir(mode=0o700)
            (root / "repo").symlink_to(REPO, target_is_directory=True)
            dialog = root / "dialog"
            dialog.mkdir()
            source = REPO / "src/luna-polkit/src/shell"
            (dialog / "AuthContent.qml").symlink_to(source / "AuthContent.qml")
            # Offscreen Qt cannot create a layer-shell surface. Keep the production
            # dialog's layout and scrolling, replacing only its compositor bindings.
            window = (source / "AuthDialog.qml").read_text()
            window = window.replace("import QtQuick\n", "import QtQuick\nimport QtQuick.Window\n")
            window = window.replace("PanelWindow {", "Window {")
            window = "\n".join(line for line in window.splitlines()
                               if not line.strip().startswith(("anchors { top: true;", "exclusionMode:",
                                                               "WlrLayershell.")))
            (dialog / "AuthDialog.qml").write_text(window + "\n")
            (root / "shell.qml").write_text('''import QtQuick
import QtQuick.Window
import Quickshell
import "repo/__tests__/src/luna-polkit/src/shell" as Tests
import "dialog" as Dialog

ShellRoot {
    // A running test must keep its loaded components if files change on disk.
    Component.onCompleted: Quickshell.watchFiles = false

    Window {
        id: testWindow
        width: 640
        height: 700
        visible: true
        Component.onCompleted: requestActivate()

        Tests.AuthContentTests {
            anchors.fill: parent
            when: testWindow.active
            dialogSource: Qt.resolvedUrl("dialog/AuthDialog.qml")
        }
    }

    Timer {
        interval: 20000
        running: true
        onTriggered: Qt.exit(98)
    }
}
''')
            theme = {
                "fonts": {"ui": "Sans", "mono": "Monospace"},
                "colors": {
                    "accent": "#bb9af7", "accent_foreground": "#1a1b26",
                    "background": "#1a1b26", "foreground": "#a9b1d6",
                    "bright_foreground": "#c0caf5", "muted": "#565f89",
                    "lighter_background": "#24283b", "selection": "#414868",
                    "selection_foreground": "#c0caf5", "error": "#f7768e",
                },
                "hyprland": {"decoration": {"rounding": 14},
                             "general": {"border_size": 1, "gaps_out": 4}},
            }
            environment = dict(os.environ, HOME=str(root / "home"),
                               QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
                               XDG_RUNTIME_DIR=str(root / "runtime"),
                               XDG_CONFIG_HOME=str(root / "config"),
                               XDG_CACHE_HOME=str(root / "cache"),
                               XDG_STATE_HOME=str(root / "state"),
                               QML_IMPORT_PATH=str(REPO / "src/qml"),
                               LUNA_UI_THEME=json.dumps(theme), QS_NO_RELOAD_POPUP="1",
                               DBUS_SYSTEM_BUS_ADDRESS="unix:path=/nonexistent-luna-test-system-bus")
            for name in ("WAYLAND_DISPLAY", "DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE",
                         "DBUS_SESSION_BUS_ADDRESS", "QML2_IMPORT_PATH"):
                environment.pop(name, None)

            # UI only: no PolkitAgent, native authentication or IPC.
            result = subprocess.run(["dbus-run-session", "--", "qs", "--no-color", "-p", str(root)],
                                    env=environment, capture_output=True, text=True, timeout=25)
            output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, output)
            summary = re.search(r"LUNA_POLKIT_TEST_RESULT (\{[^\n]+\})", output)
            self.assertIsNotNone(summary, output)
            counts = json.loads(summary.group(1))
            self.assertEqual(counts["failed"], 0, output)
            self.assertEqual(counts["skipped"], 0, output)
            tests = (Path(__file__).resolve().parent / "AuthContentTests.qml").read_text()
            expected = len(re.findall(r"function test_\w+\(", tests))
            self.assertEqual(counts["passed"], expected + 1, output)
            for error in ("ReferenceError", "TypeError", "Binding loop", "Unable to assign"):
                self.assertNotIn(error, output)


if __name__ == "__main__":
    unittest.main()
