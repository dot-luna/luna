// Quickshell entry point for Luna's wallpaper app.
// Load one TOML file, resolve supported options with defaults, and configure one wallpaper surface.
// Existing wallpaper IPC calls can change the source without writing to the config file.
import QtQuick
import Quickshell
import Quickshell.Io
import "WallpaperConfig.js" as Config

ShellRoot {
    id: shell

    // An explicit path wins; empty environment variables use the standard config location.
    readonly property string configHome: Quickshell.env("XDG_CONFIG_HOME") || Quickshell.env("HOME") + "/.config"
    readonly property string configPath: Quickshell.env("LUNA_WALLPAPER_CONFIG") || configHome + "/luna/wallpaper.toml"

    // A null document produces the dark fallback. Track parsing separately from media loading.
    property var config: null
    property string configStatus: "loading"

    // Remember an IPC selection made while the startup parser is still running.
    // Null means no selection; an empty string is a valid request to clear the wallpaper.
    property var pendingSource: null

    // Start one read at launch. Config edits take effect after a manual restart.
    Component.onCompleted: {
        Quickshell.watchFiles = false;
        parser.running = true;
        parserTimeout.start();
    }

    // Log through Quickshell's file logger, keeping any already accepted IPC selection.
    function failConfig(message) {
        if (pendingSource === null) config = null;
        configStatus = "error";
        console.warn("Wallpaper config " + configPath + ": " + message);
    }

    // TOMLKit runs in a short-lived system Python process because QML cannot import it.
    // The path is an argument, not shell text; stdout carries JSON and stderr carries errors.
    Process {
        id: parser
        command: ["/usr/bin/python3", "-I", "-c", [
            "import json, pathlib, sys",
            "try:",
            "    import tomlkit",
            "    path = pathlib.Path(sys.argv[1])",
            "    if not path.is_absolute(): raise ValueError('config path must be absolute')",
            "    if not path.is_file(): raise ValueError('config file is missing or not a regular file')",
            "    document = tomlkit.parse(path.read_text(encoding='utf-8'))",
            // TOML-only scalar values become null so unsupported options can use their defaults.
            "    encoded = json.dumps(document.unwrap(), default=lambda _: None)",
            "    print(json.dumps(json.loads(encoded, parse_constant=lambda _: None)))",
            "except Exception as error:",
            "    print(str(error).replace('\\n', ' '), file=sys.stderr)",
            "    sys.exit(1)"
        ].join("\n"), shell.configPath]
        stdout: StdioCollector { id: response }
        stderr: StdioCollector { id: failure }
        onExited: (code, status) => {
            parserTimeout.stop();

            // A timeout may have already rejected this read; do not revive its result.
            if (shell.configStatus !== "loading") return;
            if (code !== 0 || status !== 0) {
                shell.failConfig(failure.text.trim() || "TOML parser failed");
                return;
            }
            try {
                const parsed = JSON.parse(response.text);

                // Apply the newer source without losing the file's other settings.
                if (shell.pendingSource !== null)
                    parsed.wallpaper = Object.assign({}, parsed.wallpaper, { source: shell.pendingSource });
                shell.config = parsed;
                shell.configStatus = "ready";
            } catch (error) {
                shell.failConfig(String(error));
            }
        }
        onRunningChanged: {
            // Failed process startup may not emit onExited. Let normal exits finish first.
            if (!running) Qt.callLater(() => {
                if (shell.configStatus === "loading") {
                    parserTimeout.stop();
                    shell.failConfig("Could not run the TOML parser");
                }
            });
        }
    }

    // Bound config loading so a stuck parser cannot leave startup pending forever.
    Timer {
        id: parserTimeout
        interval: 10000
        onTriggered: {
            shell.failConfig("TOML parser timed out");
            parser.running = false;
        }
    }

    // Keep the existing wallpaper IPC interface; configuration persistence belongs elsewhere.
    IpcHandler {
        target: "wallpaper"

        // Replace the source in a copied document so QML notices the change.
        function set(path: string): void {
            const next = Object.assign({}, shell.config);
            next.wallpaper = Object.assign({}, next.wallpaper, { source: path });
            shell.config = next;
            shell.pendingSource = path;

            // The caller must not see the previous image's ready state after this request.
            surface.mediaStatus = "loading";
        }

        // Success requires both config startup and the current media selection to settle.
        function status(): string {
            if (shell.configStatus === "loading") return "loading";
            if (shell.pendingSource === null && shell.configStatus === "error") return "error";
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
        settings: Config.resolve(shell.config)
    }
}
