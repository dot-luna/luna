pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Luna as Luna

// Select this file with renderer.shell. [settings] may provide orbit_seconds.
ShellRoot {
    Component.onCompleted: Quickshell.watchFiles = false

    Variants {
        model: Quickshell.screens
        delegate: Luna.ScreensaverSurface {
            id: surface
            required property var modelData
            screen: modelData

            Item {
                id: orbit
                anchors.centerIn: parent
                width: Math.min(surface.width, surface.height) * 0.45
                height: width

                RotationAnimation on rotation {
                    from: 0
                    to: 360
                    duration: Math.max(10, Number(surface.settings.orbit_seconds) || 90) * 1000
                    loops: Animation.Infinite
                    running: surface.renderingActive
                }

                Rectangle {
                    anchors.fill: parent
                    color: "transparent"
                    radius: width / 2
                    border.width: Math.max(1, Luna.Theme.borderWidth)
                    border.color: Luna.Theme.muted
                    opacity: 0.35
                }

                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    y: -height / 2
                    width: 16
                    height: width
                    radius: width / 2
                    color: Luna.Theme.accent
                }
            }
        }
    }
}
