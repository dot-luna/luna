# Luna Bar

## Commands

```sh
luna bar
luna bar reload
luna bar stop
luna bar focus
luna bar controls
```

Requires a Hyprland Wayland session and Quickshell 0.3.2 or newer. Each monitor gets a top bar. Starting again keeps the existing instance; reload restarts only Luna Bar with fresh theme values.

## Layout

- Left: workspaces 1–10, with the current workspace highlighted and occupied workspaces emphasized.
- Center: date and clock. Clicking it does nothing.
- Right: network, audio, battery, and a control center button.

The control center changes Wi-Fi and Bluetooth radio state, mute, volume, and backlight brightness. It shows the active network name and battery percentage. Missing hardware disables or hides its controls. Wi-Fi connection selection and Bluetooth pairing are not part of this first version.

## Keyboard

| Keys | Action |
| --- | --- |
| Super + Ctrl + B | Start and focus the bar |
| Super + Ctrl + Space | Start and toggle the control center |
| Tab / Shift + Tab | Next / previous control, wrapping within the active panel |
| Left / Right on bar | Focus previous / next workspace or control-center button |
| Enter / Space on a button | Activate |
| Arrow keys on a slider | Adjust volume or brightness |
| Escape | Dismiss the panel or return focus to the desktop |

The bar does not take keyboard focus during ordinary use. Clicking outside the control center dismisses it. The keyboard shortcuts use the monitor currently focused by Hyprland.

## Theme

Colors come from the current theme. Rounding and background opacity follow `decoration.rounding` and `decoration.active_opacity` in the theme's `hyprland.lua`, inheriting shared Tokyo Night defaults when omitted. Text and icons stay opaque. Height stays at 32 pixels. Personal Hyprland overrides do not affect the bar; see [theme exports](../../themes/README.md).

Theme values load from the shared generated `theme.json` once per launch. After editing a theme, run `luna theme set <name>` to regenerate it, then `luna bar reload`. No theme file watcher is used. Device status updates independently through Quickshell's native services. Brightness is read at startup and when the panel opens or a change completes.

## Source

- `shell.qml`: monitor instances and scoped CLI IPC.
- `Bar.qml`: workspace buttons, date/time and status button.
- `ControlCenter.qml`: quick controls and keyboard navigation.
- `Desktop.qml`: PipeWire, NetworkManager, BlueZ, UPower and brightnessctl integration.
- `components/`: themed buttons and sliders.
- `../qml/Luna/`: shared theme and SVG icon components.
- `../luna-cli/bar/`: lifecycle commands and startup theme snapshot.

Launch the bar manually for now. Autostart is not configured.
