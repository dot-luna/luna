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
    readonly property bool microphoneMuted: microphoneAvailable ? source.audio.muted : false
    readonly property real microphoneVolume: microphoneAvailable ? source.audio.volume : 0
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
    property bool brightnessPending: false
    property int brightnessRevision: 0
    property int brightnessWriteRevision: 0
    signal brightnessFinished(bool success, string message)

    // Coalesce slider motion and serialize writes to avoid competing processes.
    property Timer brightnessDebounce: Timer {
        interval: 120

        onTriggered: {
            if (desktop.brightnessWrite.running || desktop.brightnessRead.running) {
                restart();
                return;
            }
            desktop.brightnessWriteRevision = desktop.brightnessRevision;
            desktop.brightnessWrite.command = ["brightnessctl", "-m", "-c", "backlight", "set", desktop.requestedBrightness + "%"];
            desktop.brightnessWrite.running = true;
        }
    }
    property Process brightnessRead: Process {
        command: ["brightnessctl", "-m", "-c", "backlight", "info"]
        running: true

        stderr: StdioCollector {
        }
        stdout: StdioCollector { id: brightnessReadResult }
        onExited: (code, status) => {
            const value = desktop.parseBrightness(brightnessReadResult.text);
            desktop.brightnessAvailable = code === 0 && value >= 0;
            if (desktop.brightnessAvailable) {
                desktop.brightness = value;
                if (!desktop.brightnessPending)
                    desktop.requestedBrightness = value;
            }
        }
    }
    property Process brightnessWrite: Process {
        stderr: StdioCollector {
            id: brightnessError
        }
        stdout: StdioCollector { id: brightnessWriteResult }

        onExited: (code, status) => {
            const value = desktop.parseBrightness(brightnessWriteResult.text);
            const success = code === 0 && value >= 0;
            desktop.error = success ? "" : brightnessError.text.trim() || "Brightness change failed";
            if (success) {
                desktop.brightness = value;
                if (desktop.brightnessWriteRevision === desktop.brightnessRevision) {
                    desktop.brightnessPending = false;
                    desktop.requestedBrightness = value;
                }
            } else {
                // Cancel queued repeats after a failed write instead of retrying permissions forever.
                desktop.brightnessDebounce.stop();
                desktop.brightnessPending = false;
                desktop.requestedBrightness = desktop.brightness;
                desktop.refreshBrightness();
            }
            desktop.brightnessFinished(success, desktop.error);
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
        if (!brightnessRead.running && !brightnessPending && !brightnessWrite.running)
            brightnessRead.running = true;
    }
    function parseBrightness(text) {
        const field = text.trim().split(",")[3] || "";
        if (!/^\d+(?:\.\d+)?%$/.test(field))
            return -1;
        const value = Number(field.slice(0, -1));
        return value >= 0 && value <= 100 ? Math.round(value) : -1;
    }
    function setBrightness(value) {
        requestedBrightness = Math.max(1, Math.min(100, Math.round(value)));
        brightnessPending = true;
        brightnessRevision++;
        brightnessDebounce.restart();
    }
    function adjustBrightness(change) {
        setBrightness((brightnessPending ? requestedBrightness : brightness) + change);
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
    function toggleMicrophoneMute() {
        if (microphoneAvailable)
            source.audio.muted = !source.audio.muted;
    }
    function toggleWifi() {
        Networking.wifiEnabled = !Networking.wifiEnabled;
    }
}
