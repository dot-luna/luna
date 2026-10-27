pragma ComponentBehavior: Bound

// The session controller owns idle policy. User QML runs in a separate process,
// so rendering errors and visual reloads cannot remove the automatic lock timer.
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Hyprland

ShellRoot {
    id: controller

    property var config: JSON.parse(Quickshell.env("LUNA_SCREENSAVER_SETTINGS"))
    property var theme: JSON.parse(Quickshell.env("LUNA_UI_THEME"))
    readonly property string controllerPath: Quickshell.shellDir + "/controller.qml"
    readonly property string lunaCli: Quickshell.shellDir + "/../../../../bin/luna"
    property bool stayAwake: false
    property bool showing: false
    property bool shuttingDown: false
    property string pendingAction: ""
    property string error: ""
    property string rendererState: "hidden"
    property string rendererToken: ""
    property int generation: 0
    property bool rendererSettled: true
    property bool rendererStopping: false
    property bool rendererRestart: false
    property string rendererDiagnostic: ""
    property bool lockPending: false
    property double lockDeadline: 0
    property bool powerWanted: false
    property bool powerBusy: false
    property bool powerQueryBusy: false
    property bool powerRequestOff: false
    property var powerRequestScreens: []
    property var poweredOffScreens: []
    readonly property bool outputsOff: poweredOffScreens.length > 0

    Component.onCompleted: Quickshell.watchFiles = false

    function state() {
        return {running: true, active: showing, stayAwake: stayAwake,
            outputsOff: outputsOff, rendererState: rendererState, error: error};
    }

    function status() {
        if (error) return "error";
        if (showing) return rendererState === "ready" ? "showing" : "loading";
        return pendingAction === "show" || pendingAction === "auto" ? "loading" : "idle";
    }

    function setAwake(enabled) {
        // Cancel queued work before disabling sensors, including a delayed lock check.
        if (enabled) hide();
        stayAwake = enabled;
        return JSON.stringify(state());
    }

    function stopRenderer() {
        rendererToken = "";
        renderDeadline.stop();
        if (rendererSettled) return;
        rendererStopping = true;
        renderer.running = false;
        renderKill.restart();
    }

    function hide(wake = true) {
        pendingAction = "";
        showing = false;
        rendererRestart = false;
        rendererState = "hidden";
        error = "";
        stopRenderer();
        if (wake) setPower(false);
    }

    function failRenderer(message) {
        showing = false;
        rendererRestart = false;
        rendererState = "error";
        error = message;
        stopRenderer();
        console.warn(message);
    }

    function rendererPath() {
        let path = config.renderer.shell;
        if (!path) path = Quickshell.shellDir + "/shell.qml";
        else if (path.startsWith("~/")) path = Quickshell.env("HOME") + path.slice(1);
        return path;
    }

    function startRenderer() {
        if (!showing || shuttingDown || !rendererSettled) return;
        const path = rendererPath();
        if (path === controllerPath) {
            failRenderer("Choose a rendering shell, not the idle controller.");
            return;
        }

        generation++;
        rendererToken = String(Date.now()) + "-" + generation;
        rendererState = "loading";
        rendererDiagnostic = "";
        rendererSettled = false;
        rendererStopping = false;
        rendererRestart = false;
        // No --daemonize or --no-duplicate: this controller owns this child only,
        // even when the same custom QML file is already open elsewhere.
        renderer.command = ["qs", "-p", path];
        renderer.environment = {
            LUNA_SCREENSAVER_CONTROLLER: controllerPath,
            LUNA_SCREENSAVER_TOKEN: rendererToken,
            LUNA_SCREENSAVER_SETTINGS: JSON.stringify(config),
            LUNA_SCREENSAVER_FOCUSED_SCREEN: Hyprland.focusedMonitor?.name || Quickshell.screens[0]?.name || "",
            LUNA_UI_THEME: JSON.stringify(theme),
            QS_NO_RELOAD_POPUP: "1"
        };
        renderDeadline.restart();
        renderer.running = true;
    }

    function rendererFinished(message) {
        if (rendererSettled) return;
        rendererSettled = true;
        renderKill.stop();
        renderDeadline.stop();
        const expected = rendererStopping;
        rendererStopping = false;
        if (!expected) failRenderer(message);
        if (rendererRestart && showing && !shuttingDown)
            Qt.callLater(startRenderer);
        finishShutdown();
    }

    function reloadRenderer() {
        if (!showing) return;
        rendererRestart = true;
        rendererState = "loading";
        stopRenderer();
        if (rendererSettled) startRenderer();
    }

    function configure(payload) {
        const next = JSON.parse(payload);
        // Lua validates before sending. Keep current policy alive on malformed IPC.
        if (!next.config?.idle || !next.config?.renderer || !next.theme)
            throw new Error("Invalid screensaver configuration");
        pendingAction = "";
        config = next.config;
        theme = next.theme;
        error = "";
        if (!showing) rendererState = "hidden";
        if (config.idle.display_off_seconds === 0) setPower(false);
        reloadRenderer();
    }

    function request(action) {
        if (shuttingDown || lockPending || stayAwake && action !== "show") return;
        if (action === "auto" && (outputsOff || powerWanted)) return;
        // A lock takes priority over a queued show; a manual show can replace an auto show.
        if (pendingAction === "lock" && action !== "lock") return;
        pendingAction = action;
        error = "";
        if (!lockCheck.running) lockCheck.running = true;
    }

    function lockFailed(message) {
        lockPending = false;
        lockPoll.stop();
        error = message;
        console.warn(message);
        Quickshell.execDetached(["notify-send", "--app-name=Luna", "--urgency=critical",
            "Luna auto-lock failed", "Run luna lock to check the error."]);
    }

    function checkFinished(code, text) {
        if (shuttingDown) return;
        let locked;
        try {
            if (code !== 0) throw new Error("Cannot check the session lock.");
            locked = JSON.parse(text).locked;
            if (typeof locked !== "boolean") throw new Error("Invalid session lock status.");
        } catch (failure) {
            pendingAction = "";
            if (lockPending) lockFailed(String(failure));
            else { error = String(failure); console.warn(error); }
            return;
        }

        if (lockPending) {
            if (locked) {
                lockPending = false;
                lockPoll.stop();
            } else if (Date.now() >= lockDeadline) {
                lockFailed("The compositor did not confirm automatic locking.");
            }
            return;
        }
        const action = pendingAction;
        pendingAction = "";
        if (!action) return;
        if (locked) { hide(false); return; }
        if (stayAwake && action !== "show") return;
        if (action === "lock") {
            hide(false);
            // The locker must outlive this controller. Stopping/reloading a saver
            // must never kill an active authentication session.
            lockPending = true;
            lockDeadline = Date.now() + 8000;
            Quickshell.execDetached([lunaCli, "lock"]);
            lockPoll.start();
        } else {
            setPower(false);
            showing = true;
            if (rendererStopping) rendererRestart = true;
            else startRenderer();
        }
    }

    // Encode only a monitor selector as Lua source. Command arguments are always
    // passed directly to Process, never through a shell.
    function luaString(value) {
        return '"' + value.replace(/[\\"\x00-\x1f\x7f]/g, character => {
            if (character === "\\" || character === '"') return "\\" + character;
            return "\\" + String(character.charCodeAt(0)).padStart(3, "0");
        }) + '"';
    }

    function setPower(off) {
        powerWanted = off && !stayAwake && !shuttingDown;
        applyPower();
    }

    function applyPower() {
        if (powerBusy || powerQueryBusy || powerWanted === outputsOff) return;
        if (powerWanted) {
            // Cached monitor data may predate an external power change. Query
            // before taking ownership so waking never enables an unrelated output.
            powerQueryBusy = true;
            monitorQuery.running = true;
        } else {
            dispatchPower(false, poweredOffScreens);
        }
    }

    function queriedMonitors(success, text) {
        if (!powerQueryBusy) return;
        powerQueryBusy = false;
        if (powerWanted && !shuttingDown && !stayAwake) {
            try {
                if (!success) throw new Error("Could not read display power state.");
                const monitors = JSON.parse(text);
                if (!Array.isArray(monitors)) throw new Error("Invalid display power state.");
                const screens = monitors.filter(monitor => typeof monitor.name === "string"
                    && monitor.dpmsStatus === true && monitor.disabled !== true).map(monitor => monitor.name);
                dispatchPower(true, screens);
            } catch (failure) {
                powerWanted = false;
                error = String(failure);
                console.warn(error);
            }
        }
        finishShutdown();
    }

    function dispatchPower(off, screens) {
        if (!screens.length) return;
        powerRequestOff = off;
        powerRequestScreens = screens;
        const action = off ? "off" : "on";
        const code = screens.map(name => 'hl.dispatch(hl.dsp.dpms({action="' + action
            + '",monitor=' + luaString(name) + '}))').join("\n");
        power.command = ["/usr/bin/timeout", "--kill-after=1s", "3s", "hyprctl", "eval", code];
        powerBusy = true;
        power.running = true;
    }

    function powerFinished(success) {
        if (!powerBusy) return;
        powerBusy = false;
        if (success) poweredOffScreens = powerRequestOff ? powerRequestScreens : [];
        else {
            // An off request may have partly succeeded. Retain ownership so a
            // resume can restore those outputs without waking unrelated monitors.
            if (powerRequestOff) poweredOffScreens = powerRequestScreens;
            powerWanted = false;
            error = "Could not change display power.";
            console.warn(error);
        }
        if (success || powerRequestOff) applyPower();
        finishShutdown();
    }

    function shutdown() {
        shuttingDown = true;
        hide();
        lockPoll.stop();
        finishShutdown();
    }

    function finishShutdown() {
        if (shuttingDown && rendererSettled && !powerBusy && !powerQueryBusy) Qt.quit();
    }

    IpcHandler {
        target: "screensaver"
        function ping(): string { return "ready"; }
        function status(): string { return controller.status(); }
        function getState(): string { return JSON.stringify(controller.state()); }
        function getRendererShell(): string { return controller.rendererPath(); }
        function show(): void { controller.request("show"); }
        function hide(): void { controller.hide(); }
        function configure(payload: string): void { controller.configure(payload); }
        function setStayAwake(enabled: bool): string { return controller.setAwake(enabled); }
        function toggleStayAwake(): string { return controller.setAwake(!controller.stayAwake); }
        function shutdown(): void { controller.shutdown(); }
        function applyFonts(value: string): void {
            controller.theme = Object.assign({}, controller.theme, {fonts: JSON.parse(value)});
            controller.reloadRenderer();
        }
    }

    IpcHandler {
        target: "renderer"
        function ready(token: string): void {
            if (!token || token !== controller.rendererToken || !controller.showing) return;
            renderDeadline.stop();
            controller.rendererState = "ready";
        }
        function dismiss(token: string): void {
            if (token && token === controller.rendererToken) controller.hide();
        }
    }

    IdleMonitor {
        id: saverIdle
        enabled: !controller.shuttingDown && !controller.stayAwake && controller.config.idle.screensaver_seconds > 0
        timeout: controller.config.idle.screensaver_seconds
        respectInhibitors: true
        onIsIdleChanged: {
            if (isIdle) controller.request("auto");
            else controller.hide();
        }
    }
    IdleMonitor {
        id: lockIdle
        enabled: !controller.shuttingDown && !controller.stayAwake && controller.config.idle.lock_seconds > 0
        timeout: controller.config.idle.lock_seconds
        respectInhibitors: true
        onIsIdleChanged: {
            if (isIdle) controller.request("lock");
            else if (controller.pendingAction === "lock") controller.pendingAction = "";
        }
    }
    IdleMonitor {
        id: displayIdle
        enabled: !controller.shuttingDown && !controller.stayAwake && controller.config.idle.display_off_seconds > 0
        timeout: controller.config.idle.display_off_seconds
        respectInhibitors: true
        onIsIdleChanged: controller.setPower(isIdle)
    }

    Process {
        id: lockCheck
        command: ["/usr/bin/timeout", "--kill-after=1s", "3s", "hyprctl", "-j", "locked"]
        stdout: StdioCollector { id: lockResponse }
        stderr: StdioCollector {}
        onExited: (code, exitStatus) => controller.checkFinished(code, lockResponse.text)
        onRunningChanged: if (!running) Qt.callLater(() => {
            if (controller.pendingAction && !lockCheck.running) {
                controller.pendingAction = "";
                controller.error = "Could not check the session lock.";
            }
        })
    }
    Timer {
        id: lockPoll
        interval: 200
        repeat: true
        onTriggered: if (!lockCheck.running) lockCheck.running = true
    }
    Process {
        id: renderer
        stdout: SplitParser { onRead: data => controller.rendererDiagnostic = data.slice(-1000) }
        stderr: SplitParser { onRead: data => controller.rendererDiagnostic = data.slice(-1000) }
        onStarted: if (controller.rendererStopping) renderer.running = false
        onExited: (code, exitStatus) => controller.rendererFinished("Screensaver shell exited"
            + (controller.rendererDiagnostic ? ": " + controller.rendererDiagnostic : "."))
        onRunningChanged: if (!running) Qt.callLater(() => {
            if (!renderer.running && !controller.rendererSettled)
                controller.rendererFinished("Could not start the screensaver shell.");
        })
    }
    Timer {
        id: renderDeadline
        interval: 5000
        onTriggered: controller.failRenderer("Screensaver shell did not report ready. Use Luna.ScreensaverSurface or ScreensaverSession.")
    }
    Timer {
        id: renderKill
        interval: 1000
        onTriggered: if (renderer.running) renderer.signal(9)
    }
    Process {
        id: monitorQuery
        command: ["/usr/bin/timeout", "--kill-after=1s", "3s", "hyprctl", "-j", "monitors"]
        stdout: StdioCollector { id: monitorResponse }
        stderr: StdioCollector {}
        onExited: (code, exitStatus) => controller.queriedMonitors(code === 0 && exitStatus === 0, monitorResponse.text)
        onRunningChanged: if (!running) Qt.callLater(() => {
            if (!monitorQuery.running && controller.powerQueryBusy) controller.queriedMonitors(false, "");
        })
    }
    Process {
        id: power
        stdout: StdioCollector {}
        stderr: StdioCollector {}
        onExited: (code, exitStatus) => controller.powerFinished(code === 0 && exitStatus === 0)
        onRunningChanged: if (!running) Qt.callLater(() => {
            if (!power.running && controller.powerBusy) controller.powerFinished(false);
        })
    }
}
