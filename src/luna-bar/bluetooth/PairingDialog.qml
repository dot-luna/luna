pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Wayland

PanelWindow {
    id: panel

    property var request: null
    property string error: ""
    signal accepted(string value)
    signal cancelled()

    visible: request !== null
    color: "transparent"
    anchors { top: true; bottom: true; left: true; right: true }
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "luna-bluetooth-pairing"
    WlrLayershell.keyboardFocus: visible ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None

    Shortcut {
        enabled: panel.visible
        sequence: "Escape"
        context: Qt.ApplicationShortcut
        onActivated: panel.cancelled()
        onActivatedAmbiguously: panel.cancelled()
    }
    Rectangle { anchors.fill: parent; color: "#66000000" }
    MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons }
    PairingContent {
        anchors.centerIn: parent
        width: Math.max(0, Math.min(410, panel.width - 32))
        request: panel.request
        error: panel.error
        onAccepted: value => panel.accepted(value)
        onCancelled: panel.cancelled()
    }
}
