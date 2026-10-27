// Loaded by WallpaperSurface for video sources. Owns one mpvpaper process and
// its IPC socket, and reports readiness or failure back to the wallpaper surface.
import QtQuick
import Quickshell
import Quickshell.Io
import "Video.js" as Video

Item {
    id: root

    // Inputs from WallpaperSurface; pausing uses IPC, while other changes restart playback.
    property string sourcePath: ""
    property string outputName: ""
    property string fit: "fill"
    property color backgroundColor: "#000000"
    property bool paused: false
    property bool active: true

    // A started process is still loading until mpv reports usable video dimensions.
    readonly property string status: stateValue
    signal failed(string message)

    property string stateValue: "loading"

    // Each player gets a private working directory for its socket and isolated HOME.
    property string privateDirectory: ""
    property string playerOptions: ""
    property string lastPlayerError: ""

    // Coordinate asynchronous directory creation, process exit, and queued restarts.
    property bool completed: false
    property bool stopping: false
    property bool restartPending: false
    property bool attempted: false
    property bool connectedOnce: false
    property int startupTimeout: 15000 // Milliseconds, including directory creation and decoding.

    // mpv accepts one JSON command per line. ID 1 queries readiness; ID 2 changes pause.
    function send(command, requestId) {
        if (!ipc.connected) {
            return;
        }

        ipc.write(JSON.stringify({command: command, request_id: requestId || 0}) + "\n");
        ipc.flush();
    }

    // Remove only the directory returned by mktemp, including any stale player socket.
    function removeDirectory() {
        if (!privateDirectory) {
            return;
        }

        Quickshell.execDetached(["/usr/bin/rm", "-rf", "--", privateDirectory]);
        privateDirectory = "";
    }

    // Stop IPC before the process so its expected disconnect does not become a failure.
    function stop() {
        stopping = true;
        deadline.stop();
        poll.stop();
        ipc.connected = false;

        // Let exit handlers finish cleanup; force termination if the player does not exit.
        if (player.running) {
            player.running = false;
            stopDeadline.start();
        } else if (!directory.running) {
            removeDirectory();
            continueRestart();
        }
    }

    // Restart only after the previous process or pending directory creation has finished.
    function continueRestart() {
        if (!restartPending || !active || !completed) {
            return;
        }

        restartPending = false;
        begin();
    }

    // Input bindings can change before construction finishes; defer startup until completed.
    function restart() {
        if (!completed) {
            return;
        }

        restartPending = active;
        stop();
    }

    // Report an error once and stop playback; WallpaperSurface supplies the dark fallback.
    function fail(message) {
        if (stateValue === "error") {
            return;
        }

        stateValue = "error";
        restartPending = false;
        stop();
        failed(message);
    }

    // Validate the requested source, then create the private directory before starting mpvpaper.
    function begin() {
        stopping = false;
        connectedOnce = false;
        lastPlayerError = "";
        stateValue = "loading";

        // Pass media and connector names as arguments, and never target mpvpaper's ALL output.
        if (!sourcePath || !sourcePath.startsWith("/")) {
            fail("Video wallpaper requires an absolute local media path.");
            return;
        }
        if (!outputName || /\s/.test(outputName) || outputName.toUpperCase() === "ALL") {
            fail("Video wallpaper requires one display connector name.");
            return;
        }

        // Build playback options; unsupported fit modes use the helper's fill default.
        playerOptions = Video.options(fit, backgroundColor.toString(), paused);

        // mktemp creates a private directory even when XDG_RUNTIME_DIR is unavailable.
        var runtime = Quickshell.env("XDG_RUNTIME_DIR") || "/tmp";
        directory.command = ["/usr/bin/mktemp", "-d", "--", runtime + "/luna-wp.XXXXXX"];
        deadline.start();
        directory.running = true;
    }

    // Handle both replies to our commands and asynchronous playback/property events.
    function receive(line) {
        if (stopping) {
            return;
        }

        var message;
        try {
            message = JSON.parse(line);
            if (message === null || typeof message !== "object" || Array.isArray(message)) {
                throw new Error("Invalid IPC object");
            }
        } catch (error) {
            fail("Video player returned invalid IPC data.");
            return;
        }

        // Looping playback should not end; explicit playback errors also trigger the fallback.
        if (message.event === "end-file" || message.event === "shutdown") {
            fail("Video playback stopped" + (message.error ? ": " + message.error : "."));
        } else if (message.event === "log-message" && (message.level === "error" || message.level === "fatal")) {
            fail("Video playback failed: " + String(message.text || "unknown error").trim());
        } else if (message.event === "video-reconfig" || message.event === "file-loaded") {
            send(["get_property", "video-out-params"], 1);
        } else if ((message.request_id === 1 && message.error === "success")
                   || (message.event === "property-change" && message.name === "video-out-params")) {
            // Nonzero output dimensions confirm decoded video, rather than just a live process.
            if (Video.videoReady(message.data)) {
                stateValue = "ready";
                deadline.stop();
            }
        } else if (message.request_id === 2 && message.error !== "success") {
            // Pause is updated in place, so a failed command cannot be hidden by a restart.
            fail("Video player could not update playback: " + message.error);
        }
    }

    // Start once bindings are initialized. Destruction disables callbacks and removes runtime files.
    Component.onCompleted: {
        completed = true;
        if (active) {
            begin();
        }
    }
    Component.onDestruction: {
        completed = false;
        restartPending = false;
        stopping = true;
        ipc.connected = false;
        removeDirectory();
    }

    // Recreate the player for rendering changes; preserve it for pause/resume commands.
    onActiveChanged: restart()
    onSourcePathChanged: restart()
    onOutputNameChanged: restart()
    onFitChanged: restart()
    onBackgroundColorChanged: restart()
    onPausedChanged: send(["set_property", "pause", paused], 2)

    // Directory creation runs asynchronously; its exit handler starts the player or cleans up
    // if the surface was deactivated while mktemp was running.
    Process {
        id: directory
        stdout: StdioCollector { id: directoryOutput }
        stderr: StdioCollector {}
        onExited: function(code) {
            privateDirectory = directoryOutput.text.trim();
            if (code !== 0 || !privateDirectory) {
                root.fail("Could not create the video player's private runtime directory.");
                return;
            }
            if (stopping || !active) {
                root.removeDirectory();
                root.continueRestart();
                return;
            }

            // Unix socket paths have a small platform limit; leave room below that limit.
            if ((privateDirectory + "/ipc").length > 100) {
                root.fail("The video player's runtime socket path is too long.");
                return;
            }
            ipc.path = privateDirectory + "/ipc";
            player.workingDirectory = privateDirectory;

            // mpvpaper also reads HOME/.config/mpvpaper watch lists independently of mpv's config option.
            player.environment = {HOME: privateDirectory};

            // Bottom places video above the background fallback, below normal application windows.
            // Use argument boundaries instead of inserting paths into a shell or mpv option string.
            player.command = ["mpvpaper", "--layer", "bottom", "--mpv-options", playerOptions,
                              "--", outputName, sourcePath];
            attempted = true;
            player.running = true;
        }
    }

    // Keep mpvpaper attached to this component's Process, which also terminates it on destruction.
    // Capture only the last stderr line for an actionable failure message.
    Process {
        id: player
        stdout: SplitParser {}
        stderr: SplitParser {
            onRead: function(line) { root.lastPlayerError = line.slice(-600).trim(); }
        }
        onStarted: poll.start()
        onRunningChanged: {
            if (!running && root.attempted && !root.stopping) {
                root.fail("Could not start mpvpaper; install the wallpaper video dependency.");
            }
        }
        onExited: function(code) {
            root.attempted = false;
            stopDeadline.stop();
            if (!root.stopping) {
                root.fail("Video player exited (" + code + ")" + (root.lastPlayerError ? ": " + root.lastPlayerError : "."));
            }

            // Schedule removal of the previous player's files before starting a replacement.
            root.removeDirectory();
            root.continueRestart();
        }
    }

    // Retry connection while mpv starts, then treat an established connection's loss as failure.
    Socket {
        id: ipc
        parser: SplitParser { onRead: function(line) { root.receive(line); } }
        onConnectionStateChanged: {
            if (connected && !root.stopping) {
                root.connectedOnce = true;

                // Subscribe for decode errors and size changes, query the initial size, and sync pause.
                // The observer's ID 1 is separate from command request IDs in send().
                root.send(["request_log_messages", "error"]);
                root.send(["observe_property", 1, "video-out-params"]);
                root.send(["get_property", "video-out-params"], 1);
                root.send(["set_property", "pause", root.paused], 2);
            } else if (!connected && root.connectedOnce && !root.stopping) {
                root.fail("Video player IPC connection closed.");
            }
        }
        onError: {
            // Disconnect after Socket finishes its error callback; reentry can invalidate its native socket.
            if (root.connectedOnce && !root.stopping) {
                Qt.callLater(function() {
                    if (!root.stopping) {
                        root.fail("Video player IPC failed.");
                    }
                });
            }
        }
    }

    // mpv creates its socket after process startup; retry until connected and video is ready.
    Timer {
        id: poll
        interval: 250
        repeat: true
        onTriggered: {
            if (!ipc.connected) {
                ipc.connected = true;
            } else if (root.stateValue === "loading") {
                root.send(["get_property", "video-out-params"], 1);
            }
        }
    }

    // Bound the whole startup sequence so a missing socket or stalled decoder reaches the fallback.
    Timer {
        id: deadline
        interval: root.startupTimeout
        onTriggered: root.fail("Video wallpaper did not become ready before the startup timeout.");
    }

    // Graceful shutdown gets 1.5 seconds before SIGKILL is sent to this player only.
    Timer {
        id: stopDeadline
        interval: 1500
        onTriggered: {
            // A zero PID during startup would signal the process group instead of our child.
            if (Number(player.processId) > 0) {
                player.signal(9);
            }
        }
    }
}
