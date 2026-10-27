pragma Singleton
pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Io

// Share the Lua screensaver API with QML apps without loading a renderer on import.
// Calls are queued in order; completed/failed report each asynchronous result.
QtObject {
    id: screensaver

    readonly property bool busy: activeRequest !== null || pending.length > 0
    property string error: ""
    property var config: null
    property string state: "unknown"
    property string configPath: ""
    property var stateData: null
    property var library: null
    property string libraryPath: ""
    readonly property bool active: stateData !== null && stateData.active
    readonly property bool stayAwake: stateData !== null && stateData.stayAwake

    signal completed(string method, var result)
    signal failed(string method, string message)

    // Resolve the neighboring Lua transport through installed source links or checkout paths.
    readonly property string bridgePath: decodeURIComponent(Qt.resolvedUrl("../bridge.lua").toString().replace(/^file:\/\//, ""))
    property var pending: []
    property var activeRequest: null

    // These requests read/edit the user file in any renderer state. The cached
    // config below is a response snapshot; applying file edits needs reload().
    function getConfig(key) { enqueue("getConfig", key === null ? undefined : key); }
    function updateConfig(changes) { enqueue("updateConfig", changes); }
    function getConfigFile() { enqueue("getConfigFile"); }
    function reload() { enqueue("reload"); }
    function status() { enqueue("status"); }
    function start() { enqueue("start"); }
    function stop() { enqueue("stop"); }
    function restart() { enqueue("restart"); }
    function getState() { enqueue("getState"); }
    function show() { enqueue("show"); }
    function hide() { enqueue("hide"); }
    function setStayAwake(enabled) { enqueue("setStayAwake", enabled); }
    function toggleStayAwake() { enqueue("toggleStayAwake"); }
    function list() { enqueue("list"); }
    function getDirectory() { enqueue("getDirectory"); }
    function install(source, options) { enqueue("install", {source: source, options: options}); }
    function set(target) { enqueue("set", target); }
    function removalPlan(names) { enqueue("removalPlan", names); }
    function remove(names) { enqueue("remove", names); }

    // Serialize at submission so later edits to a caller's object cannot change a request.
    function enqueue(method, argument) {
        let encoded;
        try {
            encoded = JSON.stringify({method: method, argument: argument});
        } catch (failure) {
            error = "Could not encode screensaver request: " + String(failure);
            failed(method, error);
            return;
        }
        pending = pending.concat([{method: method, encoded: encoded, key: method === "getConfig" ? argument : undefined}]);
        runNext();
    }

    // Each request owns its collectors, avoiding stale output when callbacks queue work.
    function runNext() {
        if (activeRequest !== null || pending.length === 0) return;
        const next = pending[0];
        activeRequest = requestProcess.createObject(screensaver, {
            method: next.method,
            encoded: next.encoded,
            key: next.key
        });
        pending = pending.slice(1);
        error = "";
        activeRequest.running = true;
    }

    // Check transport result shapes only; option defaults and validation belong to Lua.
    function validEntry(entry) {
        return entry !== null && typeof entry === "object" && !Array.isArray(entry)
            && typeof entry.name === "string" && typeof entry.path === "string"
            && typeof entry.bundled === "boolean";
    }

    function validResult(method, key, result) {
        if (method === "getConfig" && key !== undefined && key !== "") return true;
        if (method === "getConfig" || method === "updateConfig")
            return result !== null && typeof result === "object" && !Array.isArray(result);
        if (method === "getConfigFile" || method === "getDirectory") return typeof result === "string";
        if (method === "install") return validEntry(result);
        if (method === "set")
            return validEntry(result) && typeof result.selection === "string" && result.current === true;
        if (method === "list" || method === "removalPlan")
            return Array.isArray(result) && result.every(entry => validEntry(entry)
                && (method !== "list" || typeof entry.current === "boolean"));
        if (method === "remove")
            return Array.isArray(result) && result.every(name => typeof name === "string");
        if (method === "status") return ["stopped", "idle", "loading", "showing", "error"].indexOf(result) !== -1;
        if (method === "getState" || method === "setStayAwake" || method === "toggleStayAwake")
            return result !== null && typeof result === "object" && !Array.isArray(result)
                && typeof result.running === "boolean" && typeof result.active === "boolean"
                && typeof result.stayAwake === "boolean" && typeof result.outputsOff === "boolean"
                && ["hidden", "loading", "ready", "error"].indexOf(result.rendererState) !== -1
                && typeof result.error === "string";
        return result === null;
    }

    // Keyed reads return through completed without replacing the cached whole config.
    function finish(request, reply, message) {
        if (request.settled) return;
        request.settled = true;

        if (message) {
            error = message;
            failed(request.method, message);
        } else {
            error = "";
            configPath = reply.configPath;
            if (request.method === "updateConfig"
                || request.method === "getConfig" && (request.key === undefined || request.key === "")) {
                config = reply.result;
            }
            if (request.method === "list") {
                library = reply.result;
            } else if (["install", "remove", "set", "updateConfig"].indexOf(request.method) !== -1) {
                // Entries include the selected marker, so selection edits invalidate
                // the snapshot even when the installed package files did not change.
                library = null;
            }
            if (request.method === "getDirectory") libraryPath = reply.result;
            if (request.method === "set") config = null;
            if (request.method === "getState" || request.method === "setStayAwake" || request.method === "toggleStayAwake") {
                stateData = reply.result;
                state = !stateData.running ? "stopped" : stateData.error || stateData.rendererState === "error" ? "error"
                    : stateData.rendererState === "loading" ? "loading" : stateData.active ? "showing" : "idle";
            } else if (request.method === "status") {
                state = reply.result;
            } else if (request.method === "stop") {
                state = "stopped";
                stateData = {running: false, active: false, stayAwake: false,
                    outputsOff: false, rendererState: "hidden", error: ""};
            } else if (["start", "restart", "reload", "show", "hide", "set"].indexOf(request.method) !== -1) {
                // Lifecycle calls acknowledge work, not a state snapshot. Read the
                // controller separately so rendering readiness is never guessed.
                state = "unknown";
                stateData = null;
            }
            completed(request.method, reply.result);
        }

        // Keep this request reserved through signal handlers, then start queued work
        // outside the QProcess callback that completed or failed the previous command.
        activeRequest = null;
        request.destroy();
        Qt.callLater(runNext);
    }

    property Component requestProcess: Component {
        Process {
            id: request
            property string method
            property string encoded
            property var key
            property bool settled: false
            // Give each request a process group. A deadline must stop Lua's child
            // writers too, before queued changes can begin. The controller uses setsid.
            command: ["/usr/bin/timeout", "--signal=KILL", "90s", "/usr/bin/lua", "-E", screensaver.bridgePath, encoded]
            stdout: StdioCollector { id: response }
            stderr: StdioCollector { id: failure }

            onExited: (code, exitStatus) => {
                let reply;
                try {
                    reply = JSON.parse(response.text);
                } catch (ignored) {}

                if (code === 0 && exitStatus === 0 && reply && reply.ok === true
                    && Object.prototype.hasOwnProperty.call(reply, "result")
                    && typeof reply.configPath === "string"
                    && screensaver.validResult(method, key, reply.result)) {
                    screensaver.finish(request, reply, "");
                } else {
                    const message = code === 137 || (exitStatus !== 0 && code === 9)
                        ? "Screensaver request timed out or was terminated: " + method
                        : reply && typeof reply.error === "string" && reply.error
                        ? reply.error : failure.text.trim() || "Screensaver request failed: " + method;
                    screensaver.finish(request, null, message);
                }
            }

            onRunningChanged: {
                // Failed process startup has no exited signal. Defer this check so a
                // normal exit can consume its output before startup failure is assumed.
                if (!running && !settled) {
                    Qt.callLater(() => {
                        if (request && !request.settled && !request.running)
                            screensaver.finish(request, null, "Could not start screensaver request: " + method);
                    });
                }
            }

            // Unloading this object cancels its owned group; never signal PID 0.
            Component.onDestruction: {
                if (!settled && running && Number(processId) > 0)
                    Quickshell.execDetached(["/usr/bin/kill", "-KILL", "--", "-" + processId]);
            }
        }
    }
}
