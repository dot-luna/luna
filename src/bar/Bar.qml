pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import Quickshell.Hyprland
import Luna as Luna

PanelWindow {
    id: bar

    readonly property int activeWorkspace: monitor && monitor.activeWorkspace ? monitor.activeWorkspace.id : 1
    property alias controlCenter: center
    required property var controller
    property bool keyboardActive: false
    readonly property var monitor: Hyprland.monitors.values.find(item => item.name === screen.name)

    function beginFocus() {
        keyboardActive = true;
        focusDelay.restart();
    }
    function controls() {
        const result = [];
        for (let i = 0; i < workspaces.count; i++)
            result.push(workspaces.itemAt(i));
        result.push(statusButton);
        return result;
    }
    function release() {
        keyboardActive = false;
        center.visible = false;
    }
    function stepFocus(direction) {
        const items = controls();
        const current = items.findIndex(item => item.activeFocus);
        items[(current + direction + items.length) % items.length].forceActiveFocus(Qt.TabFocusReason);
    }

    WlrLayershell.keyboardFocus: keyboardActive ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
    WlrLayershell.layer: WlrLayer.Top
    WlrLayershell.namespace: "luna-bar"
    color: "transparent"
    exclusiveZone: implicitHeight
    implicitHeight: Luna.Theme.barHeight

    anchors {
        left: true
        right: true
        top: true
    }
    Timer {
        id: focusDelay

        interval: 50

        onTriggered: workspaces.itemAt(Math.max(0, Math.min(9, bar.activeWorkspace - 1))).forceActiveFocus(Qt.TabFocusReason)
    }
    Shortcut {
        enabled: bar.keyboardActive
        sequence: "Escape"

        onActivated: bar.release()
    }
    Shortcut {
        enabled: bar.keyboardActive
        sequence: "Tab"

        onActivated: bar.stepFocus(1)
    }
    Shortcut {
        enabled: bar.keyboardActive
        sequence: "Shift+Tab"

        onActivated: bar.stepFocus(-1)
    }
    Shortcut {
        enabled: bar.keyboardActive
        sequence: "Left"

        onActivated: bar.stepFocus(-1)
    }
    Shortcut {
        enabled: bar.keyboardActive
        sequence: "Right"

        onActivated: bar.stepFocus(1)
    }
    Rectangle {
        anchors.fill: parent
        color: Luna.Theme.background
        opacity: Luna.Theme.barOpacity
        radius: Luna.Theme.barRounding
    }
    RowLayout {
        anchors.left: parent.left
        anchors.leftMargin: 8
        anchors.verticalCenter: parent.verticalCenter
        spacing: 2

        Repeater {
            id: workspaces

            model: 10

            delegate: Button {
                id: workspaceButton

                required property int index
                readonly property bool occupied: Hyprland.workspaces.values.some(item => item.id === workspace)
                readonly property int workspace: index + 1

                Accessible.name: "Workspace " + workspace
                focusPolicy: Qt.StrongFocus
                implicitHeight: Math.max(24, Luna.Theme.barHeight - 6)
                implicitWidth: 26
                text: String(workspace)

                background: Rectangle {
                    border.color: Luna.Theme.brightForeground
                    border.width: workspaceButton.visualFocus ? 2 : 0
                    color: bar.activeWorkspace === workspaceButton.workspace ? Luna.Theme.accent : workspaceButton.hovered ? Luna.Theme.selection : "transparent"
                    radius: 5
                }
                contentItem: Label {
                    color: bar.activeWorkspace === workspaceButton.workspace ? Luna.Theme.accentForeground : workspaceButton.occupied ? Luna.Theme.brightForeground : Luna.Theme.foreground
                    font.bold: bar.activeWorkspace === workspaceButton.workspace
                    font.pixelSize: 12
                    horizontalAlignment: Text.AlignHCenter
                    opacity: workspaceButton.occupied || bar.activeWorkspace === workspaceButton.workspace ? 1 : 0.65
                    text: workspaceButton.text
                    verticalAlignment: Text.AlignVCenter
                }

                Keys.onEnterPressed: click()
                Keys.onReturnPressed: click()
                onClicked: {
                    Hyprland.dispatch("hl.dsp.focus({workspace=" + workspace + "})");
                    bar.release();
                }
            }
        }
    }

    // This label deliberately has no mouse handler or keyboard action.
    SystemClock {
        id: clock

        precision: SystemClock.Minutes
    }
    Label {
        anchors.centerIn: parent
        color: Luna.Theme.brightForeground
        font.pixelSize: 13
        font.weight: Font.Medium
        text: Qt.formatDateTime(clock.date, "ddd, MMM d  ·  HH:mm")
    }
    Button {
        id: statusButton

        Accessible.name: "Open control center"
        anchors.right: parent.right
        anchors.rightMargin: 8
        anchors.verticalCenter: parent.verticalCenter
        focusPolicy: Qt.StrongFocus
        implicitHeight: Luna.Theme.barHeight - 4
        implicitWidth: statuses.implicitWidth + 18

        background: Rectangle {
            border.color: Luna.Theme.brightForeground
            border.width: statusButton.visualFocus ? 2 : 0
            color: statusButton.hovered ? Luna.Theme.selection : "transparent"
            radius: 6
        }
        contentItem: RowLayout {
            id: statuses

            spacing: 12

            Luna.Icon {
                name: Desktop.wifiEnabled ? "wifi" : "wifi-off"
            }
            Luna.Icon {
                name: Desktop.muted ? "volume-x" : "volume-2"
            }
            Luna.Icon {
                name: "battery"
                visible: Desktop.hasBattery
            }
            Label {
                color: Luna.Theme.foreground
                font.pixelSize: 12
                text: Desktop.batteryText
                visible: Desktop.hasBattery
            }
            Luna.Icon {
                implicitHeight: 14
                implicitWidth: 14
                name: "chevron-down"
            }
        }

        Keys.onEnterPressed: click()
        Keys.onReturnPressed: click()
        onClicked: bar.controller.toggleControls(bar)
    }
    ControlCenter {
        id: center

        screen: bar.screen
        topOffset: bar.implicitHeight
    }
}
