pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland

ShellRoot {
    id: shell

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
        for (const bar of bars.instances)
            bar.release();
    }
    function toggleControls(bar) {
        const wasOpen = bar.controlCenter.visible;
        release();
        if (!wasOpen)
            bar.controlCenter.open();
    }

    // Keyboard shortcuts use scoped IPC rather than trying to focus a layer by title.
    IpcHandler {
        function controls(): void {
            const bar = shell.focusedBar();
            if (bar)
                shell.toggleControls(bar);
        }
        function focus(): void {
            shell.focusBar();
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
            screen: modelData
        }
    }
}
