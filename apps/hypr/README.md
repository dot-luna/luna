# Hyprland

## Layout

- `apps/hypr/config/hyprland.lua`: resolves paths and loads the modules in an explicit order.
- `apps/hypr/config/autostart.lua`: starts the existing session services when Hyprland starts.
- `apps/hypr/config/input.lua`: keyboard repeat, touchpad behavior, workspace gestures and split preservation.
- `apps/hypr/config/rules.lua`: Luna surfaces, Zen picture-in-picture, GTK dialogs and the drop-down terminal.
- `apps/hypr/config/monitors.lua`: enables displays at their preferred mode with automatic placement.
- `apps/hypr/config/theme.lua`: applies the selected theme through native `hl.config()`.
- `apps/hypr/config/bindings.lua`: shares the binding helper and loads the shortcut groups below.
- `apps/hypr/config/bindings/apps.lua`: terminal and browser shortcuts.
- `apps/hypr/config/bindings/windows.lua`: navigation, resizing, fullscreen, floating and groups.
- `apps/hypr/config/bindings/workspaces.lua`: workspace/monitor navigation, scratchpad and drop-down terminal.
- `apps/hypr/config/bindings/display.lua`: desktop zoom and temporary monitor scaling.
- `apps/hypr/config/bindings/appearance.lua`: workspace layout, gaps, transparency and single-window proportions.
- `apps/hypr/config/bindings/desktop.lua`: Luna menus, lock, notifications and capture shortcuts.
- `apps/hypr/config/bindings/media.lua`: volume, brightness and media keys.
- `apps/hypr/config/animations.lua`: sets animation timings and horizontal workspace slides.
- `apps/hypr/config/workspaces.lua`: distributes numbered workspaces across monitors.
- `apps/hypr/app.lua`: declares the config directory, builder, and personal Lua include.
- `apps/hypr/build.lua`: fills `templates/paths.lua` with the checkout path in `generated/paths.lua`.

All modules are copied into the installed app config. Runtime toggles do not rewrite
these files or personal overrides.

## Load

Requires Hyprland 0.55 or newer with Lua configuration support.
The complete configuration and native callback APIs are checked against Hyprland 0.56.2.

The `apps` setup step installs the maintained files under `$LUNA_CONFIG_DIR/hypr` (normally `~/.config/luna/hypr`). It prepends a managed `dofile` block to `$XDG_CONFIG_HOME/hypr/hyprland.lua`, creating the file when absent. Personal settings stay below Luna's defaults and retain their original bytes and file mode. Reruns update the managed include without duplicating it.

Run only the Hyprland setup with:

```sh
bash scripts/setup/hypr.sh
```

Set `HYPRLAND_CONFIG` to an absolute custom Lua config path if your session uses one, including when starting Hyprland with `--config`. A legacy `hyprland.conf` is preserved: when it is the only existing config, setup installs Luna's files but skips activation with a warning. Convert that personal configuration to Lua before rerunning setup; creating a Lua file would otherwise shadow it.

Setup migrates the recognized old Luna entry point from `config/hypr/.config/hypr/hyprland.lua`, replacing its loader and preserving the personal settings below it. An old symlink into the checkout is detached into a personal file. If the old tracked target was deleted during an update, setup recovers it from local Git history; unavailable history or an unrecognized loader requires manual migration instead of discarding settings. Other personal file symlinks remain intact.

The source step links each whole directory under `src/` into `~/.local/src/`:

```sh
bash scripts/setup/12-link-sources.sh
```

For example, `~/.local/src/luna-bar` points to the checkout's `src/luna-bar`. Whole-directory links preserve the source modules' relative paths back into the checkout. Matching links are reused, and conflicting paths are replaced without backups. Back up files you want to keep before running setup.

The main `scripts/setup.sh` installs core packages, development tools, main packages, fonts, and Git apps without package-manager confirmations. It links source directories and installs `/usr/local/bin/luna` without changing shell startup files for command lookup. Setup skips Docker enablement and NVIDIA installation, and attempts to reload an active Hyprland session. Individual setup steps live under `scripts/setup/`.

The installed entry reads its own directory and generated checkout path, so it does not depend on shell environment variables or the working directory. To load an already installed configuration manually:

```lua
dofile("/home/you/.config/luna/hypr/hyprland.lua")
```

The entry point supplies theme appearance, animation defaults, and the shortcuts below. Put personal overrides after the include. Setup's session step attempts a manual reload; running `hypr.sh` alone does not reload or restart Hyprland. Back up files you want to keep before setup; no automatic backups are created.

## Animations

