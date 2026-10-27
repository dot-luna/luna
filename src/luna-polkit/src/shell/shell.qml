pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland
import Quickshell.Services.Polkit

// A separate shell keeps administrator prompts alive across bar and launcher reloads.
ShellRoot {
    id: shell

    readonly property bool validating: Quickshell.env("LUNA_POLKIT_VALIDATE") === "1"
    readonly property var agent: backend.item
    property var promptScreen: Quickshell.screens[0] || null

    Loader {
        id: backend
        active: !shell.validating
        sourceComponent: PolkitAgent {
            path: "/org/luna/Polkit"
            onAuthenticationRequestStarted: {
                const name = Hyprland.focusedMonitor ? Hyprland.focusedMonitor.name : "";
                shell.promptScreen = Quickshell.screens.find(screen => screen.name === name) || Quickshell.screens[0] || null;
            }
        }
    }

    AuthDialog {
        flow: shell.agent ? shell.agent.flow : null
        // Keep the prompt on its initial monitor; recover if that monitor is unplugged.
        screen: Quickshell.screens.includes(shell.promptScreen) ? shell.promptScreen : Quickshell.screens[0] || null
    }

    Timer {
        interval: 10000
        running: !shell.validating && (!shell.agent || !shell.agent.isRegistered)
        onTriggered: {
            console.error("Luna authentication could not register. Check that this is a desktop session and no other polkit agent is running.");
            Qt.exit(1);
        }
    }

    IpcHandler {
        target: "auth"
        function ping(): bool { return shell.agent !== null && shell.agent.isRegistered; }
        function status(): string { return shell.agent && shell.agent.isRegistered ? "running" : "unavailable"; }
        function stop(): void { Qt.quit(); }
    }

    Component.onCompleted: {
        if (validating) {
            // Instantiate the real dialog and imports before a service takeover, without registering.
            Qt.callLater(() => {
                console.info("Luna polkit validation passed");
                Qt.quit();
            });
        }
    }
}
