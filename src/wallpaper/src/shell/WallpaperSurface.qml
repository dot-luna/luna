pragma ComponentBehavior: Bound

// Wallpaper window created by shell.qml for its selected screen.
// Inspect the source, decode images with Qt, or delegate videos to VideoWallpaper.
// Two image slots allow a fade while this window provides the solid-color fallback underneath.
import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io
import Quickshell.Wayland
import "WallpaperConfig.js" as Config

PanelWindow {
    id: surface

    // shell.qml supplies resolved global options, or null when config loading failed.
    property var settings: null
    property string kind: "image"

    // Centered and tiled rasters keep one source pixel per physical screen pixel.
    readonly property real nativeScale: settings?.wallpaper.fit === "center" || settings?.wallpaper.fit === "tile"
        ? 1 / (screen ? screen.devicePixelRatio : 1) : 1
    readonly property int fadeDuration: settings && settings.transition.type === "fade" ? settings.transition.duration_ms : 0
    property string mediaStatus: "error"

    // Hyprland's output state controls animation/video pausing when the option is enabled.
    // Without a compositor monitor object, treat the output as active.
    readonly property bool hasHyprland: !!Quickshell.env("HYPRLAND_INSTANCE_SIGNATURE")
    readonly property var monitor: hasHyprland ? Hyprland.monitorFor(screen) : null
    readonly property bool outputActive: !monitor || !monitor.lastIpcObject
        || (monitor.lastIpcObject.dpmsStatus !== false && monitor.lastIpcObject.disabled !== true)
    readonly property bool pauseMedia: !!settings && settings.playback.pause_when_output_inactive && !outputActive
    // Slot 0 is first, slot 1 is second, and -1 means no current/pending image.
    property int frontSlot: -1
    property int loadingSlot: -1

    // Cover the screen behind applications without taking keyboard or pointer input.
    // The configured color fills gaps; any config/media error forces solid black.
    visible: true
    anchors { top: true; bottom: true; left: true; right: true }
    exclusionMode: ExclusionMode.Ignore
    color: mediaStatus === "error" || !settings ? "#000000" : settings.wallpaper.background_color
    mask: Region {}
    WlrLayershell.layer: WlrLayer.Background
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
    WlrLayershell.namespace: "luna-wallpaper"

    // Release visible media and log the failure, leaving only the dark window background.
    function fail(message) {
        fade.stop();
        mediaTimeout.stop();
        mediaStatus = "error";
        frontSlot = -1;
        loadingSlot = -1;
        first.active = false;
        second.active = false;
        video.active = false;
        console.warn("Wallpaper " + (screen ? screen.name : "output") + ": " + message);
    }

    // Begin a new selection: cancel previous inspection, then clear or inspect the source.
    function apply() {
        probe.active = false;
        mediaTimeout.stop();
        fade.stop();
        // Finish an interrupted fade visually so the next transition starts from an opaque image.
        if (frontSlot !== -1) (frontSlot === 0 ? first : second).opacity = 1;

        // An empty source is a valid solid-color choice; null settings indicate a config error.
        if (!settings || !settings.wallpaper.source) {
            frontSlot = -1;
            loadingSlot = -1;
            first.active = false;
            second.active = false;
            video.active = false;
            mediaStatus = settings ? "ready" : "error";
            return;
        }
        // Inspection is asynchronous; keep the current image visible while metadata loads.
        mediaStatus = "loading";
        probe.active = true;
        mediaTimeout.start();
    }

    // Start the renderer chosen from metadata. Video switches immediately; images can fade.
    function render(mediaKind) {
        kind = mediaKind;
        if (kind === "video") {
            mediaTimeout.stop();
            first.active = false;
            second.active = false;
            frontSlot = -1;
            loadingSlot = -1;
            // Recreate the component so the previous video process is owned and cleaned up separately.
            video.active = false;
            video.active = true;
            return;
        }
        // Decode into the spare image slot while leaving the current image visible.
        video.active = false;
        loadingSlot = frontSlot === 0 ? 1 : 0;
        const next = loadingSlot === 0 ? first : second;
        next.active = false;
        next.opacity = 0;
        next.mediaPath = settings.wallpaper.source;
        next.mediaKind = kind;
        next.active = true;
        mediaTimeout.start();
    }

    // Only current/pending slots may change status; a stale decoder must not replace newer media.
    function decoded(slot, status) {
        if (slot !== loadingSlot && slot !== frontSlot) return;
        // An active animation can fail on a later frame, after its initial Ready notification.
        if (status === Image.Error) {
            fail("Cannot decode " + settings.wallpaper.source);
        } else if (status === Image.Ready && slot === loadingSlot) {
            mediaTimeout.stop();
            const incoming = slot === 0 ? first : second;
            const previous = frontSlot;
            frontSlot = slot;
            loadingSlot = -1;
            mediaStatus = "ready";
            // Fade only when an outgoing image exists; the first image can appear immediately.
            if (previous !== -1 && fadeDuration > 0) {
                fade.target = incoming;
                fade.start();
            } else {
                incoming.opacity = 1;
                (slot === 0 ? second : first).active = false;
            }
        }
    }

    // Invalidate the previous probe immediately, then coalesce binding updates before applying.
    onSettingsChanged: {
        if (probe) probe.active = false;
        // Release the old player before its source binding can bypass media inspection.
        // Only render() may start a player for the newly classified source.
        if (video) video.active = false;
        loadingSlot = -1;
        mediaStatus = settings ? "loading" : "error";
        Qt.callLater(apply);
    }
    Component.onCompleted: Qt.callLater(apply)

    // Bound each metadata/image load. VideoWallpaper owns its separate startup deadline.
    Timer {
        id: mediaTimeout
        interval: 20000
        onTriggered: {
            probe.active = false;
            surface.fail("Media loading timed out: " + surface.settings?.wallpaper.source);
        }
    }

    // Each selection gets a short-lived ffprobe process that reads metadata without transcoding.
    // Destroying this loader cancels an obsolete probe when settings change.
    Loader {
        id: probe
        active: false
        sourceComponent: Component {
            Process {
                id: inspection
                // A failed process start may change running without producing an exit callback.
                property bool finished: false
                command: ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                    "stream=codec_name:format=format_name", "-of", "json", "-i", surface.settings?.wallpaper.source || ""]
                running: true
                stdout: StdioCollector { id: metadata }
                stderr: StdioCollector {}
                onExited: code => {
                    finished = true;
                    try {
                        // Qt also reads images such as SVG that ffprobe cannot inspect.
                        surface.render(code === 0 ? Config.mediaKind(JSON.parse(metadata.text)) : "image");
                    } catch (error) {
                        surface.fail("Could not identify media: " + error);
                    }
                }
                // Wait for normal exit handling, and report only failures from the current probe.
                onRunningChanged: if (!running) Qt.callLater(() => {
                    if (!finished && probe.item === inspection)
                        surface.fail("Could not run ffprobe; install the ffmpeg package.");
                })
            }
        }
    }

    // Keep the outgoing image opaque underneath the incoming fade to avoid a dark midpoint.
    // Once the fade finishes, release the old image instead of retaining both decoded files.
    NumberAnimation {
        id: fade
        property: "opacity"
        from: 0
        to: 1
        duration: surface.fadeDuration
        onFinished: (surface.frontSlot === 0 ? second : first).active = false
    }

    // Refresh compositor power state only for moving media that should pause on an inactive output.
    Timer {
        interval: 2000
        repeat: true
        running: surface.hasHyprland && !!surface.settings && surface.kind !== "image"
            && surface.settings.playback.pause_when_output_inactive
        triggeredOnStart: true
        onTriggered: Hyprland.refreshMonitors()
    }

    // Clip oversized centered/cropped content to the screen. The front slot is stacked on top.
    // Both slots use identical geometry; their source snapshots stay fixed during a crossfade.
    Item {
        anchors.fill: parent
        clip: true

        // First half of the alternating pair; onLoaded also handles a synchronously ready image.
        Loader {
            id: first
            property int slot: 0
            property string mediaPath: ""
            property string mediaKind: "image"
            width: parent.width / surface.nativeScale
            height: parent.height / surface.nativeScale
            scale: surface.nativeScale
            transformOrigin: Item.TopLeft
            active: false
            opacity: 0
            z: surface.frontSlot === slot ? 1 : 0
            sourceComponent: mediaKind === "animated" ? animated : still
            onLoaded: surface.decoded(slot, item.status)
        }

        // Second half of the pair; the old slot stays opaque until the incoming fade completes.
        Loader {
            id: second
            property int slot: 1
            property string mediaPath: ""
            property string mediaKind: "image"
            width: parent.width / surface.nativeScale
            height: parent.height / surface.nativeScale
            scale: surface.nativeScale
            transformOrigin: Item.TopLeft
            active: false
            opacity: 0
            z: surface.frontSlot === slot ? 1 : 0
            sourceComponent: mediaKind === "animated" ? animated : still
            onLoaded: surface.decoded(slot, item.status)
        }
    }

    // Still images decode at their original resolution; fit affects presentation, not the file.
    Component {
        id: still
        Image {
            source: Config.fileUrl(parent.mediaPath)
            fillMode: surface.settings?.wallpaper.fit === "fill" ? Image.PreserveAspectCrop
                : surface.settings?.wallpaper.fit === "fit" ? Image.PreserveAspectFit
                : surface.settings?.wallpaper.fit === "stretch" ? Image.Stretch
                : surface.settings?.wallpaper.fit === "tile" ? Image.Tile : Image.Pad
            asynchronous: true
            cache: false
            autoTransform: true
            smooth: surface.settings?.wallpaper.fit !== "center" && surface.settings?.wallpaper.fit !== "tile"
            mipmap: smooth
            // Scaled SVGs rasterize at output resolution. Center/tile retain the intrinsic size;
            // raster images leave sourceSize unset so Qt does not request a smaller decode.
            sourceSize: /\.svg$/i.test(parent.mediaPath) && surface.settings?.wallpaper.fit !== "center"
                && surface.settings?.wallpaper.fit !== "tile"
                ? Qt.size(surface.width * (surface.screen?.devicePixelRatio || 1), surface.height * (surface.screen?.devicePixelRatio || 1))
                : undefined
            onStatusChanged: surface.decoded(parent.slot, status)
        }
    }

    // Qt owns GIF/WebP frame decoding. Pause on inactive output and repeat finite animations.
    Component {
        id: animated
        AnimatedImage {
            source: Config.fileUrl(parent.mediaPath)
            fillMode: surface.settings?.wallpaper.fit === "fill" ? Image.PreserveAspectCrop
                : surface.settings?.wallpaper.fit === "fit" ? Image.PreserveAspectFit
                : surface.settings?.wallpaper.fit === "stretch" ? Image.Stretch
                : surface.settings?.wallpaper.fit === "tile" ? Image.Tile : Image.Pad
            asynchronous: true
            cache: false
            smooth: surface.settings?.wallpaper.fit !== "center" && surface.settings?.wallpaper.fit !== "tile"
            mipmap: smooth
            paused: surface.pauseMedia
            onStatusChanged: surface.decoded(parent.slot, status)
            // Qt versions before 6.12 expose no loop count override.
            onPlayingChanged: if (!playing && status === Image.Ready && frameCount > 1)
                Qt.callLater(() => { currentFrame = 0; playing = true; })
        }
    }

    // The video child owns mpvpaper and its IPC socket; unloading it ends that playback.
    Loader {
        id: video
        active: false
        sourceComponent: Component {
            VideoWallpaper {
                sourcePath: surface.settings?.wallpaper.source || ""
                outputName: surface.screen ? surface.screen.name : ""
                fit: surface.settings?.wallpaper.fit || "fill"
                backgroundColor: surface.settings?.wallpaper.background_color || "#000000"
                paused: surface.pauseMedia
                active: true
                onStatusChanged: surface.mediaStatus = status
                onFailed: message => {
                    // Let native socket callbacks return before unloading their component.
                    // A delayed failure from a replaced player must not clear the new wallpaper.
                    const failedPlayer = video.item;
                    Qt.callLater(() => { if (video.item === failedPlayer) surface.fail(message); });
                }
            }
        }
        onStatusChanged: if (status === Loader.Error) surface.fail("Could not load the video backend")
    }
}
