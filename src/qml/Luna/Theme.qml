pragma Singleton
import QtQuick
import Quickshell

// The Lua launcher passes one validated snapshot. Theme changes require a restart.
QtObject {
    readonly property color accent: colors.accent || "#7aa2f7"
    readonly property color accentForeground: colors.accent_foreground || "#1a1b26"
    readonly property color background: colors.background || "#1a1b26"
    readonly property var bar: snapshot.bar || ({})
    readonly property int barHeight: bar.height ?? 32
    readonly property real barOpacity: bar.opacity ?? 1
    readonly property int barRounding: bar.rounding ?? 0
    readonly property color brightForeground: colors.bright_foreground || "#c0caf5"
    readonly property var colors: snapshot.colors || ({})
    readonly property color foreground: colors.foreground || "#a9b1d6"
    readonly property color lighterBackground: colors.lighter_background || "#24283b"
    readonly property color muted: colors.muted || "#414868"
    readonly property color selection: colors.selection || "#292e42"
    readonly property var snapshot: JSON.parse(Quickshell.env("LUNA_UI_THEME") || "{}")
}
