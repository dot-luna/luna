# Luna Launcher

## Commands

```sh
luna launcher
luna launcher toggle
luna launcher start
luna launcher reload
luna launcher stop
```

The default command opens the launcher. `toggle` opens or dismisses it; `start` prepares a hidden instance. Reload restarts the instance with fresh theme colors and leaves it hidden.

## Keyboard

| Keys | Action |
| --- | --- |
| Super + Space | Toggle launcher |
| Type | Search installed applications |
| Up / Down | Select previous / next result |
| Tab / Shift + Tab | Select next / previous result |
| Enter | Launch selected application |
| Escape | Close launcher |

Search keeps keyboard focus while selecting results. Clicking a result launches it; clicking outside closes the launcher. Opening uses Hyprland's focused monitor and clears the previous query.

## Applications

Quickshell discovers installed `.desktop` entries from the XDG application directories. Hidden and NoDisplay entries are excluded. Search matches names, descriptions, keywords and desktop IDs, with name matches ranked first.

Application icons come from installed icon themes or the entry's absolute image path; missing icons use Luna's bundled fallback. Applications launch through Quickshell's desktop-entry API. `Terminal=true` entries run in Kitty, using the parsed argument list and working directory.

## Theme

Reads the shared resolved `theme.json` at startup. After editing a theme, run `luna theme set <name>` to regenerate it, then `luna launcher reload`. No theme watcher is used.

## Source

- `shell.qml`: overlay, search field, results and keyboard navigation.
- `Search.js`: filtering and result ranking.
- `../luna-cli/launcher/`: command registration.
- `../../lib/quickshell.lua`: shared shell lifecycle and theme loading.

Requires Quickshell 0.3.2 or newer and a Hyprland Wayland session. No launcher autostart is needed; Super + Space starts it when necessary.
