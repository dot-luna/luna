pragma Singleton
import QtQuick
import Quickshell.Io

// Each UI reads the same session state from the screensaver's CLI bridge.
QtObject {
    id: awake

    property bool enabled: false
    property bool ready: false
    property bool busy: false
    readonly property string error: actionError || statusError
    property string actionError: ""
    property string statusError: ""
    readonly property string lunaCli: decodeURIComponent(Qt.resolvedUrl("../../../bin/luna").toString().replace(/^file:\/\//, ""))

    function refresh() {
        run("status");
    }
    function toggle() {
        if (ready) run("toggle");
    }
    function run(action) {
        if (busy) return;
        // Reserve requests synchronously; Process only notifies running after startup.
        busy = true;
        if (action !== "status") actionError = "";
        request.action = action;
        request.running = true;
    }

    // Serialize refreshes and changes so a stale status response cannot overwrite a toggle.
    property Process process: Process {
        id: request
        property string action: "status"
        command: [awake.lunaCli, "awake", action]
        stdout: StdioCollector { id: response }
        stderr: StdioCollector { id: failure }
        onRunningChanged: {
            // Failed startup emits runningChanged without exited; allow the next retry.
            if (!running && awake.busy) {
                if (action === "status") {
                    awake.ready = false;
                    awake.statusError = "Could not read Stay awake status.";
                } else {
                    awake.actionError = "Could not start the Stay awake command.";
                }
                awake.busy = false;
            }
        }
        onExited: (code, status) => {
            let state;
            try {
                if (code === 0) state = JSON.parse(response.text);
            } catch (error) {}

            if (state && typeof state.enabled === "boolean") {
                awake.enabled = state.enabled;
                awake.ready = true;
                awake.statusError = "";
                if (action !== "status") awake.actionError = "";
            } else if (action === "status") {
                awake.ready = false;
                awake.statusError = "Could not read Stay awake status.";
            } else {
                awake.actionError = failure.text.trim() || "Could not change Stay awake.";
            }
            awake.busy = false;
        }
    }
}
