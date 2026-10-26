pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Hyprland
import Luna as Luna
import "notifications"
import "bluetooth"

ShellRoot {
    id: shell

    readonly property var config: JSON.parse(Quickshell.env("LUNA_BAR_CONFIG"))
    readonly property var notifications: notificationStore

    // Quickshell updates workspace flags on fullscreen events, but the bar also
    // needs fresh client modes to distinguish maximized from actual fullscreen.
    Connections {
        target: Hyprland
        function onRawEvent(event) {
            if (["fullscreen", "openwindow", "movewindowv2"].includes(event.name))
                Hyprland.refreshToplevels();
        }
    }

    // Session helpers are shared by every monitor; only their visible surfaces follow focus.
    HardwareControls {
        id: hardware
        screen: shell.focusedBar() ? shell.focusedBar().screen : null
    }
    BatteryAlerts {}
    BluetoothAgent {
        screen: shell.focusedBar() ? shell.focusedBar().screen : null
        onPrompted: shell.release()
    }
    RecordingIndicator {
        id: recordingIndicator
        screen: shell.focusedBar() ? shell.focusedBar().screen : null
    }

    NotificationStore { id: notificationStore }
    NotificationSound {
        id: notificationSound
        enabled: !notificationStore.dnd && !notificationStore.panelOpen
    }
    Connections {
        target: notificationStore
        function onSoundRequested(urgency: int) {
            notificationSound.play(urgency);
        }
    }
    NotificationPanel { id: notificationPanel; store: notificationStore; topOffset: Luna.Theme.barHeight + Luna.Theme.outerGap }
    NotificationPopups {
        store: notificationStore
        screen: shell.focusedBar() ? shell.focusedBar().screen : Quickshell.screens[0]
        topOffset: Luna.Theme.barHeight + Luna.Theme.outerGap
        onOpenHistory: {
            const bar = shell.focusedBar();
            if (bar)
                shell.toggleNotifications(bar);
        }
    }
    // Clicking another monitor dismisses history, including clicks on empty desktop.
    Variants {
        model: Quickshell.screens
        delegate: PanelWindow {
            required property var modelData
            screen: modelData
            visible: notificationPanel.visible && notificationPanel.screen
                && modelData.name !== notificationPanel.screen.name
            color: "transparent"
            anchors { top: true; bottom: true; left: true; right: true }
            exclusionMode: ExclusionMode.Ignore
            WlrLayershell.layer: WlrLayer.Overlay
            WlrLayershell.namespace: "luna-notification-dismiss"
            WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
            MouseArea {
                anchors.fill: parent
                acceptedButtons: Qt.AllButtons
                onPressed: notificationPanel.dismiss()
            }
        }
    }

    function toggleNotifications(bar) {
        const wasOpen = notificationPanel.visible && notificationPanel.screen === bar.screen;
        release();
        if (!wasOpen) {
            notificationPanel.screen = bar.screen;
            notificationPanel.open();
        }
    }
    function dismissNotifications(bar) {
        if (notificationPanel && notificationPanel.screen === bar.screen)
            notificationPanel.dismiss();
    }

    function focusBar() {
        const bar = focusedBar();
        release();
        if (bar)
            bar.beginFocus();
    }
    function focusedBar() {
        const name = Hyprland.focusedMonitor ? Hyprland.focusedMonitor.name : "";
        return bars.instances.find(bar => bar.screen.name === name) || bars.instances[0];
    }
    function release() {
        notificationPanel.dismiss();
        for (const bar of bars.instances)
            bar.release();
    }
    function toggleControls(bar) {
        if (!bar.visible)
            return;
        const wasOpen = bar.controlCenter.visible;
        release();
        if (!wasOpen)
            bar.controlCenter.open();
    }
    function toggleCalendar(bar) {
        if (!bar.visible)
            return;
        const wasOpen = bar.calendar.visible;
        release();
        if (!wasOpen)
            bar.calendar.open();
    }

    // Keyboard shortcuts use scoped IPC rather than trying to focus a layer by title.
    IpcHandler {
        function control(action: string): bool {
            if (["play-pause", "next", "previous"].includes(action))
                return Media.run(action);
            return hardware.run(action);
        }
        function hardwareStatus(): string {
            return hardware.status();
        }
        function recordingChanged(): void {
            recordingIndicator.refresh();
        }
        function notifications(): void {
            const bar = shell.focusedBar();
            if (bar)
                shell.toggleNotifications(bar);
        }
        function dnd(): void {
            notificationStore.dnd = !notificationStore.dnd;
        }
        function notificationStatus(): string {
            return JSON.stringify({running: true, dnd: notificationStore.dnd,
                unread: notificationStore.unreadCount, count: notificationStore.entries.length,
                popups: notificationStore.popupEntries.length});
        }
        function clearNotifications(): void {
            notificationStore.clear();
        }
        function removeNotification(id: int): void {
            notificationStore.remove(id);
        }
        function controls(): void {
            const bar = shell.focusedBar();
            if (bar)
                shell.toggleControls(bar);
        }
        function focus(): void {
            shell.focusBar();
        }
        function applyFonts(value: string): void {
            Luna.Theme.applyFonts(JSON.parse(value));
        }
        function ping(): string {
            return "ready";
        }
        function stop(): void {
            Qt.quit();
        }

        target: "bar"
    }
    Variants {
        id: bars

        model: Quickshell.screens

        delegate: Bar {
            required property var modelData

            controller: shell
            workspaceConfig: shell.config.workspaces
            clockConfig: shell.config.clock
            screen: modelData
        }
    }
}
