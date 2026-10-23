# Hyprland

## Layout

- `apps/hypr/hyprland.lua`: Luna's maintained entry point, copied into the installed app config.
- `apps/hypr/monitors.lua`: enables displays at their preferred mode with automatic placement.
- `apps/hypr/theme.lua`: applies the selected theme through native `hl.config()`.
- `apps/hypr/bindings.lua`: registers Luna's basic keyboard shortcuts.
- `apps/hypr/animations.lua`: sets animation timings and horizontal workspace slides.
- `apps/hypr/workspaces.lua`: distributes numbered workspaces across monitors.
- `apps/hypr/scripts/generate-config.lua`: generates the installed checkout path in `generated/paths.lua`.

## Load

Requires Hyprland 0.55 or newer with Lua configuration support.

The `apps` setup step installs the maintained files under `$LUNA_CONFIG_DIR/hypr` (normally `~/.config/luna/hypr`). It prepends a managed `dofile` block to `$XDG_CONFIG_HOME/hypr/hyprland.lua`, creating the file when absent. Personal settings stay below Luna's defaults and retain their original bytes and file mode. Reruns update the managed include without duplicating it.

Run only the Hyprland setup with:

```sh
bash scripts/setup/hypr.sh
```

Set `HYPRLAND_CONFIG` to an absolute custom Lua config path if your session uses one, including when starting Hyprland with `--config`. A legacy `hyprland.conf` is preserved: when it is the only existing config, setup installs Luna's files but skips activation with a warning. Convert that personal configuration to Lua before rerunning setup; creating a Lua file would otherwise shadow it.

Setup migrates the recognized old Luna entry point from `config/hypr/.config/hypr/hyprland.lua`, replacing its loader and preserving the personal settings below it. An old symlink into the checkout is detached into a personal file. If the old tracked target was deleted during an update, setup recovers it from local Git history; unavailable history or an unrecognized loader requires manual migration instead of discarding settings. Other personal file symlinks remain intact.

The source step links each whole directory under `src/` into `~/.local/src/`:

```sh
bash scripts/setup/src.sh
```

For example, `~/.local/src/luna-bar` points to the checkout's `src/luna-bar`. Whole-directory links preserve the source modules' relative paths back into the checkout. Matching links are reused, and conflicting paths are replaced without backups. Back up files you want to keep before running setup.

The main `scripts/setup.sh` installs core packages, development tools, main packages, fonts, and Git apps without package-manager confirmations. It links source directories and installs `~/.local/bin/luna`. Open a new terminal after setup so the shell uses that command path. Setup skips Docker enablement and NVIDIA installation, and attempts to reload an active Hyprland session. Individual setup steps live under `scripts/setup/`.

The installed entry reads its own directory and generated checkout path, so it does not depend on shell environment variables or the working directory. To load an already installed configuration manually:

```lua
dofile("/home/you/.config/luna/hypr/hyprland.lua")
```

The entry point supplies theme appearance, animation defaults, and the shortcuts below. Put personal overrides after the include. Setup's session step attempts a manual reload; running `hypr.sh` alone does not reload or restart Hyprland. Back up files you want to keep before setup; no automatic backups are created.

## Animations

Windows animate in 200 ms, fades in 150 ms, layers in 180 ms, and workspaces in 220 ms. Other animations inherit a 250 ms default. Workspaces slide horizontally in the direction determined by workspace order.

## Multiple monitors

`apps/hypr/workspaces.lua` divides workspaces 1–10 evenly into consecutive ranges across connected monitors, ordered left to right (then top to bottom for equal horizontal positions). Two monitors get 1–5 and 6–10; three get 1–4, 5–7, and 8–10. The 0 key still selects workspace 10. Extra workspaces from an uneven split go to the leftmost monitors. Mirrored outputs do not get a separate range.

Assignments update after startup, reload, hotplug, or monitor rearrangement, moving existing numbered workspaces with their windows. With one display, all ten belong to it.

When a display starts before its workspace range is reassigned, Hyprland can temporarily open an empty workspace above 10. Luna switches that display to the first workspace in its assigned range (6 on the second of two displays) and restores the previous focus and cursor position. This also covers a quick reconnect with the same monitor arrangement. Populated, persistent, explicitly renamed, and special workspaces are preserved.

New outputs use their preferred resolution and refresh rate, automatic placement, and scale 1. Monitor scaling belongs in your personal display configuration. Add output-specific `hl.monitor()` rules after Luna's include for a fixed arrangement.

```sh
hyprctl monitors all
```

For supported NVIDIA GPUs on Arch's standard `linux` kernel, the optional driver setup is:

```sh
bash scripts/setup/nvidia.sh
```

This step supports Turing or newer NVIDIA hardware and asks for confirmation before making changes; pressing Enter or declining skips it. After confirmation, it uses `sudo` to update the system and install `linux`, `nvidia-open`, `nvidia-utils` (including `nvidia-smi`), and `nvidia-settings`. It enables DRM modesetting, blacklists Nouveau, and rebuilds initramfs. Reboot to activate the driver before testing an external display; a Hyprland reload cannot replace the running GPU driver.

## Keybindings

| Shortcut | Action |
| --- | --- |
| Super + Return | Open Kitty |
| Super + Shift + Return | Open Zen |
| Super + W | Close the active window |
| Super + F | Toggle edge-to-edge monitor fullscreen for the focused window |
| Super + 1–9 | Switch to workspace 1–9 |
| Super + 0 | Switch to workspace 10 |
| Super + Shift + 1–9 / 0 | Move the focused window to that workspace and follow it (0 = 10) |
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
