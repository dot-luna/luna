pragma ComponentBehavior: Bound
import QtQuick

// Hardware keys share the control center's native devices and one short-lived OSD.
QtObject {
    id: controls

    property var backend: Desktop
    property var screen: null
    property string category: ""
    property string icon: "volume"
    property real level: 0
    property bool muted: false
    property string error: ""
    readonly property bool visible: hide.running
    property bool _brightnessRequested: false

    function present(kind, symbol, value, isMuted, message) {
        category = kind;
        icon = symbol;
        level = Math.max(0, Math.min(1, value));
        muted = isMuted;
        error = message || "";
        hide.restart();
    }

    function run(action: string): bool {
        if (action === "volume-up" || action === "volume-down" || action === "volume-mute") {
            if (!backend.audioAvailable) {
                present("volume", "volume-x", 0, true, "No audio output");
                return false;
            }
            if (action === "volume-mute") {
                backend.toggleMute();
            } else {
                backend.setVolume(Math.round((backend.volume + (action === "volume-up" ? 0.05 : -0.05)) * 100) / 100);
                if (backend.muted)
                    backend.toggleMute();
            }
            present("volume", backend.muted ? "volume-x" : backend.volume < 0.5 ? "volume-1" : "volume-2",
                backend.volume, backend.muted, "");
            return true;
        }
        if (action === "mic-mute") {
            if (!backend.microphoneAvailable) {
                present("microphone", "mic-off", 0, true, "No microphone");
                return false;
            }
            backend.toggleMicrophoneMute();
            present("microphone", backend.microphoneMuted ? "mic-off" : "mic", backend.microphoneVolume,
                backend.microphoneMuted, "");
            return true;
        }
        if (action === "brightness-up" || action === "brightness-down") {
            if (!backend.brightnessAvailable) {
                present("brightness", "sun", 0, false, "Brightness unavailable");
                return false;
            }
            _brightnessRequested = true;
            backend.adjustBrightness(action === "brightness-up" ? 5 : -5);
            present("brightness", "sun", backend.requestedBrightness / 100, false, "");
            return true;
        }
        return false;
    }

    function status(): string {
        return JSON.stringify({visible: visible, category: category, icon: icon, level: level,
            muted: muted, error: error});
    }

    property Connections _brightness: Connections {
        target: controls.backend
        function onBrightnessFinished(success, message) {
            if (!controls._brightnessRequested)
                return;
            if (controls.category === "brightness") {
                controls.present("brightness", "sun", (controls.backend.brightnessPending
                    ? controls.backend.requestedBrightness : controls.backend.brightness) / 100,
                    false, success ? "" : "Brightness change failed");
            }
            if (!controls.backend.brightnessPending)
                controls._brightnessRequested = false;
        }
    }
    property Timer _hide: Timer {
        id: hide
        interval: 1500
    }
    property Loader _window: Loader {
        active: controls.visible && controls.screen !== null
        sourceComponent: Component {
            HardwareOsd {
                screen: controls.screen
                icon: controls.icon
                level: controls.level
                muted: controls.muted
                error: controls.error
            }
        }
    }
}
