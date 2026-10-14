pragma ComponentBehavior: Bound
import QtQuick
import Quickshell.Io
import Quickshell.Services.UPower

// Instantiate once in ShellRoot, independently of monitor count.
QtObject {
    id: alerts

    property var backend: Desktop
    property bool enabled: true
    property bool _lowSent: false
    property bool _criticalSent: false
    property int _pending: -1
    property int _percentage: 0
    property bool _warned: false
    readonly property string observedState: JSON.stringify([enabled, backend.hasBattery,
        backend.battery ? backend.battery.percentage : -1, backend.battery ? backend.battery.state : 0])

    function evaluate() {
        if (!enabled || !backend.hasBattery || !backend.battery) {
            _lowSent = false;
            _criticalSent = false;
            _pending = -1;
            return;
        }
        const state = backend.battery.state;
        const percentage = Number(backend.battery.percentage);
        if (!Number.isFinite(percentage) || percentage < 0 || percentage > 1)
            return;
        if (state === UPowerDeviceState.Charging || state === UPowerDeviceState.FullyCharged
                || state === UPowerDeviceState.PendingCharge) {
            _lowSent = false;
            _criticalSent = false;
            _pending = -1;
            return;
        }
        if (state !== UPowerDeviceState.Discharging && state !== UPowerDeviceState.PendingDischarge
                && state !== UPowerDeviceState.Empty)
            return;

        // Recovery thresholds prevent noisy battery estimates from repeatedly crossing a boundary.
        if (percentage >= 0.20)
            _lowSent = false;
        if (percentage >= 0.08)
            _criticalSent = false;
        let urgency = -1;
        if (percentage <= 0.05 && !_criticalSent) {
            urgency = 2;
            _criticalSent = true;
            _lowSent = true;
        } else if (percentage <= 0.15 && !_lowSent) {
            urgency = 1;
            _lowSent = true;
        }
        if (urgency >= 0) {
            _pending = Math.max(_pending, urgency);
            _percentage = Math.round(percentage * 100);
            send();
        }
    }

    function send() {
        if (_pending < 0 || sender.running || !enabled)
            return;
        const battery = backend.battery;
        const discharging = battery && (battery.state === UPowerDeviceState.Discharging
            || battery.state === UPowerDeviceState.PendingDischarge || battery.state === UPowerDeviceState.Empty);
        if (!backend.hasBattery || !discharging || battery.percentage > (_pending === 2 ? 0.05 : 0.15)) {
            _pending = -1;
            return;
        }
        const critical = _pending === 2;
        _pending = -1;
        sender.command = ["env", "-u", "LD_LIBRARY_PATH", "-u", "LD_PRELOAD", "notify-send",
            "--app-name=Luna Battery", "--icon=" + (critical ? "battery-caution" : "battery-low"),
            "--urgency=" + (critical ? "critical" : "normal"), "--",
            critical ? "Battery critical" : "Battery low", _percentage + "% remaining. Connect a charger."];
        sender.running = true;
    }

    onObservedStateChanged: update.restart()
    Component.onCompleted: update.restart()
    property Timer _update: Timer {
        id: update
        interval: 100
        onTriggered: alerts.evaluate()
    }
    property Process _sender: Process {
        id: sender
        stdout: StdioCollector {}
        stderr: StdioCollector {}
        onExited: (code, status) => {
            if (code !== 0 && !alerts._warned) {
                alerts._warned = true;
                console.warn("Could not send a Luna battery alert.");
            }
        }
        onRunningChanged: {
            if (!running)
                alerts.send();
        }
    }
}
