pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Hyprland
import Luna as Luna

ShellRoot {
    id: shell
    property bool showing: false
    property bool inputReady: false
    property bool stayAwake: false
    property string focusedScreen: ""
    property var config: JSON.parse(Quickshell.env("LUNA_IDLE_CONFIG"))
    property string pendingAction: ""
    readonly property string lunaCli: Quickshell.shellDir + "/../../bin/luna"

    function awakeStatus() {
        return JSON.stringify({enabled: stayAwake});
    }
    function setAwake(action) {
        if (!["on", "off", "toggle"].includes(action))
            return JSON.stringify({error: "Unknown Stay awake action"});

        const enabled = action === "toggle" ? !stayAwake : action === "on";
        // Clear queued idle work before disabling the monitors, including an in-flight lock check.
        if (enabled) hide();
        stayAwake = enabled;
        return awakeStatus();
    }
    function hide() {
        pendingAction = "";
        showing = false;
        inputReady = false;
        inputDelay.stop();
    }
    function request(action) {
        if (stayAwake && (action === "auto" || action === "lock"))
            return;
        if (locker.running)
            return;
        if (lockCheck.running) {
            if (action === "lock")
                pendingAction = action;
            return;
        }
        pendingAction = action;
        lockCheck.running = true;
    }

    IpcHandler {
        target: "screensaver"
        function ping(): string { return "ready"; }
        function awakeStatus(): string { return shell.awakeStatus(); }
        function setAwake(action: string): string { return shell.setAwake(action); }
        function status(): string {
            return JSON.stringify({showing: shell.showing, idle: saverIdle.isIdle, config: shell.config, pending: shell.pendingAction});
        }
        function open(): void { shell.request("show"); }
        function hide(): void { shell.hide(); }
        function stop(): void { Qt.quit(); }
        function applyFonts(value: string): void { Luna.Theme.applyFonts(JSON.parse(value)); }
        function configure(value: string): void { shell.config = JSON.parse(value); shell.hide(); }
    }
    IdleMonitor {
        id: saverIdle
        enabled: !shell.stayAwake && shell.config.screensaver_seconds > 0
        timeout: shell.config.screensaver_seconds
        respectInhibitors: true
        onIsIdleChanged: {
            if (isIdle) shell.request("auto");
            else {
                if (shell.pendingAction === "auto")
                    shell.pendingAction = "";
                shell.hide();
            }
        }
    }
    IdleMonitor {
        id: lockIdle
        enabled: !shell.stayAwake && shell.config.lock_seconds > 0
        timeout: shell.config.lock_seconds
        respectInhibitors: true
        onIsIdleChanged: if (isIdle) shell.request("lock")
    }
    Process {
        id: lockCheck
        command: ["hyprctl", "-j", "locked"]
        stdout: StdioCollector {}
        stderr: StdioCollector {}
        onExited: (code, status) => {
            if (code !== 0)
                return;
            try {
                if (JSON.parse(stdout.text).locked) {
                    shell.hide();
                    return;
                }
                if (shell.pendingAction === "lock") {
                    shell.hide();
                    locker.running = true;
                } else if (shell.pendingAction) {
                    shell.focusedScreen = Hyprland.focusedMonitor?.name || Quickshell.screens[0]?.name || "";
                    shell.showing = true;
                    inputDelay.restart();
                }
            } catch (error) {
                console.warn("Cannot read lock state:", error);
            }
        }
    }
    Process {
        id: locker
        command: [shell.lunaCli, "lock"]
        stdout: StdioCollector {}
        stderr: StdioCollector {}
        onExited: (code, status) => {
            if (code !== 0) {
                console.warn("Auto-lock failed:", stderr.text);
                Quickshell.execDetached(["env", "-u", "LD_LIBRARY_PATH", "-u", "LD_PRELOAD", "notify-send", "--app-name=Luna", "--urgency=critical", "Luna auto-lock failed", "Run luna lock to check the error."]);
            }
        }
    }
    Timer {
        id: inputDelay
        interval: 300
        onTriggered: shell.inputReady = true
    }
    SystemClock { id: clock; precision: SystemClock.Minutes }

    Variants {
        model: Quickshell.screens
        delegate: PanelWindow {
            id: surface
            required property var modelData
            screen: modelData
            visible: shell.showing
            color: Luna.Theme.background
            exclusionMode: ExclusionMode.Ignore
            WlrLayershell.namespace: "luna-screensaver"
            WlrLayershell.layer: WlrLayer.Overlay
            WlrLayershell.keyboardFocus: visible && modelData.name === shell.focusedScreen ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
            anchors { top: true; bottom: true; left: true; right: true }

            Item {
                anchors.fill: parent
                focus: true
                Keys.onPressed: event => { event.accepted = true; shell.hide(); }

                ColumnLayout {
                    anchors.centerIn: parent
                    spacing: 14
                    transform: Translate {
                        id: drift
                        SequentialAnimation on x {
                            running: shell.showing
                            loops: Animation.Infinite
                            NumberAnimation { from: -35; to: 35; duration: 45000; easing.type: Easing.InOutSine }
                            NumberAnimation { from: 35; to: -35; duration: 45000; easing.type: Easing.InOutSine }
                        }
                        SequentialAnimation on y {
                            running: shell.showing
                            loops: Animation.Infinite
                            NumberAnimation { from: -20; to: 20; duration: 60000; easing.type: Easing.InOutSine }
                            NumberAnimation { from: 20; to: -20; duration: 60000; easing.type: Easing.InOutSine }
                        }
                    }
                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        text: "luna"
                        color: Luna.Theme.accent
                        font.family: Luna.Theme.uiFont
                        font.pixelSize: 20
                        font.letterSpacing: 5
                    }
                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        text: Qt.formatTime(clock.date, Qt.locale().timeFormat(Locale.ShortFormat))
                        color: Luna.Theme.brightForeground
                        font.family: Luna.Theme.uiFont
                        font.pixelSize: Math.min(96, surface.width / 8)
                        font.weight: Font.Light
                    }
                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        text: Qt.formatDate(clock.date, "dddd, d MMMM")
                        color: Luna.Theme.foreground
                        font.family: Luna.Theme.uiFont
                        font.pixelSize: 20
                    }
                }
                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    acceptedButtons: Qt.AllButtons
                    cursorShape: Qt.BlankCursor
                    onPressed: shell.hide()
                    onWheel: shell.hide()
                    onPositionChanged: if (shell.inputReady) shell.hide()
                }
            }
        }
    }
}
