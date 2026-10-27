import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland

// One background window per screen, with no reserved space or input interception.
ShellRoot {
    id: shell

    property string wallpaperPath: ""
    readonly property string configHome: Quickshell.env("XDG_CONFIG_HOME") || Quickshell.env("HOME") + "/.config"
    readonly property string imageUrl: wallpaperPath ? "file://" + wallpaperPath.split("/").map(encodeURIComponent).join("/") : ""

    // Restore the saved path at startup; CLI changes arrive through scoped IPC.
    FileView {
        id: selection
        path: shell.configHome + "/luna/wallpaper"
        printErrors: false
        blockLoading: true
    }

    // Read before serving IPC so a delayed file load cannot overwrite a new selection.
    Component.onCompleted: wallpaperPath = selection.text().replace(/\n$/, "")

    // An invisible image checks decoder readiness before the CLI persists a path.
    Image {
        id: probe
        source: shell.imageUrl
        asynchronous: true
        cache: false
    }

    IpcHandler {
        target: "wallpaper"

        function set(path: string): void {
            shell.wallpaperPath = "";
            shell.wallpaperPath = path;
        }

        function status(): string {
            if (probe.status === Image.Ready) return "ready";
            if (probe.status === Image.Error) return "error";
            return "loading";
        }
    }

    Variants {
        model: Quickshell.screens

        delegate: PanelWindow {
            required property var modelData
            screen: modelData
            visible: shell.wallpaperPath !== ""
            anchors { top: true; bottom: true; left: true; right: true }
            exclusionMode: ExclusionMode.Ignore
            color: "#000000"
            mask: Region {}
            WlrLayershell.layer: WlrLayer.Background
            WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
            WlrLayershell.namespace: "luna-wallpaper"

            Image {
                anchors.fill: parent
                source: shell.imageUrl
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                cache: false
            }
        }
    }
}
