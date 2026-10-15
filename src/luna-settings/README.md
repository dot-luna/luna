# Luna Settings

See the [roadmap](ROADMAP.md) for planned pages, shared behavior, and implementation order.

## Launch

```sh
luna settings
```

Requires Quickshell and a Wayland session. The source lives here; no separate install or Stow package is needed.

The interface uses Luna's active theme colors, UI font, and corner rounding. Font
changes made with `luna font set` update an open window. After changing the theme,
run `luna settings reload` to reopen it with the new theme. `luna settings stop`
closes the window.

## Current interface

The sidebar groups the planned settings pages into three sections:

| Group | Pages |
| --- | --- |
| Desktop | Appearance, Wallpaper, Desktop, Windows, Notifications |
| Devices | Displays, Sound, Connectivity, Keyboard & Mouse |
| System | Power & Lock, Applications, System |

Every page shows its title, a short description, and a “Coming soon” placeholder.
There are no settings controls yet; navigating between pages does not change any
configuration.

## Keyboard

| Keys | Action |
| --- | --- |
| Tab / Shift + Tab | Move between the current sidebar entry, page, and close button |
| Up / Down in sidebar | Open previous / next page |
| Home / End in sidebar | Open the first / last page |
| Ctrl + Tab / Ctrl + Shift + Tab | Next / previous page |
| Ctrl + L | Focus the current sidebar entry |
| Ctrl + Q | Close the app |

## Structure

- `shell.qml`: window, grouped sidebar, navigation, placeholder, and palette.
- `../luna-cli/settings/`: Lua command that launches and manages the app.
