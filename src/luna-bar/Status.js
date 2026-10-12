// Shared status thresholds keep the bar and control-center icons consistent.
.pragma library

function wifiIcon(enabled, connected, strength) {
    if (!enabled) return "wifi-off";
    if (!connected) return "wifi-zero";
    return strength >= 0.7 ? "wifi" : strength >= 0.4 ? "wifi-high" : "wifi-low";
}
function volumeIcon(available, muted, volume) {
    if (!available || muted) return "volume-x";
    return volume === 0 ? "volume" : volume < 0.5 ? "volume-1" : "volume-2";
}
function batteryIcon(present, charging, percentage) {
    if (!present) return "plug";
    if (charging) return "battery-charging";
    return percentage <= 0.15 ? "battery-warning" : percentage < 0.35 ? "battery-low"
        : percentage < 0.8 ? "battery-medium" : "battery-full";
}
function duration(seconds) {
    const minutes = Math.round(seconds / 60);
    if (minutes <= 0) return "";
    return minutes >= 60 ? Math.floor(minutes / 60) + "h " + minutes % 60 + "m" : minutes + "m";
}
