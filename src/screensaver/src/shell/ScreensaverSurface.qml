pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Wayland
import Luna as Luna

// Custom shells supply the screen and visual children. The surface owns wake
// input and session communication; it is a screensaver window, not a session lock.
PanelWindow {
    id: surface

    default property alias contentData: visuals.data
    readonly property var settings: Luna.ScreensaverSession.settings
    readonly property bool hasHyprland: !!Quickshell.env("HYPRLAND_INSTANCE_SIGNATURE")
    readonly property var monitor: hasHyprland && screen ? Hyprland.monitorFor(screen) : null
    readonly property bool outputActive: !monitor || !monitor.lastIpcObject
        || (monitor.lastIpcObject.dpmsStatus !== false && monitor.lastIpcObject.disabled !== true)
    readonly property bool renderingActive: visible && backingWindowVisible && !!screen && outputActive
    readonly property bool keyboardFocused: !!screen && screen.name === Luna.ScreensaverSession.focusedScreen
    property bool inputReady: false

    visible: !!screen
    color: Luna.Theme.background
    anchors { top: true; bottom: true; left: true; right: true }
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "luna-screensaver"
    WlrLayershell.keyboardFocus: visible && keyboardFocused ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None

    function reportReady() {
        if (visible && backingWindowVisible && screen && width > 0 && height > 0)
            Luna.ScreensaverSession.ready();
    }

    function wake() {
        Luna.ScreensaverSession.dismiss();
    }

    function windowChanged() {
        inputReady = false;
        openingGrace.stop();
        if (visible && backingWindowVisible) {
            openingGrace.start();
            Qt.callLater(reportReady);
            if (keyboardFocused) Qt.callLater(wakeInput.forceActiveFocus);
        }
    }

    onBackingWindowVisibleChanged: windowChanged()
    onWidthChanged: Qt.callLater(reportReady)
    onHeightChanged: Qt.callLater(reportReady)
    onScreenChanged: Qt.callLater(reportReady)
    onKeyboardFocusedChanged: if (keyboardFocused && visible) Qt.callLater(wakeInput.forceActiveFocus)

    // Initial pointer placement must not immediately wake a newly shown surface.
    // Deliberate key presses, clicks and scrolling still dismiss immediately.
    Timer {
        id: openingGrace
        interval: 300
        onTriggered: surface.inputReady = true
    }

    Item {
        id: visuals
        anchors.fill: parent
        clip: true
    }

    Item {
        id: wakeInput
        objectName: "screensaverWakeInput"
        anchors.fill: parent
        z: 1000000
        focus: true
        Keys.onPressed: event => { event.accepted = true; surface.wake(); }
        Keys.onReleased: event => { event.accepted = true; }

        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.AllButtons
            cursorShape: Qt.BlankCursor
            onPressed: event => { event.accepted = true; surface.wake(); }
            onReleased: event => { event.accepted = true; }
            onWheel: event => { event.accepted = true; surface.wake(); }
            onPositionChanged: if (surface.inputReady) surface.wake()
        }
    }
}
