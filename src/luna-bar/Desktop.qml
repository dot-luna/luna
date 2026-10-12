pragma Singleton
import "Status.js" as Status
import QtQuick
import Quickshell.Io
import Quickshell.Networking
import Quickshell.Bluetooth
import Quickshell.Services.Pipewire
import Quickshell.Services.UPower

// Native services own live state. Brightness uses a debounced CLI bridge.
QtObject {
    id: desktop

    readonly property var adapter: Bluetooth.defaultAdapter
    readonly property bool audioAvailable: !!sink && sink.ready && !!sink.audio
    property PwObjectTracker audioTracker: PwObjectTracker {
        objects: Pipewire.nodes.values.filter(node => !node.isStream && !!node.audio)
    }
    readonly property var source: Pipewire.defaultAudioSource
    readonly property bool microphoneAvailable: !!source && source.ready && !!source.audio
    readonly property var outputs: Pipewire.nodes.values.filter(node => !node.isStream && node.isSink && !!node.audio)
    readonly property var inputs: Pipewire.nodes.values.filter(node => !node.isStream && !node.isSink && !!node.audio)
    readonly property string volumeIcon: Status.volumeIcon(audioAvailable, muted, volume)
    readonly property var wifiDevices: Networking.devices.values.filter(device => device.type === DeviceType.Wifi)
    readonly property var networks: {
        const result = [];
        for (const device of wifiDevices)
            for (const network of device.networks.values) result.push(network);
        return result.sort((a, b) => Number(b.connected) - Number(a.connected) || b.signalStrength - a.signalStrength);
    }
    readonly property var connectedNetwork: networks.find(network => network.connected) || null
    readonly property string wifiIcon: Status.wifiIcon(wifiEnabled, !!connectedNetwork, connectedNetwork ? connectedNetwork.signalStrength : 0)
    readonly property var bluetoothDevices: adapter ? adapter.devices.values : []
    readonly property var connectedBluetooth: bluetoothDevices.filter(device => device.connected)
    readonly property string bluetoothIcon: connectedBluetooth.length ? "bluetooth-connected" : "bluetooth"
    readonly property var battery: UPower.displayDevice
    readonly property bool charging: hasBattery && battery.state === UPowerDeviceState.Charging
    readonly property string batteryIcon: Status.batteryIcon(hasBattery, charging, hasBattery ? battery.percentage : 0)
    readonly property string batteryRemaining: {
        if (!hasBattery) return "";
        const duration = Status.duration(charging ? battery.timeToFull : battery.timeToEmpty);
        return duration ? duration + (charging ? " until full" : " remaining") : "";
    }
    property bool powerProfilesAvailable: false
    property Process powerProfileCheck: Process {
        command: ["powerprofilesctl", "list"]
        stdout: StdioCollector {}
        stderr: StdioCollector {}
        onExited: (code, status) => desktop.powerProfilesAvailable = code === 0
    }
    function refreshPowerProfiles() {
        if (!powerProfileCheck.running) powerProfileCheck.running = true;
    }
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
