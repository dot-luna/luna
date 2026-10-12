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

- Left: four workspace slots by default, with higher workspaces added while they exist or are active. Inactive workspaces are uniformly muted dots; the current workspace shows its configured icon or an accent-colored number (1–9, 0) without a filled background.
- Center: date and clock. Clicking it does nothing.
- Right: network, audio, battery, and a control center button.

The control center changes Wi-Fi and Bluetooth radio state, mute, volume, and backlight brightness. It shows the active network name and battery percentage. Missing hardware disables or hides its controls. Wi-Fi connection selection and Bluetooth pairing are not part of this first version.

## Workspace indicators

User preferences live in `$XDG_CONFIG_HOME/luna/bar.json`, normally `~/.config/luna/bar.json`. Luna creates this file from [config.json](config.json) on the first start if it is missing. Theme changes do not overwrite it. Edit it and run `luna bar reload`.

The base indicators are:

```json
{
    "workspaces": {
        "active": { "type": "number", "size": 12 },
        "inactive": { "type": "dot", "size": 5 }
    }
}
```

Each state accepts `number`, `dot`, `label`, or `icon`. Omitted states use defaults. `size` is an integer from 1 to 24 pixels; defaults are 12 for text, 5 for dots, and 14 for icons. Numbers use 1–9, 0. Labels accept `{number}`, for example `{ "type": "label", "label": "[{number}]" }`.

To replace both indicators with SVGs:

```json
{
    "workspaces": {
        "active": { "type": "icon", "path": "icons/workspace-active.svg", "size": 14 },
        "inactive": { "type": "icon", "path": "icons/workspace-inactive.svg", "size": 12 }
    }
}
```

Individual workspaces can override their active indicator with an icon. The shipped config maps `1` to code, `2` to terminal, `3` to browser, and `0` to AI:

```json
{
    "workspaces": {
        "overrides": {
            "1": { "type": "icon", "icon": "code-xml" },
            "2": { "type": "icon", "icon": "terminal" },
            "3": { "type": "icon", "icon": "globe" },
            "0": { "type": "icon", "icon": "bot" }
        }
    }
}
```

`icon` selects a bundled SVG by name; use `path` instead for your own file. Override keys use `1`–`9` and `0` (Hyprland workspace 10). Overrides apply only to the active workspace. Inactive workspaces use the shared inactive indicator, which defaults to a muted dot. Workspaces without an override use the base indicators. Removing an override restores that workspace's number/dot behavior. Overrides do not create extra workspace slots.

SVG paths are relative to the folder containing `bar.json`; absolute paths and `~/` paths also work. Use local SVG files. Icons are tinted with the theme's accent for the active workspace and muted foreground for inactive workspaces. If an SVG cannot render, its workspace number is shown instead. Invalid JSON, unsupported fields, and missing SVG files fail before stopping the running bar. The stop command still works with invalid preferences.

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

The bar hides on monitors whose active workspace has a fullscreen window, releasing its reserved space and dismissing the control center. It returns when fullscreen ends or you switch to a workspace without fullscreen content. Other monitors are unaffected.

## Theme

Colors and the UI font come from the resolved theme JSON. The bar and control center use `general.border_size`; keyboard focus indicators remain visible independently. Rounding and background opacity follow `decoration.rounding` and `decoration.active_opacity` in the theme's `hyprland.lua`, inheriting shared Tokyo Night defaults when omitted. Rounding also applies to buttons and sliders, capped to fit each control. Popup translucency affects its background only; text and icons stay opaque. Height stays at 32 pixels. Top and side margins follow `general.gaps_out`; the control center aligns to the same outer gap. Personal Hyprland overrides do not affect the bar; see [theme exports](../../themes/README.md).

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
