import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Window
import Quickshell
import Quickshell.Wayland
import Luna as Luna
import "components"

// An input overlay makes outside-click dismissal and keyboard focus predictable.
PanelWindow {
    id: panel

    property int topOffset: 32

    function controls() {
        return [closeButton, wifiButton, bluetoothButton, muteButton, volumeSlider, brightnessSlider].filter(item => item.enabled && item.visible);
    }
    function open() {
        Desktop.refreshBrightness();
        visible = true;
        focusDelay.restart();
    }
    function stepFocus(direction) {
        const items = controls();
        const focused = contentItem.Window.window.activeFocusItem;
        let current = items.findIndex(item => item === focused || item.activeFocus);
        items[(current + direction + items.length) % items.length].forceActiveFocus(Qt.TabFocusReason);
    }

    WlrLayershell.keyboardFocus: visible ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "luna-control-center"
    color: "transparent"
    exclusionMode: ExclusionMode.Ignore
    visible: false

    anchors {
        bottom: true
        left: true
        right: true
        top: true
    }
    Timer {
        id: focusDelay

        interval: 50

        onTriggered: closeButton.forceActiveFocus(Qt.TabFocusReason)
    }
    Shortcut {
        enabled: panel.visible
        sequence: "Escape"

        onActivated: panel.visible = false
    }
    Shortcut {
        enabled: panel.visible
        sequence: "Tab"

        onActivated: panel.stepFocus(1)
    }
    Shortcut {
        enabled: panel.visible
        sequence: "Shift+Tab"

        onActivated: panel.stepFocus(-1)
    }
    MouseArea {
        anchors.fill: parent

        onClicked: panel.visible = false
    }
    Rectangle {
        id: card

        anchors.right: parent.right
        anchors.rightMargin: 10
        anchors.top: parent.top
        anchors.topMargin: panel.topOffset + 10
        border.color: Luna.Theme.muted
        border.width: 1
        color: Luna.Theme.background
        height: body.implicitHeight + 36
        radius: 16
        width: Math.min(380, panel.width - 20)

        MouseArea {
            anchors.fill: parent
        }
        ColumnLayout {
            id: body

            anchors.left: parent.left
            anchors.margins: 18
            anchors.right: parent.right
            anchors.top: parent.top
            spacing: 16

            RowLayout {
                Layout.fillWidth: true

                Label {
                    Layout.fillWidth: true
                    color: Luna.Theme.brightForeground
                    font.bold: true
                    font.pixelSize: 16
                    text: "Control Center"
                }
                ActionButton {
                    id: closeButton

                    symbol: "x"
                    text: "Close"

                    onClicked: panel.visible = false
                }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 10

                ActionButton {
                    id: wifiButton

                    Layout.fillWidth: true
                    enabled: Desktop.wifiAvailable && Desktop.wifiHardwareEnabled
                    implicitHeight: 58
                    selected: Desktop.wifiEnabled && Desktop.wifiAvailable
                    symbol: Desktop.wifiEnabled ? "wifi" : "wifi-off"
                    text: Desktop.wifiAvailable ? "Wi-Fi" : "No Wi-Fi"

                    onClicked: Desktop.toggleWifi()
                }
                ActionButton {
                    id: bluetoothButton

                    Layout.fillWidth: true
                    enabled: !!Desktop.adapter
                    implicitHeight: 58
                    selected: Desktop.bluetoothEnabled
                    symbol: "bluetooth"
                    text: "Bluetooth"

                    onClicked: Desktop.toggleBluetooth()
                }
            }
            Label {
                Layout.fillWidth: true
                color: Luna.Theme.foreground
                elide: Text.ElideRight
                font.pixelSize: 12
                text: Desktop.networkName
            }
            RowLayout {
                Layout.fillWidth: true

                ActionButton {
                    id: muteButton

                    enabled: Desktop.audioAvailable
                    symbol: Desktop.muted ? "volume-x" : "volume-2"
                    text: Desktop.muted ? "Unmute" : "Mute"

                    onClicked: Desktop.toggleMute()
                }
                LevelSlider {
                    id: volumeSlider

                    Accessible.name: "Volume"
                    Layout.fillWidth: true
                    enabled: Desktop.audioAvailable
                    value: Desktop.volume

                    onMoved: Desktop.setVolume(value)
                }
                Label {
                    Layout.preferredWidth: 38
                    color: Luna.Theme.foreground
                    text: Desktop.audioAvailable ? Math.round(Desktop.volume * 100) + "%" : "—"
                }
            }
            RowLayout {
                Layout.fillWidth: true
                visible: Desktop.brightnessAvailable

                Luna.Icon {
                    Layout.preferredWidth: 26
                    name: "sun"
                }
                LevelSlider {
                    id: brightnessSlider

                    Accessible.name: "Brightness"
                    Layout.fillWidth: true
                    from: 1
                    stepSize: 5
                    to: 100
                    value: Desktop.brightness
                    visible: Desktop.brightnessAvailable

                    onMoved: Desktop.setBrightness(value)
                }
                Label {
                    Layout.preferredWidth: 38
                    color: Luna.Theme.foreground
                    text: Desktop.brightness + "%"
                }
            }
            Rectangle {
                Layout.fillWidth: true
                color: Luna.Theme.muted
                implicitHeight: 1
            }
            RowLayout {
                Layout.fillWidth: true

                Luna.Icon {
                    name: Desktop.hasBattery ? "battery" : "monitor"
                }
                Label {
                    Layout.fillWidth: true
                    color: Luna.Theme.foreground
                    text: Desktop.batteryText
                }
                Label {
                    color: Luna.Theme.foreground
                    font.pixelSize: 11
                    text: "Esc to close"
                }
            }
            Label {
                Layout.fillWidth: true
                color: Luna.Theme.brightForeground
                text: Desktop.error
                visible: Desktop.error !== ""
                wrapMode: Text.WordWrap
            }
        }
    }
}
