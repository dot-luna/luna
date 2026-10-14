pragma ComponentBehavior: Bound
import QtQuick
import Quickshell.Io

// One player and one pending priority keep notification bursts from overlapping.
QtObject {
    id: sound

    property bool enabled: true
    property int _pendingUrgency: -1
    property real _pendingSince: 0
    property real _lastPlayed: 0
    property int _lastUrgency: -1
    property bool _warned: false
    property bool _cancelled: false

    function play(urgency: int): void {
        if (!enabled)
            return;
        const priority = urgency === 0 || urgency === 2 ? urgency : 1;
        if (_pendingUrgency < 0)
            _pendingSince = Date.now();
        _pendingUrgency = Math.max(_pendingUrgency, priority);
        schedule();
    }

    function schedule() {
        if (!enabled || _pendingUrgency < 0 || player.running)
            return;
        // Critical alerts can follow a lower-priority sound without its cooldown.
        const cooldown = _pendingUrgency === 2 && _lastUrgency < 2 ? 0 : _lastPlayed + 800;
        wake.interval = Math.max(1, Math.max(_pendingSince + 100, cooldown) - Date.now());
        wake.restart();
    }

    function flush() {
        if (!enabled || _pendingUrgency < 0 || player.running)
            return;
        const urgency = _pendingUrgency;
        _pendingUrgency = -1;
        _lastPlayed = Date.now();
        _lastUrgency = urgency;
        _cancelled = false;
        const event = urgency === 2 ? "dialog-warning" : urgency === 0 ? "message-new-instant" : "message";
        const volume = urgency === 2 ? "-6" : urgency === 0 ? "-18" : "-12";
        // AppImage libraries must not replace the system sound player's dependencies.
        player.command = ["env", "-u", "LD_LIBRARY_PATH", "-u", "LD_PRELOAD", "canberra-gtk-play",
            "--id=" + event, "--volume=" + volume, "--loop=1"];
        player.running = true;
    }

    onEnabledChanged: {
        if (!enabled) {
            wake.stop();
            _pendingUrgency = -1;
            _cancelled = true;
            player.running = false;
        }
    }

    property Timer _wake: Timer {
        id: wake
        onTriggered: sound.flush()
    }
    property Process _player: Process {
        id: player
        stdout: StdioCollector {}
        stderr: StdioCollector {}
        onExited: (code, status) => {
            if (code !== 0 && !sound._cancelled && !sound._warned) {
                sound._warned = true;
                console.warn("Could not play a Luna notification sound.");
            }
        }
        onRunningChanged: {
            if (!running)
                sound.schedule();
        }
    }
}
