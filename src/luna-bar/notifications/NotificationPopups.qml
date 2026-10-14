pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import Luna as Luna

// A small non-focusable layer leaves the active app's keyboard focus untouched.
PanelWindow {
    id: popups

    required property var store
    property int topOffset: 32
    signal openHistory()

    anchors { top: true; right: true }
    margins.top: topOffset + Luna.Theme.outerGap
    margins.right: Luna.Theme.outerGap
    implicitWidth: Math.min(380, screen ? screen.width - 2 * Luna.Theme.outerGap : 380)
    implicitHeight: Math.min(cards.implicitHeight, screen ? Math.max(0, screen.height - margins.top - Luna.Theme.outerGap) : cards.implicitHeight)
    color: "transparent"
    exclusionMode: ExclusionMode.Ignore
    visible: store.popupEntries.length > 0 && !store.panelOpen
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "luna-notification-popups"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

    ScrollView {
        id: scroll
        anchors.fill: parent
        contentWidth: availableWidth
        contentHeight: cards.implicitHeight
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        ColumnLayout {
            id: cards
            width: scroll.availableWidth
            spacing: 10

            Repeater {
                model: popups.store.popupEntries.slice(0, 3)
                delegate: NotificationCard {
                    required property var modelData
                    Layout.fillWidth: true
                    entry: modelData
                    popup: true
                    onOpened: if (!popups.store.open(entry.id)) popups.openHistory()
                    onDismissed: popups.store.dismiss(entry.id)
                    onRemoved: popups.store.remove(entry.id)
                    onActionInvoked: identifier => popups.store.invoke(entry.id, identifier)
                    onHoverStateChanged: hovered => popups.store.setHovered(entry.id, hovered)
                }
            }
        }
    }
}
