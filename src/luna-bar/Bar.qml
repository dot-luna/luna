pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import Quickshell.Hyprland
import Luna as Luna
import "components"

PanelWindow {
    id: bar

    readonly property int activeWorkspace: monitor && monitor.activeWorkspace ? monitor.activeWorkspace.id : 1
    property alias controlCenter: center
    property alias calendar: calendarPanel
    required property var controller
    required property var clockConfig
    required property var workspaceConfig
    property bool keyboardActive: false
    readonly property var monitor: Hyprland.monitors.values.find(item => item.name === screen.name)
    readonly property bool fullscreenActive: !!(monitor && monitor.activeWorkspace && monitor.activeWorkspace.hasFullscreen)
    onActiveWorkspaceChanged: {
        if (calendarPanel) calendarPanel.dismiss();
        if (center) center.dismiss();
    }
    readonly property var workspaceIds: {
        const ids = [1, 2, 3, 4];
        // Keep the baseline compact and add higher workspaces only while they exist.
        for (const workspace of Hyprland.workspaces.values) {
            if (workspace.id > 4 && !ids.includes(workspace.id))
                ids.push(workspace.id);
        }
        if (activeWorkspace > 4 && !ids.includes(activeWorkspace))
            ids.push(activeWorkspace);
        return ids.sort((a, b) => a - b);
    }

    function beginFocus() {
        if (!visible)
            return;
        keyboardActive = true;
        focusDelay.restart();
    }
    function controls() {
        const result = [];
        for (let i = 0; i < workspaces.count; i++)
            result.push(workspaces.itemAt(i));
        result.push(clockButton);
        result.push(statusButton);
        return result;
    }
    function release() {
        keyboardActive = false;
        center.visible = false;
        calendarPanel.visible = false;
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
    exclusiveZone: visible ? implicitHeight : 0
    implicitHeight: Luna.Theme.barHeight
    visible: !fullscreenActive

    onVisibleChanged: {
        if (!visible) {
            keyboardActive = false;
            focusDelay.stop();
            if (center)
                center.visible = false;
            if (calendarPanel)
                calendarPanel.visible = false;
        }
    }

    margins {
        left: Luna.Theme.outerGap
        right: Luna.Theme.outerGap
        top: Luna.Theme.outerGap
    }

    anchors {
        left: true
        right: true
        top: true
    }
    Timer {
        id: focusDelay

        interval: 50

        onTriggered: workspaces.itemAt(Math.max(0, bar.workspaceIds.indexOf(bar.activeWorkspace))).forceActiveFocus(Qt.TabFocusReason)
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
        border.color: Luna.Theme.muted
        border.width: Luna.Theme.borderWidth
        color: Luna.Theme.background
        radius: Math.min(Luna.Theme.barRounding, width / 2, height / 2)
    }
    RowLayout {
        anchors.left: parent.left
        anchors.leftMargin: 8
        anchors.verticalCenter: parent.verticalCenter
        spacing: 2

        Repeater {
            id: workspaces

            model: bar.workspaceIds

            delegate: Button {
                id: workspaceButton

                required property int modelData
                readonly property bool active: bar.activeWorkspace === workspace
                readonly property int workspace: modelData
                readonly property string workspaceLabel: workspace === 10 ? "0" : String(workspace)
                readonly property var indicatorConfig: active
                    ? (bar.workspaceConfig.overrides[workspaceLabel] || bar.workspaceConfig.active)
                    : bar.workspaceConfig.inactive

                Accessible.name: "Workspace " + workspaceLabel
                focusPolicy: Qt.StrongFocus
                implicitHeight: Math.max(24, Luna.Theme.barHeight - 6)
                implicitWidth: Math.max(22, workspaceIndicator.implicitWidth + 10)
                text: active ? workspaceLabel : ""

                background: Rectangle {
                    border.color: Luna.Theme.brightForeground
                    border.width: workspaceButton.visualFocus ? 2 : 0
                    color: "transparent"
                    radius: Math.min(Luna.Theme.barRounding, width / 2, height / 2)
                }
                contentItem: WorkspaceIndicator {
                    id: workspaceIndicator

                    active: workspaceButton.active
                    indicator: workspaceButton.indicatorConfig
                    workspaceLabel: workspaceButton.workspaceLabel
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

    SystemClock {
        id: clock

        precision: SystemClock.Minutes
    }
    Button {
        id: clockButton
        anchors.centerIn: parent
        Accessible.name: "Open calendar"
        focusPolicy: Qt.StrongFocus
        implicitHeight: Luna.Theme.barHeight - 4
        implicitWidth: contentItem.implicitWidth + 16
        background: Rectangle {
            color: "transparent"
            border.width: clockButton.visualFocus ? 1 : 0
            border.color: Luna.Theme.accent
            radius: Luna.Theme.barRounding
        }
        contentItem: Label {
            color: Luna.Theme.brightForeground
            font.family: Luna.Theme.uiFont
            font.pixelSize: 13
            font.weight: Font.Medium
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            text: Qt.formatDateTime(clock.date, bar.clockConfig.format)
        }
        onClicked: bar.controller.toggleCalendar(bar)
    }
    // Fixed slots prevent layout stretching; glyph sizes balance Lucide's differing shapes.
    component TriggerIcon: Item {
        required property string symbol
        property int glyphSize: 16
        property int opticalOffset: 0
        Layout.minimumWidth: 18
        Layout.maximumWidth: 18
        Layout.preferredWidth: 18
        Layout.minimumHeight: 20
        Layout.maximumHeight: 20
        Layout.preferredHeight: 20
        Layout.alignment: Qt.AlignVCenter

        Luna.Icon {
            anchors.centerIn: parent
            anchors.verticalCenterOffset: parent.opticalOffset
            width: parent.glyphSize
            height: parent.glyphSize
            name: parent.symbol
        }
    }
    Button {
        id: statusButton

        Accessible.name: "Open control center"
        anchors.right: parent.right
        anchors.rightMargin: 8
        anchors.verticalCenter: parent.verticalCenter
        focusPolicy: Qt.StrongFocus
        implicitHeight: Luna.Theme.barHeight - 4
        implicitWidth: statuses.implicitWidth + 16
        leftPadding: 8
        rightPadding: 8
        topPadding: 0
        bottomPadding: 0

        background: Rectangle {
            border.color: Luna.Theme.brightForeground
            border.width: statusButton.visualFocus ? 2 : 0
            color: statusButton.hovered ? Luna.Theme.selection : "transparent"
            radius: Math.min(Luna.Theme.barRounding, width / 2, height / 2)
        }
        contentItem: RowLayout {
            id: statuses

            spacing: 7

            TriggerIcon {
                symbol: Desktop.wifiIcon
                opticalOffset: -1
                visible: Desktop.wifiAvailable && Desktop.wifiEnabled
            }
            TriggerIcon {
                symbol: Desktop.bluetoothIcon
                glyphSize: 13
                visible: Desktop.bluetoothEnabled
            }
            TriggerIcon {
                symbol: Desktop.volumeIcon
            }
            RowLayout {
                Layout.alignment: Qt.AlignVCenter
                spacing: 4
                TriggerIcon {
                    symbol: Desktop.batteryIcon
                    glyphSize: 18
                }
                Label {
                    Layout.alignment: Qt.AlignVCenter
                    font.family: Luna.Theme.uiFont
                    color: Luna.Theme.foreground
                    font.pixelSize: 11
                    text: Desktop.batteryText
                    visible: Desktop.hasBattery
                }
            }
        }

        Keys.onEnterPressed: click()
        Keys.onReturnPressed: click()
        onClicked: bar.controller.toggleControls(bar)
    }
    ControlCenter {
        id: center

        screen: bar.screen
        topOffset: bar.implicitHeight + bar.margins.top
    }
    CalendarPopover {
        id: calendarPanel
        config: bar.clockConfig
        currentDate: clock.date
        screen: bar.screen
        topOffset: bar.implicitHeight + bar.margins.top
    }
}
