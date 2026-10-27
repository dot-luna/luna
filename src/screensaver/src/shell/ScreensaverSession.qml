pragma Singleton
pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io

// The controller gives each renderer a private activation token. This transport
// can report readiness or wake that activation; it never starts or stops idle logic.
QtObject {
    id: session

    readonly property string controller: Quickshell.env("LUNA_SCREENSAVER_CONTROLLER")
    readonly property string token: Quickshell.env("LUNA_SCREENSAVER_TOKEN")
    readonly property bool managed: controller !== "" && token !== ""
    readonly property var config: readConfig()
    readonly property var settings: config.settings || ({})
    readonly property string requestedScreen: Quickshell.env("LUNA_SCREENSAVER_FOCUSED_SCREEN")
    readonly property string focusedScreen: {
        const screens = Quickshell.screens;
        for (let index = 0; index < screens.length; index++) {
            if (screens[index].name === requestedScreen) return requestedScreen;
        }
        return screens[0]?.name || "";
    }

    property string error: ""
    property bool readyRequested: false
    property bool dismissRequested: false
    property var pending: []
    property var activeRequest: null

    function readConfig() {
        const encoded = Quickshell.env("LUNA_SCREENSAVER_SETTINGS");
        if (!encoded) return {};
        try {
            const result = JSON.parse(encoded);
            if (result !== null && typeof result === "object" && !Array.isArray(result)) return result;
        } catch (ignored) {}
        console.warn("Could not read screensaver renderer settings.");
        return {};
    }

    // Surface helpers call ready after a real output window becomes visible.
    // A custom renderer with its own windows must make that same check itself.
    function ready() {
        if (!managed || readyRequested || dismissRequested) return;
        readyRequested = true;
        enqueue("ready");
    }

    function dismiss() {
        if (!managed || dismissRequested) return;
        dismissRequested = true;
        enqueue("dismiss");
    }

    function enqueue(method) {
        pending = pending.concat([method]);
        runNext();
    }

    // Serialize ready and dismiss so a wake during initial rendering cannot be
    // overtaken by a late ready message. The controller also rejects old tokens.
    function runNext() {
        if (activeRequest !== null || pending.length === 0) return;
        const method = pending[0];
        activeRequest = requestProcess.createObject(session, {method: method});
        pending = pending.slice(1);
        activeRequest.running = true;
    }

    function finish(request, message) {
        if (request.settled) return;
        request.settled = true;
        error = message;
        if (message) {
            console.warn(message);
            // A failed dismissal may be retried by the user's next input event.
            if (request.method === "dismiss") dismissRequested = false;
        }
        activeRequest = null;
        request.destroy();
        Qt.callLater(runNext);
    }

    Component.onCompleted: if (managed) Quickshell.watchFiles = false

    // One monitor query serves every output. A managed renderer exists only while
    // shown, so the controller's idle lifetime does not keep this polling alive.
    property Timer monitorRefresh: Timer {
        interval: 2000
        repeat: true
        running: !!Quickshell.env("HYPRLAND_INSTANCE_SIGNATURE")
        triggeredOnStart: true
        onTriggered: Hyprland.refreshMonitors()
    }

    property Component requestProcess: Component {
        Process {
            id: request
            property string method
            property bool settled: false
            command: ["/usr/bin/timeout", "--signal=KILL", "3s", "qs", "ipc", "-p", session.controller,
                "call", "renderer", method, session.token]
            stdout: StdioCollector {}
            stderr: StdioCollector { id: failure }
            onExited: (code, status) => session.finish(request, code === 0 && status === 0 ? ""
                : failure.text.trim() || "Could not contact the screensaver controller: " + method)
            onRunningChanged: if (!running && !settled) Qt.callLater(() => {
                if (request && !request.settled && !request.running)
                    session.finish(request, "Could not start screensaver session request: " + method);
            })
            Component.onDestruction: {
                if (!settled && running && Number(processId) > 0)
                    Quickshell.execDetached(["/usr/bin/kill", "-KILL", "--", "-" + processId]);
            }
        }
    }
}
