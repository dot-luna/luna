pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import Quickshell
import Luna as Luna

// The bundled clock uses the same surface API as a user's replacement shell.
ShellRoot {
    Component.onCompleted: Quickshell.watchFiles = false

    Variants {
        model: Quickshell.screens
        delegate: Luna.ScreensaverSurface {
            id: surface
            required property var modelData
            screen: modelData

            SystemClock { id: clock; enabled: surface.renderingActive; precision: SystemClock.Minutes }

            ColumnLayout {
                anchors.centerIn: parent
                spacing: 14
                transform: Translate {
                    SequentialAnimation on x {
                        running: surface.renderingActive
                        loops: Animation.Infinite
                        NumberAnimation { from: -28; to: 28; duration: 45000; easing.type: Easing.InOutSine }
                        NumberAnimation { from: 28; to: -28; duration: 45000; easing.type: Easing.InOutSine }
                    }
                    SequentialAnimation on y {
                        running: surface.renderingActive
                        loops: Animation.Infinite
                        NumberAnimation { from: -16; to: 16; duration: 60000; easing.type: Easing.InOutSine }
                        NumberAnimation { from: 16; to: -16; duration: 60000; easing.type: Easing.InOutSine }
                    }
                }

                Text {
                    Layout.alignment: Qt.AlignHCenter
                    text: Qt.formatTime(clock.date, Qt.locale().timeFormat(Locale.ShortFormat))
                    color: Luna.Theme.brightForeground
                    font.family: Luna.Theme.uiFont
                    font.pixelSize: Math.max(24, Math.min(96, surface.width / 8, surface.height / 4))
                    font.weight: Font.Light
                }

                Text {
                    Layout.alignment: Qt.AlignHCenter
                    text: Qt.formatDate(clock.date, "dddd, d MMMM")
                    color: Luna.Theme.foreground
                    font.family: Luna.Theme.uiFont
                    font.pixelSize: Math.max(12, Math.min(20, surface.width / 24))
                }
            }
        }
    }
}
