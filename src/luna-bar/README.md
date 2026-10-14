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
- Center: system-local date and clock. Click to open the Gregorian calendar and configured world clocks.
- Right: application tray icons with their native menus, followed by a notification bell with an unread dot, or a crossed bell while Do Not Disturb is enabled.
- Right: a grouped control-center trigger. Sound and power are always present (AC power uses a plug); Wi-Fi and Bluetooth appear when enabled. Icons reflect Wi-Fi signal strength, volume/mute, Bluetooth connections, and battery level/charging.

The 320px-wide control center uses a compact two-column tile grid with 44px-high tiles, 14px control icons (12px Bluetooth), 12px chevrons, and slim sliders. Its split Wi-Fi/Bluetooth tiles work as follows: the main button toggles the radio, and the chevron opens its detail screen. Sound has a mute tile and device-picker chevron; volume and supported brightness sliders sit beneath the grid. Power stays visible and opens battery details. Icons and highlights convey enabled/connected states, while text is reserved for names and useful values. The bar trigger has no dropdown arrow. There are no shortcut hints, settings redirects, or redundant headings on the main screen.

- Wi-Fi details list nearby networks with signal icons and connected state. Select a connected network to disconnect, a saved/open network to connect, or enter a password for WPA/WPA2 personal and WPA3 SAE. Enterprise and legacy networks need a previously configured NetworkManager profile. Password fields are cleared when leaving the page.
- Bluetooth details support radio control, connecting/disconnecting paired devices, battery levels when reported, discovery, and pairing/canceling nearby devices. Luna's BlueZ agent presents PIN/passkey entry and confirmation dialogs. Requests require an explicit response and close on cancellation, timeout, or device disappearance. Scans started by the panel stop when leaving it.
- Sound details select PipeWire output/input devices and control volume and microphone mute/level.
- Power details show battery charge, charging state, remaining time when reported, and available power profiles. Profile controls require a working `powerprofilesctl` and power-profiles service.

Detail screens share the same panel, support Back, and scroll to fit the monitor. Tab/Shift+Tab and Up/Down navigate available controls; Enter/Space activates buttons, and Left/Right adjusts sliders. Escape or Alt+Left returns from details (restoring focus to the original chevron); Escape on the main screen or any outside mouse press closes the panel. Hardware controls hide or disable as devices appear/disappear.

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

## Calendar and clocks

The center clock uses the system's local timezone. Its popover contains a Gregorian month grid and world clocks, with no settings controls or shortcut hints. Previous/next arrows change months; clicking the month title returns to today. Press Escape or press any mouse button outside to close. It also closes when switching workspaces, entering fullscreen, or opening another panel.

Configure it in `bar.json`:

```json
{
    "clock": {
        "use_24_hour": "system",
        "week_start": 1,
        "secondary_calendar": "bs",
        "world_clocks": [
            { "label": "US Eastern", "timezone": "America/New_York" },
            { "label": "US Central", "timezone": "America/Chicago" }
        ]
    }
}
```

`secondary_calendar` defaults to `"bs"`: the main calendar and bar date remain Gregorian (AD), with a smaller Bikram Sambat day below each grid date and a full BS date below the popup's current date. Hover a day for its full BS date. Set `"none"` to hide these labels. Only BS is currently supported as a secondary calendar. Conversion uses the system-local civil date, matching the AD date, and works offline. The bundled [medic/bikram-sambat](https://github.com/medic/bikram-sambat/tree/aeaa7b88332384bddeea98c2445308d437966641) month table covers BS 1970–2090; outside that range, secondary labels are hidden while AD navigation continues normally. The adapted converter and Apache-2.0 license are in `calendars/`.

`week_start` is `1` for Monday (default) or `0` for Sunday. World clocks appear in configured order; use an empty list to hide them. Each timezone must exist in the system's IANA timezone database. Times and local dates update every minute while the popover is open; DST and fractional offsets are handled by the system. The default world clocks are US Eastern (New York) and US Central (Chicago). US zones automatically follow standard/daylight time.

`use_24_hour` defaults to `"system"`, reading the desktop GSettings `org.gnome.desktop.interface clock-format` preference on bar startup/reload. Set it to `true` or `false` to override with 24-hour or 12-hour time. This applies to both the primary and world clocks.

The bar shows time first, for example `19:40 · Mon, 12 Oct` or `7:40 PM · Mon, 12 Oct`. An optional `clock.format` uses Qt date/time formatting for the bar text, overriding the default format derived from `use_24_hour`. For example, `"ddd · HH:mm"`. The popover uses `use_24_hour` for its clocks. Reload the bar after changing configuration.

## Keyboard

| Keys | Action |
| --- | --- |
| Super + Ctrl + B | Start and focus the bar |
| Super + Ctrl + Space | Start and toggle the control center |
| Super + N | Toggle notification history |
| Super + Shift + N | Toggle Do Not Disturb |
| Volume / mute / microphone keys | Adjust the current audio device and show a brief indicator |
| Brightness keys | Adjust screen backlight in 5% steps; hold to repeat |
| Play / next / previous keys | Control the active media player |
| Tab / Shift + Tab | Next / previous control, wrapping within the active panel |
| Left / Right on bar | Focus previous / next workspace or control-center button |
| Enter / Space on a button | Activate |
| Arrow keys on a slider | Adjust volume or brightness |
| Escape / Alt + Left | Go back within the control center; Escape on its main screen closes it |