Windows animate in 200 ms, fades in 150 ms, layers in 180 ms, and workspaces in 220 ms. Other animations inherit a 250 ms default. Workspaces slide horizontally in the direction determined by workspace order.

## Multiple monitors

`apps/hypr/config/workspaces.lua` divides workspaces 1–10 evenly into consecutive ranges across connected monitors, ordered left to right (then top to bottom for equal horizontal positions). Two monitors get 1–5 and 6–10; three get 1–4, 5–7, and 8–10. The 0 key still selects workspace 10. Extra workspaces from an uneven split go to the leftmost monitors. Mirrored outputs do not get a separate range.

Assignments update after startup, reload, hotplug, or monitor rearrangement, moving existing numbered workspaces with their windows. With one display, all ten belong to it.

When a display starts before its workspace range is reassigned, Hyprland can temporarily open an empty workspace above 10. Luna switches that display to the first workspace in its assigned range (6 on the second of two displays) and restores the previous focus and cursor position. This also covers a quick reconnect with the same monitor arrangement. Populated, persistent, explicitly renamed, and special workspaces are preserved.

New outputs use their preferred resolution and refresh rate, automatic placement, and scale 1. Add output-specific `hl.monitor()` rules after Luna's include for a fixed arrangement and persistent scaling.

`Super + /` and `Super + Alt + /` temporarily increase/decrease the focused monitor's
scale, using valid quarter steps from 1 to 3 and the original scale. The shortcut
preserves resolution, refresh rate, position, rotation and color mode. It skips
mirrored displays, fractional logical pixel sizes and changes that would overlap
another display. At a limit, it leaves the scale alone. Automatically positioned
neighbors can move after scaling and block a later decrease; fixed positions avoid
that. Reload the config to restore the configured arrangement.

Use monitor names such as `DP-1` in advanced `hl.monitor()` overrides. Hyprland can
preserve ICC/HDR/VRR and other rule settings when updating an exact named rule;
settings inherited only from a `desc:` or catch-all rule cannot all be read back
through Lua and may be lost when a named scaling override is created.

```sh
hyprctl monitors all
```

For supported NVIDIA GPUs on Arch's standard `linux` kernel, the optional driver setup is:

```sh
bash scripts/setup/nvidia.sh
```

This step supports Turing or newer NVIDIA hardware and asks for confirmation before making changes; pressing Enter or declining skips it. After confirmation, it uses `sudo` to update the system and install `linux`, `nvidia-open`, `nvidia-utils` (including `nvidia-smi`), and `nvidia-settings`. It enables DRM modesetting, blacklists Nouveau, and rebuilds initramfs. Reboot to activate the driver before testing an external display; a Hyprland reload cannot replace the running GPU driver.

## Keybindings

### Windows and workspaces

| Shortcut | Action |
| --- | --- |
| Super + Return | Open Kitty |
| Super + Shift + Return | Open Zen |
| Super + W | Close the active window |
| Super + F | Toggle edge-to-edge monitor fullscreen for the focused window |
| Super + Alt + F | Toggle maximized window |
| Super + Ctrl + F | Toggle app fullscreen inside the window's current geometry |
| Super + Arrows | Focus the neighboring window |
| Super + Shift + Arrows | Swap with the neighboring window |
| Alt + Tab / Alt + Shift + Tab | Cycle forward/backward through windows and raise the selection |
| Super + left/right mouse drag | Move/resize a window |
| Super + −/= | Shrink/grow width by 100px; add Alt for 25px |
| Super + Shift + −/= | Shrink/grow height by 100px; add Alt for 25px |
| Super + T | Toggle floating |
| Super + J / Super + P | Toggle dwindle split direction / pseudo tiling |
| Super + O | Float, pin and raise a window; press again to unpin and tile it |
| Super + G / Super + Alt + G | Toggle a group / remove the focused window from it |
| Super + Alt + Arrows | Move the focused window into the neighboring group |
| Super + Alt + Tab / Super + Alt + Shift + Tab | Next/previous grouped window |
| Super + Ctrl + Left/Right | Previous/next grouped window |
| Super + Alt + 1–5 | Select a grouped window by position |
| Super + 1–9 | Switch to workspace 1–9 |
| Super + 0 | Switch to workspace 10 |
| Super + Shift + 1–9 / 0 | Move the focused window to that workspace and follow it (0 = 10) |
| Super + Shift + Alt + 1–9 / 0 | Move to that workspace without following |
| Super + Tab / Super + Shift + Tab | Next/previous existing workspace on this monitor |
| Super + mouse wheel | Cycle existing workspaces on this monitor |
| Super + Ctrl + Tab | Return to the former workspace on this monitor |
| Ctrl + Alt + Tab / Ctrl + Alt + Shift + Tab | Next/previous monitor |
| Super + Ctrl + Shift + Arrows | Move the window to the monitor in that direction and follow |
| Super + S / Super + Alt + S | Show/hide scratchpad / send the window there without following |
| Super + Grave (backtick) | Launch or show/hide the drop-down Kitty terminal |

