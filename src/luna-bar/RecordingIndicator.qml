pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Luna as Luna

// Stay available above fullscreen windows until the recorder finishes the file.
PanelWindow {
    id: indicator

    property bool recording: false
    property bool stopping: false
    property bool refreshPending: false
    readonly property string helper: Quickshell.shellDir + "/../luna-cli/record/record.py"
    readonly property string runtimePath: Quickshell.env("XDG_RUNTIME_DIR")
        ? Quickshell.env("XDG_RUNTIME_DIR") + "/luna-recording/state.json" : ""

    function refresh() {
        if (stateCheck.running) {
            refreshPending = true;
            return;
        }
        refreshPending = false;
        stateCheck.running = true;
    }
    visible: recording
    color: "transparent"
    anchors { bottom: true; right: true }
    margins { bottom: 16; right: 16 }
    implicitWidth: 98
    implicitHeight: 38
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "luna-recording"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

    FileView {
        path: indicator.runtimePath
        watchChanges: true
        printErrors: false
        onFileChanged: indicator.refresh()
    }
    Process {
        id: stateCheck
        command: ["python", indicator.helper, "status"]
        running: true
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    indicator.recording = JSON.parse(text).running === true;
                } catch (error) {
                    indicator.recording = false;
                }
            }
        }
        stderr: StdioCollector {}
        onExited: {
            // A write can arrive after this query read the old state but before its output arrives.
            if (indicator.refreshPending)
                Qt.callLater(indicator.refresh);
        }
    }
    // Reconcile unexpected worker exits without polling when the recorder is idle.
    Timer {
        interval: 2000
        running: indicator.recording
        repeat: true
        onTriggered: indicator.refresh()
    }
    Process {
        id: stopper
        command: ["python", indicator.helper, "stop"]
        stdout: StdioCollector {}
        stderr: StdioCollector {}
        onExited: {
            indicator.stopping = false;
            indicator.refresh();
        }
    }
    Button {
        id: stopButton
        anchors.fill: parent
        enabled: !indicator.stopping
        Accessible.name: "Stop recording"
        onClicked: {
            indicator.stopping = true;
            stopper.running = true;
        }
        background: Rectangle {
            color: stopButton.hovered ? Luna.Theme.selection : Luna.Theme.background
            border.color: Luna.Theme.colors.error
            border.width: 1
            radius: Math.min(10, Luna.Theme.barRounding)
        }
        contentItem: RowLayout {
            spacing: 8
            Rectangle {
                Layout.leftMargin: 14
                width: 10
                height: 10
                color: Luna.Theme.colors.error
                radius: 2
            }
            Label {
                Layout.fillWidth: true
                text: indicator.stopping ? "Saving…" : "Stop"
                color: Luna.Theme.brightForeground
                font.family: Luna.Theme.uiFont
                font.pixelSize: 12
            }
        }
    }
}
