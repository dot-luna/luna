import QtQuick
import QtTest
import "../../src/luna-bar/Status.js" as Status

TestCase {
    name: "Status"
    function test_wifi_connection_and_signal() {
        compare(Status.wifiIcon(false, false, 0), "wifi-off");
        compare(Status.wifiIcon(true, false, 1), "wifi-zero");
        compare(Status.wifiIcon(true, true, 0.2), "wifi-low");
        compare(Status.wifiIcon(true, true, 0.5), "wifi-high");
        compare(Status.wifiIcon(true, true, 0.9), "wifi");
    }
    function test_volume_mute_and_unavailable() {
        compare(Status.volumeIcon(false, false, 1), "volume-x");
        compare(Status.volumeIcon(true, true, 1), "volume-x");
        compare(Status.volumeIcon(true, false, 0), "volume");
        compare(Status.volumeIcon(true, false, 0.3), "volume-1");
        compare(Status.volumeIcon(true, false, 1), "volume-2");
    }
    function test_battery_charging_and_levels() {
        compare(Status.batteryIcon(false, false, 0), "plug");
        compare(Status.batteryIcon(true, true, 0.1), "battery-charging");
        compare(Status.batteryIcon(true, false, 0.1), "battery-warning");
        compare(Status.batteryIcon(true, false, 0.25), "battery-low");
        compare(Status.batteryIcon(true, false, 0.6), "battery-medium");
        compare(Status.batteryIcon(true, false, 1), "battery-full");
    }
    function test_remaining_time() {
        compare(Status.duration(0), "");
        compare(Status.duration(1800), "30m");
        compare(Status.duration(5400), "1h 30m");
    }
}
