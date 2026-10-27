pragma Singleton
import QtQuick

// Widget state for Stay awake. The shared Screensaver API owns transport and the
// session controller owns the value; this adapter tracks only its own requests.
QtObject {
    id: awake

    property bool enabled: false
    property bool ready: false
    property bool busy: false
    readonly property string error: actionError || statusError
    property string actionError: ""
    property string statusError: ""
    property string requestAction: "status"

    function refresh() {
        run("status");
    }
    function toggle() {
        if (ready) run("toggle");
    }
    function run(action) {
        // Wait for an empty shared queue so our response cannot be confused with
        // an earlier request for the same method from another widget.
        if (busy || Screensaver.busy) return;
        busy = true;
        requestAction = action;
        if (action !== "status") actionError = "";
        if (action === "status") Screensaver.getState();
        else Screensaver.toggleStayAwake();
    }

    function failed(message) {
        if (requestAction === "status") {
            ready = false;
            statusError = "Could not read Stay awake status.";
        } else {
            actionError = message || "Could not change Stay awake.";
        }
        busy = false;
    }

    property Connections responses: Connections {
        target: Screensaver
        function onCompleted(method, result) {
            const expected = awake.requestAction === "status" ? "getState" : "toggleStayAwake";
            if (!awake.busy || method !== expected) return;
            if (!result || typeof result.stayAwake !== "boolean") {
                awake.failed("Could not change Stay awake.");
                return;
            }
            awake.enabled = result.stayAwake;
            awake.ready = true;
            awake.statusError = "";
            if (awake.requestAction !== "status") awake.actionError = "";
            awake.busy = false;
        }
        function onFailed(method, message) {
            const expected = awake.requestAction === "status" ? "getState" : "toggleStayAwake";
            if (awake.busy && method === expected) awake.failed(message);
        }
    }
}
