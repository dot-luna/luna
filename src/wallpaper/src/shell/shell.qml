pragma ComponentBehavior: Bound

// Quickshell entry point for Luna's wallpaper app.
// Load TOML at startup or on explicit IPC reload, then configure one wallpaper surface.
import QtQuick
import Quickshell
import Quickshell.Io

ShellRoot {
    id: shell

    // An explicit path wins; empty environment variables use the standard config location.
    readonly property string configHome: Quickshell.env("XDG_CONFIG_HOME") || Quickshell.env("HOME") + "/.config"
    readonly property string configPath: Quickshell.env("LUNA_WALLPAPER_CONFIG") || configHome + "/luna/wallpaper.toml"

    // A null document produces the dark fallback. Track parsing separately from media loading.
    property var config: null
    property string configStatus: "loading"

    // Read only at startup or on request; neither TOML nor QML edits are watched.
    Component.onCompleted: {
        Quickshell.watchFiles = false;
        reloadConfig();
    }

    // Replacing the reader cancels overlapping requests and their timeout together.
    function reloadConfig() {
        reader.active = false;
        configStatus = "loading";
        reader.active = true;
    }

    // A failed read clears media and reports through Quickshell's file logger.
    function failConfig(message) {
        config = null;
        configStatus = "error";
        console.warn("Wallpaper config " + configPath + ": " + message);
    }

    // Lua resolves defaults and validates the file. QML only consumes its JSON
    // result; a failed read or validation clears the surface to black.
    Loader {
        id: reader
        active: false
        sourceComponent: Component {
            Process {
                id: parser
                running: true
                // The deadline owns a process group so it also stops Lua's TOMLKit
                // children. Each replacement read gets its own group and deadline.
                command: ["/usr/bin/timeout", "--signal=KILL", "10s", "/usr/bin/lua", "-E", Quickshell.shellDir + "/../read.lua"]
                stdout: StdioCollector { id: response }
                stderr: StdioCollector { id: failure }
                onExited: (code, status) => {
                    if (reader.item !== parser || shell.configStatus !== "loading") return;
                    if (code !== 0 || status !== 0) {
                        const timedOut = code === 137 || (status !== 0 && code === 9);
                        shell.failConfig(timedOut ? "Config reader timed out or was terminated"
                            : failure.text.trim() || "Config reader failed");
                        return;
                    }
                    try {
                        shell.config = JSON.parse(response.text);
                        shell.configStatus = "ready";
                    } catch (error) {
                        shell.failConfig(String(error));
                    }
                }
                onRunningChanged: {
                    // Failed process startup may not emit onExited. Let normal exits finish first.
                    if (!running) Qt.callLater(() => {
                        if (reader.item === parser && shell.configStatus === "loading") {
                            shell.failConfig("Could not run the config reader");
                        }
                    });
                }

                // Reloading or stopping the shell must also cancel parser children.
                // Only signal this reader's group, never PID 0 or the shell's group.
                Component.onDestruction: {
                    if (running && Number(processId) > 0)
                        Quickshell.execDetached(["/usr/bin/kill", "-KILL", "--", "-" + processId]);
                }
            }
        }
    }

    // Renderer IPC applies the user file and reports state; edits belong to the Lua API.
    IpcHandler {
        target: "wallpaper"

        // Reread settings without restarting Quickshell or writing the user's config.
        function reload(): void {
            shell.reloadConfig();
        }

        // Success requires both the latest config read and current media selection to settle.
        function status(): string {
            if (shell.configStatus === "loading") return "loading";
            if (shell.configStatus === "error") return "error";
            return surface.screen ? surface.mediaStatus : "error";
        }
    }

    // Keep reload diagnostics in Quickshell's logs instead of displaying desktop popups.
    Connections {
        target: Quickshell
        function onReloadCompleted() { Quickshell.inhibitReloadPopup(); }
        function onReloadFailed(errorString) { Quickshell.inhibitReloadPopup(); }
    }

    // Only the first available screen is rendered; outputs tables are reserved for later.
    WallpaperSurface {
        id: surface
        screen: Quickshell.screens[0] || null
        settings: shell.config
    }
}
