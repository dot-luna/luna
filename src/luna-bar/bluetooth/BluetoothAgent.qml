pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Io

// One instance in ShellRoot owns the BlueZ agent and its short-lived pairing prompt.
QtObject {
    id: agent

    property bool enabled: true
    property var screen: Quickshell.screens[0]
    property bool available: false
    property string error: ""
    property var request: null
    signal prompted()

    function respond(action, value) {
        if (request && helper.running)
            helper.write(JSON.stringify({id: request.id, action: action, value: value || ""}) + "\n");
    }

    function receive(data) {
        try {
            const message = JSON.parse(data);
            if (message.event === "request") {
                const fresh = !request || request.id !== message.id;
                request = message;
                if (fresh) {
                    error = "";
                    prompted();
                }
            } else if (message.event === "closed" && request && request.id === message.id) {
                request = null;
                error = "";
            } else if (message.event === "validation" && request && request.id === message.id) {
                error = message.error;
            } else if (message.event === "status") {
                available = message.available;
                if (message.error)
                    console.warn(message.error);
            }
        } catch (failure) {
            console.warn("Could not read Bluetooth pairing response.");
        }
    }

    onEnabledChanged: {
        if (!enabled) {
            retry.stop();
            if (request)
                respond("cancel", "");
            request = null;
            helper.running = false;
        } else {
            helper.running = true;
        }
    }
    Component.onCompleted: if (enabled) helper.running = true

    property Process helper: Process {
        // DBus and PyGObject come from Arch packages, outside mise's development Python.
        command: ["/usr/bin/python3", "-u", Quickshell.shellPath("bluetooth/agent.py")]
        stdinEnabled: true
        stdout: SplitParser { onRead: data => agent.receive(data) }
        stderr: SplitParser { onRead: data => console.warn("Bluetooth pairing:", data) }
        onExited: {
            agent.available = false;
            agent.request = null;
            if (agent.enabled)
                retry.restart();
        }
    }
    property Timer retry: Timer {
        interval: 5000
        onTriggered: if (agent.enabled) helper.running = true
    }
    property PairingDialog dialog: PairingDialog {
        screen: agent.screen
        request: agent.request
        error: agent.error
        onAccepted: value => agent.respond("accept", value)
        onCancelled: agent.respond("cancel", "")
    }
}
