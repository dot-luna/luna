pragma Singleton
import QtQuick
import Quickshell

// The Lua launcher passes one validated snapshot. Theme changes require a restart.
QtObject {
    readonly property color accent: colors.accent
    readonly property color accentForeground: colors.accent_foreground
    readonly property color background: colors.background
    readonly property var decoration: snapshot.hyprland.decoration
    readonly property int borderWidth: snapshot.hyprland.general.border_size
    readonly property int outerGap: snapshot.hyprland.general.gaps_out
    readonly property string uiFont: snapshot.fonts.ui
    readonly property color selectionForeground: colors.selection_foreground
    readonly property int barHeight: 32
    readonly property real barOpacity: decoration.active_opacity
    readonly property int barRounding: decoration.rounding
    readonly property color brightForeground: colors.bright_foreground
    readonly property var colors: snapshot.colors
    readonly property color foreground: colors.foreground
    readonly property color lighterBackground: colors.lighter_background
    readonly property color muted: colors.muted
    readonly property color selection: colors.selection
    readonly property var snapshot: JSON.parse(Quickshell.env("LUNA_UI_THEME"))
}
