# Luna Menu

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
| Type | Search the current list |
| Up / Down | Select previous / next result |
| Page Up / Page Down | Move by one visible page, stopping at either end |
| Home / End | Select the first / last result |
| Tab / Shift + Tab | Select next / previous result |
| Enter | Open Apps or launch the selected application |
| Alt + Left | Go back one menu level |
| Escape | Go back one menu level; close from the main menu |

In font lists, Tab toggles selection and moves down; Shift + Tab toggles and moves up. Clicking toggles a row without checkboxes. Selected rows have an accent outline and the header shows the selection count. Selections survive search changes and clear when leaving the list or reopening the menu. Enter processes the selection, or the highlighted font when none are selected. Mixed repository/AUR installs share one dialog with separate package transactions.

Search keeps keyboard focus while selecting results. Clicking Apps opens the application list; clicking an application launches it and closes the menu. Escape goes back one level in nested menus; pressing any mouse button outside closes the launcher, including on another monitor. The list has no section label or result count, and the search placeholder is simply “Search…”. Opening uses Hyprland's focused monitor and returns to the main menu and clears the previous query.

## Top-level menu

The current view lists Apps, Learn, Trigger, Style, Setup, Install, Remove, About, and System in that order. Apps opens the searchable installed-application list. Typing at the root searches both menu sections and installed applications; application results show a small Apps parent label and launch directly. Search inside Apps stays scoped to applications. An empty root query shows only the main sections. Install → Style → Install Font opens live package search. Type at least two characters to search repositories and AUR through `luna font search --aur --json`. Each result shows its source and installed status. Enter opens a centered floating Kitty dialog using the shared font installer. Menu installs automatically confirm package prompts; sudo still requests authentication when needed. The normal CLI remains interactive. Installed results do not reinstall. Logs show completion or failure and wait for Enter before closing. Installing does not change the active theme font. Searches include descendants of the current section, with small parent labels for nested results. Remove → Style → Remove Font lists installed fonts, searchable by family, package, and source. Packaged fonts are grouped by package: selecting one removes that package and all fonts it contains. Local fonts are grouped by their primary Fontconfig family within each folder. A local entry removes all files in that group; copies in other folders and package-managed fonts remain separate. The source label includes the file count, and hovering shows the folder and styles. Sources are pacman, foreign (AUR or a manually installed package), and local. Removal uses the same centered terminal dialog, automatic confirmations, logs, and Enter-to-close behavior. Normal CLI removal still asks for confirmation. Other sections remain placeholders.

## Application search

Quickshell discovers installed `.desktop` entries from the XDG application directories. Hidden and NoDisplay entries are excluded. Search matches names, descriptions, keywords and desktop IDs, with name matches ranked first.

Application icons come from installed icon themes or the entry's absolute image path; missing icons use Luna's bundled fallback. Applications launch through Quickshell's desktop-entry API. `Terminal=true` entries run in Kitty, using the parsed argument list and working directory.

## Theme

Reads the shared resolved `theme.json` at startup. The menu has a search header and a stable-height results body, without a footer. A clear button resets the query. Application rows show an icon and name; the selected row uses the theme selection palette. All sections share the bar’s colors, UI font, rounding, and panel border width. Text sizes derive from the system Qt font size, with panel and row dimensions scaling alongside them. An unavailable theme font falls back to sans-serif. No keyboard-help legend or application-description clutter is shown. The panel background uses the theme’s `hyprland.decoration.active_opacity`. Hyprland’s launcher layer rule renders the actual blur using its global blur settings; QML does not render a blur effect. Fully transparent pixels outside the panel are excluded from blur. An opacity of 1 keeps the panel opaque. After editing a theme, run `luna theme set <name>` to regenerate it, then `luna launcher reload`. No theme watcher is used.

## Source

- `shell.qml`: overlay, search field, results and keyboard navigation.
- `Search.js`: filtering and result ranking.
- `../luna-cli/launcher/`: command registration.
- `../../lib/quickshell.lua`: shared shell lifecycle and theme loading.

Requires Quickshell 0.3.2 or newer and a Hyprland Wayland session. No launcher autostart is needed; Super + Space starts it when necessary.

## Set Font

Style → Set Font → UI / Mono searches all installed families in both pickers, including Nerd Fonts. Click or Enter applies one family; Current marks the active choice.
Choices persist across theme switches through Luna's personal font preferences.
The menu and bar update without restarting.

## System

System lists Screensaver, Lock, Suspend, Hibernate, Logout, Reboot, and Shutdown.
Logout exits the current Hyprland session. Reboot and Shutdown request normal systemd reboot/poweroff, without forcing past inhibitors. Click or Enter executes the selected action; failures appear in the menu. Lock starts Hyprlock with theme colors, UI font, and rounding. Type your system password and press Enter to unlock; PAM handles authentication. Super + L and `luna lock` also lock the session. Suspend and Hibernate check logind support, wait for the compositor to confirm the screen is locked, then request normal systemd sleep. Hibernate is hidden from menus and root search when logind reports it unavailable; availability refreshes each time the menu opens. Hibernate requires disk-backed swap and resume setup; zram alone is insufficient. These also work as `luna suspend` and `luna hibernate`. Screensaver opens a themed clock/date across all monitors. Setup → Idle configures automatic screensaver and auto-lock independently, with Disabled and preset delays. Defaults are 5 and 10 minutes.