Resize keys use the physical minus/equal positions on a US keyboard so Shift keeps
working across layouts. Scratchpad and terminal workspaces are separate from the
numbered 1–10 set. To return a scratchpad window, use the normal numbered move keys.
The terminal starts only when requested, opens at 90% width and half height, and
reuses its existing window. A session-specific `flock` prevents duplicate terminals.

### Display and appearance

| Shortcut | Action |
| --- | --- |
| Super + Ctrl + Z | Increase desktop zoom by 0.5, up to 3× |
| Super + Ctrl + Alt + Z | Reset zoom to 1× |
| `Super + /` and `Super + Alt + /` | Increase/decrease the focused monitor's scale |
| Super + Ctrl + L | Toggle dwindle/scrolling on the active numbered workspace |
| Super + Shift + Backspace | Toggle gaps off and restore their previous values |
| Super + Backspace | Toggle transparent/opaque windows and restore previous opacity values |
| Super + Ctrl + Backspace | Toggle square proportions for a lone tiled window |

Appearance, layout and zoom changes reset on config reload. Gap and opacity toggles
save the current values on first use, including theme and personal overrides, and
restore them on the next press. Layout switching leaves named and special workspaces
alone and keeps numbered workspace-to-monitor assignments intact. Split/pseudo
shortcuts apply to dwindle; they do not change scrolling layout behavior.

### Luna desktop

| Shortcut | Action |
| --- | --- |
| Super + L | Lock the screen |
| Super + Ctrl + B | Focus Luna Bar |
| Super + Ctrl + Space | Toggle the control center |
| Super + Space | Toggle the application launcher |
| Super + N | Toggle notification history |
| Super + Shift + N | Toggle Do Not Disturb |
| Print | Select a screenshot region |
| Shift + Print | Screenshot the active screen |
| Alt + Print | Screenshot the active window |
| Ctrl + Print | Screenshot all screens |
| Super + Print | Start region recording or stop the current recording |
| Super + Shift + Print | Stop recording |
| Volume / mute / microphone keys | Adjust sound with a small on-screen indicator |
| Brightness keys | Adjust backlight; hold to repeat |
| Play / next / previous keys | Control the active media player |

Screenshots are saved in `~/Pictures/Screenshots` and copied to the clipboard.
The same actions are available under Luna's Trigger → Screenshot menu and through
`luna screenshot [region|screen|window|all]`.

Recordings save to `~/Videos/Recordings`; Trigger → Screen Recording and
`luna record [region|screen|stop|toggle]` share the same worker and visible Stop control.
The login hook also runs `luna auth start` for administrator password dialogs.

## Input and window rules

Keys repeat at 40 characters per second after 250ms. Touchpads support tap-to-click
and two-finger right-clicking, and pause while typing.
Keyboard layout, remaps, pointer sensitivity and natural scrolling remain personal
preferences. Three-finger horizontal swipes switch existing workspaces on the
current monitor without creating extra workspaces.

Zen picture-in-picture windows float, keep their aspect ratio, stay pinned across
workspaces and open in the bottom-right corner. GTK portal dialogs float and center.
Normal browser windows and Kitty terminals keep their regular tiling behavior.

Luna's global bindings consume their matching key events and bypass application shortcut inhibitors, including in fullscreen apps. They retain normal lock-screen protection. Personal global bindings can use the same flags:

```lua
hl.bind("SUPER + F", hl.dsp.window.fullscreen({ action = "toggle", mode = "fullscreen", layout_aware = false }), {
    non_consuming = false,
    dont_inhibit = true,
})
```

## Theme behavior

- Reads `$XDG_CONFIG_HOME/luna/theme`, with the normal `~/.config` fallback.
- Reads the resolved `$XDG_CONFIG_HOME/luna/theme.json` generated by `luna theme set`.
- Maps `accent` and `muted` to active and inactive borders.
- Applies the resolved Hyprland settings, including inherited defaults, and derives shadow colors from background tokens.
- No selected theme leaves Hyprland's other settings intact. Invalid or missing selected themes report a config error.
- Resolved values are validated with the same rules used by `luna theme install`.
- Edit theme sources and run `luna theme set <name>` to regenerate JSON before reloading. No automatic live reload is used.

```sh
luna theme set tokyo-night
hyprctl reload
```

Reload manually when you want the newly selected appearance applied. The adapter does not install fonts or select a wallpaper.
