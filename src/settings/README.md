# Luna Settings

## Launch

```sh
luna settings
```

Requires Quickshell and a Wayland session. The source lives here; no separate install or Stow package is needed.

## Preview

- Appearance: sample themes and color mode.
- Wallpapers: local illustration previews and image fit.
- Fonts: sample font choices and size.
- Windows: Hyprland gaps, borders, rounding, blur and opacity.
- Keyboard: desktop shortcuts and app navigation.

Controls update only the mockup. Nothing is installed, downloaded, persisted or applied to Hyprland. Selections survive page changes and reset when the app closes.

## Keyboard

| Keys | Action |
| --- | --- |
| Tab / Shift + Tab | Next / previous control |
| Up / Down in sidebar | Open previous / next page |
| Tab / Right / Enter in sidebar | Focus the first setting |
| Shift + Tab in sidebar | Focus the last setting |
| Enter / Space | Activate a focused button or switch |
| Arrow keys | Adjust selections and numeric controls |
| Space in a dropdown | Open choices; arrows choose, Enter confirms, Escape cancels |
| Ctrl + Tab / Ctrl + Shift + Tab | Next / previous page |
| Alt + 1–5 | Open a page directly |
| Ctrl + L | Focus the current sidebar entry |
| Ctrl + Q | Close the app |

## Structure

- `shell.qml`: window, sidebar, navigation and palette.
- `pages/`: one component per settings page.
- `components/`: reusable groups, rows and previews.
- `../luna-cli/settings/`: Lua command that launches the preview.
