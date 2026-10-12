pragma Singleton
import QtQuick
import Quickshell.Io
import Quickshell.Networking
import Quickshell.Bluetooth
import Quickshell.Services.Pipewire
import Quickshell.Services.UPower

// Quickshell's native services own device state; only brightness needs a CLI bridge.
QtObject {
    id: desktop

    readonly property var adapter: Bluetooth.defaultAdapter
    readonly property bool audioAvailable: !!sink && sink.ready && !!sink.audio
    property PwObjectTracker audioTracker: PwObjectTracker {
        objects: desktop.sink ? [desktop.sink] : []
    }
    readonly property var battery: UPower.displayDevice
    readonly property string batteryText: hasBattery ? Math.round(battery.percentage * 100) + "%" : "AC power"
    readonly property bool bluetoothEnabled: adapter ? adapter.enabled : false
    property int brightness: 0
    property bool brightnessAvailable: false

    // Coalesce slider motion and serialize writes to avoid competing processes.
    property Timer brightnessDebounce: Timer {
        interval: 120

        onTriggered: {
            if (desktop.brightnessWrite.running) {
                restart();
                return;
            }
            desktop.brightnessWrite.command = ["brightnessctl", "-c", "backlight", "set", desktop.requestedBrightness + "%"];
            desktop.brightnessWrite.running = true;
        }
    }
    property Process brightnessRead: Process {
        command: ["brightnessctl", "-m", "-c", "backlight", "info"]
        running: true

        stderr: StdioCollector {
        }
        stdout: StdioCollector {
            onStreamFinished: {
                const fields = text.trim().split(",");
                const value = parseInt(fields[3]);
                desktop.brightnessAvailable = Number.isFinite(value);
                if (desktop.brightnessAvailable)
                    desktop.brightness = value;
            }
        }
    }
    property Process brightnessWrite: Process {
        stderr: StdioCollector {
            id: brightnessError
        }
        stdout: StdioCollector {
        }

        onExited: (code, status) => {
            desktop.error = code === 0 ? "" : brightnessError.text.trim() || "Brightness change failed";
            desktop.refreshBrightness();
        }
    }
    property string error: ""
    readonly property bool hasBattery: !!battery && battery.ready && battery.isPresent && battery.isLaptopBattery
    readonly property bool muted: audioAvailable ? sink.audio.muted : false
    readonly property string networkName: {
        for (const device of Networking.devices.values) {
            for (const network of device.networks.values) {
                if (network.connected)
                    return network.name;
            }
        }
        return wifiEnabled ? "Not connected" : "Wi-Fi off";
    }
    property int requestedBrightness: 0
    readonly property var sink: Pipewire.defaultAudioSink
    readonly property real volume: audioAvailable ? sink.audio.volume : 0
    readonly property bool wifiAvailable: Networking.devices.values.some(device => device.type === DeviceType.Wifi)
    readonly property bool wifiEnabled: Networking.wifiEnabled
    readonly property bool wifiHardwareEnabled: Networking.wifiHardwareEnabled

    function refreshBrightness() {
        if (!brightnessRead.running)
            brightnessRead.running = true;
    }
    function setBrightness(value) {
        requestedBrightness = Math.max(1, Math.min(100, Math.round(value)));
        brightnessDebounce.restart();
    }
    function setVolume(value) {
        if (audioAvailable)
            sink.audio.volume = Math.max(0, Math.min(1, value));
    }
    function toggleBluetooth() {
        if (adapter)
            adapter.enabled = !adapter.enabled;
    }
    function toggleMute() {
        if (audioAvailable)
            sink.audio.muted = !sink.audio.muted;
    }
    function toggleWifi() {
        Networking.wifiEnabled = !Networking.wifiEnabled;
    }
}
