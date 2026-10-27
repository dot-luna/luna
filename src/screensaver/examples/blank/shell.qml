import QtQuick
import Quickshell
import Luna as Luna

// A black screensaver keeps the output powered on. DPMS belongs to Luna's controller.
ShellRoot {
    Component.onCompleted: Quickshell.watchFiles = false

    Variants {
        model: Quickshell.screens
        delegate: Luna.ScreensaverSurface {
            required property var modelData
            screen: modelData
            color: "#000000"
        }
    }
}
