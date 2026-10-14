pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import Luna as Luna
import "../components"

PanelWindow {
    id: panel

    required property var store
    property int topOffset: 32

    function open() {
        visible = true;
        store.panelOpen = true;
        store.markRead();
        focusDelay.restart();
    }
    function dismiss() {
        visible = false;
    }
    function stepFocus(direction) {
        const controls = [];
        function visit(item) {
            if (!item.visible || !item.enabled) return;
            if ((item instanceof Button || item instanceof NotificationCard) && item.activeFocusOnTab)
                controls.push(item);
            for (const child of item.children) visit(child);
        }
        visit(body);
        if (!controls.length) return;
        const index = controls.findIndex(item => item.activeFocus);
        const next = index < 0 ? (direction < 0 ? controls.length - 1 : 0)
            : (index + direction + controls.length) % controls.length;
        const target = controls[next];
        target.forceActiveFocus(Qt.TabFocusReason);

        // Header buttons should not move history; map list controls before its scroll offset.
        let ancestor = target.parent;
        while (ancestor && ancestor !== entries) ancestor = ancestor.parent;
        if (ancestor !== entries || !history.contentItem) return;
        const view = history.contentItem;
        const y = target.mapToItem(entries, 0, 0).y;
        let offset = view.contentY;
        if (y < offset) offset = y;
        else if (y + (target instanceof NotificationCard ? Math.min(target.height, 48) : target.height) > offset + history.availableHeight)
            offset = y + (target instanceof NotificationCard ? Math.min(target.height, 48) : target.height) - history.availableHeight;
        view.contentY = Math.max(0, Math.min(offset, view.contentHeight - history.availableHeight));
    }

    visible: false
    color: "transparent"
    exclusionMode: ExclusionMode.Ignore
    anchors { top: true; right: true; bottom: true; left: true }
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "luna-notifications"
    WlrLayershell.keyboardFocus: visible ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
    onVisibleChanged: {
        if (!visible) {
            focusDelay.stop();
            store.panelOpen = false;
        }
    }

    Timer {
        id: focusDelay
        interval: 50
        onTriggered: if (panel.visible) dndButton.forceActiveFocus(Qt.TabFocusReason)
    }
    Shortcut {
        enabled: panel.visible
        sequence: "Escape"
        context: Qt.ApplicationShortcut
        onActivated: panel.dismiss()
        onActivatedAmbiguously: panel.dismiss()
    }
    Shortcut { enabled: panel.visible; sequence: "Tab"; onActivated: panel.stepFocus(1) }
    Shortcut { enabled: panel.visible; sequence: "Shift+Tab"; onActivated: panel.stepFocus(-1) }
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.AllButtons
        onPressed: panel.dismiss()
    }

    Rectangle {
        id: frame
        anchors.top: parent.top
        anchors.topMargin: panel.topOffset + Luna.Theme.outerGap
        anchors.right: parent.right
        anchors.rightMargin: Luna.Theme.outerGap
        width: Math.min(400, Math.max(0, panel.width - 2 * Luna.Theme.outerGap))
        height: Math.min(680, Math.max(0, panel.height - y - Luna.Theme.outerGap))
        color: Luna.Theme.background
        border.color: Luna.Theme.muted
        border.width: Luna.Theme.borderWidth
        radius: Math.max(0, Math.min(14, Luna.Theme.barRounding))
        clip: true

        MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons }

        ColumnLayout {
            id: body
            anchors.fill: parent
            anchors.margins: 16
            spacing: 14

            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                Luna.Icon { name: "bell"; ink: Luna.Theme.accent; implicitWidth: 18; implicitHeight: 18 }
                Label {
                    Layout.fillWidth: true
                    text: "Notifications"
                    color: Luna.Theme.brightForeground
                    font.family: Luna.Theme.uiFont
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                }
                ActionButton {
                    symbol: "trash"
                    enabled: panel.store.entries.length > 0
                    Accessible.name: "Clear all notifications"
                    ToolTip.visible: hovered
                    ToolTip.delay: 600
                    ToolTip.text: "Clear all"
                    onClicked: panel.store.clear()
                }
            }
            Button {
                id: dndButton
                Layout.fillWidth: true
                implicitHeight: 44
                padding: 12
                checkable: true
                checked: panel.store.dnd
                focusPolicy: Qt.StrongFocus
                Accessible.name: "Do Not Disturb"
                onClicked: panel.store.dnd = checked
                background: Rectangle {
                    color: dndButton.hovered ? Luna.Theme.selection : Luna.Theme.lighterBackground
                    border.color: dndButton.visualFocus ? Luna.Theme.brightForeground : dndButton.checked ? Qt.alpha(Luna.Theme.accent, 0.55) : "transparent"
                    border.width: 1
                    radius: Math.min(8, Luna.Theme.barRounding)
                }
                contentItem: RowLayout {
                    spacing: 10
                    Luna.Icon {
                        name: dndButton.checked ? "bell-off" : "bell"
                        ink: dndButton.checked ? Luna.Theme.accent : Luna.Theme.foreground
                        implicitWidth: 18
                        implicitHeight: 18
                    }
                    Label {
                        Layout.fillWidth: true
                        text: "Do Not Disturb"
                        font.family: Luna.Theme.uiFont
                        font.pixelSize: 12
                        font.weight: Font.Medium
                        color: Luna.Theme.brightForeground
                    }
                    Rectangle {
                        implicitWidth: 32
                        implicitHeight: 18
                        radius: 9
                        color: dndButton.checked ? Luna.Theme.accent : Luna.Theme.muted
                        Rectangle {
                            x: dndButton.checked ? 16 : 3
                            y: 3
                            width: 12
                            height: 12
                            radius: 6
                            color: dndButton.checked ? Luna.Theme.accentForeground : Luna.Theme.brightForeground
                        }
                    }
                }
                Keys.onReturnPressed: click()
                Keys.onEnterPressed: click()
            }
            ScrollView {
                id: history
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: panel.store.entries.length > 0
                contentWidth: availableWidth
                contentHeight: entries.implicitHeight
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                ColumnLayout {
                    id: entries
                    width: history.availableWidth
                    spacing: 10
                    Repeater {
                        model: panel.store.entries
                        delegate: NotificationCard {
                            id: historyCard
                            required property var modelData
                            Layout.fillWidth: true
                            entry: modelData
                            onOpened: {
                                if (panel.store.open(entry.id)) panel.dismiss();
                                else historyCard.toggleExpanded();
                            }
                            onRemoved: panel.store.remove(entry.id)
                            onDismissed: panel.store.dismiss(entry.id)
                            onActionInvoked: identifier => {
                                panel.dismiss();
                                panel.store.invoke(entry.id, identifier);
                            }
                        }
                    }
                }
            }
            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: panel.store.entries.length === 0
                Label {
                    anchors.centerIn: parent
                    width: parent.width
                    text: "All caught up"
                    color: Luna.Theme.foreground
                    font.family: Luna.Theme.uiFont
                    font.pixelSize: 13
                    horizontalAlignment: Text.AlignHCenter
                }
            }
        }
    }
}