The bar does not take keyboard focus during ordinary use. Clicking outside the control center dismisses it. The keyboard shortcuts use the monitor currently focused by Hyprland.

Volume and brightness keys repeat in 5% steps. Audio stays between 0% and 100%;
raising or lowering volume unmutes it. The indicator shows only an icon and level,
does not take focus or mouse input, and disappears after 1.5 seconds. Unavailable
devices and failed brightness writes show a short error. The same commands are
available through `luna control`.

Tray icons expose each application's native menu with right-click or Menu/Shift+F10;
left-click activates the application, and middle-click uses its secondary action.
Passive items are hidden. The control center shows a media card when a supported
player exists, with title, artist, optional local artwork, and available playback
buttons. Playing players take priority; the selected player is retained when paused.

Battery warnings appear once at 15%, with a persistent critical alert at 5%.
Charging resets the warning cycle; recovery above 20%/8% rearms each threshold.
They use Luna notifications and respect Do Not Disturb.

The bar hides on monitors whose active workspace has a fullscreen window, releasing its reserved space and dismissing the control center. It returns when fullscreen ends or you switch to a workspace without fullscreen content. Other monitors are unaffected.

## Theme

Colors and the UI font come from the resolved theme JSON. The bar and control center use `general.border_size`; keyboard focus indicators remain visible independently. Rounding follows `decoration.rounding` from the resolved theme, inheriting shared Tokyo Night defaults when omitted. Rounding also applies to buttons and sliders, capped to fit each control. The bar and control center draw opaque backgrounds. Background blur and translucency are left to Hyprland; the UI does not apply these effects. Height stays at 32 pixels. Top and side margins follow `general.gaps_out`; the control center aligns to the same outer gap. Theme values are read from JSON, while compositor effects are controlled by Hyprland; see [theme exports](../../themes/README.md).

Theme values load from the shared generated `theme.json` once per launch. After editing a theme, run `luna theme set <name>` to regenerate it, then `luna bar reload`. No theme file watcher is used. Device status updates independently through Quickshell's native services. Brightness is read at startup and when the panel opens or a change completes.

## Source

- `shell.qml`: monitor instances and scoped CLI IPC.
- `Bar.qml`: workspace buttons, date/time and status button.
- `ControlCenter.qml`: quick controls and keyboard navigation.
- `Desktop.qml`: PipeWire, NetworkManager, BlueZ, UPower and brightnessctl integration.
- `HardwareControls.qml`, `HardwareOsd.qml`: hardware-key actions and brief feedback.
- `BatteryAlerts.qml`: low and critical battery warnings.
- `Media.qml`: shared media-player selection and playback actions.
- `RecordingIndicator.qml`: visible recording stop control.
- `bluetooth/`: BlueZ authentication agent and pairing dialogs.
- `components/`: themed controls, application tray and media card.
- `../qml/Luna/`: shared theme and SVG icon components.
- `../luna-cli/bar/`: lifecycle commands and startup theme snapshot.

The Hyprland startup hook runs `luna notifications start`, which starts the bar and
notification provider together. `luna notifications setup` activates it in the
current session; later application notifications can also activate it through D-Bus.

## Notifications

The bell and `luna notifications open` open a panel with the newest messages first,
Do Not Disturb, and Clear all. Opening it marks the list read and hides
current popups. Escape or clicking outside closes the panel. Tab and Shift + Tab
navigate its controls. Left-click opens the default application action, screenshot, or recording;
right-click dismisses a popup or removes a history item. A popup without an open
action opens history; a history item without one expands its text. Enter/Space opens
the focused card and Delete dismisses it. Cards and the panel have no cross buttons.

Every card shows the sending application's icon when available (with a priority-icon
fallback), title, plain-text body, available actions, and a local image
preview when supplied. Priority badges, timestamps, counts, and explanatory footers
are omitted. Low priority uses
a quiet information style and a four-second popup. Normal uses the theme accent
and seven seconds. Critical uses an error-colored border and stays
until dismissed. An application's explicit timeout overrides low/normal defaults;
zero means persistent. Hovering pauses the timer. Up to three popups appear on the
focused monitor, with critical messages taking precedence.

Do Not Disturb suppresses all popups while collecting history; switching it off
does not replay the backlog. Its preference is saved in
`~/.config/luna/notifications.json` (or `$XDG_CONFIG_HOME/luna/notifications.json`).
History holds up to 100 messages in memory and resets on a service restart. Messages
marked transient by their sender are never archived. Expired popups remain in
history with live actions; closing a notification disables its application actions.
Screenshot and recording notices retain their local file-opening action.

Low, normal, and critical arrivals play distinct short event sounds at progressively
stronger levels. Sounds never loop, overlap, or change system volume. Bursts coalesce
to the highest priority. Do Not Disturb, an open history panel, and the sender's
`suppress-sound` hint silence them; replacements and reloads do not replay sounds.

Luna owns the desktop notification service through Quickshell. Setup installs a
user service and D-Bus activation and masks Dunst for this user so only Luna handles
delivery. Bar reload/stop commands control that service once configured. See
[notification lifecycle commands](../luna-cli/notifications/README.md).
