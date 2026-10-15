# Hyprland

## Layout

- `config/hypr/.config/hypr/hyprland.lua`: Stow-managed entry point and place for personal overrides.
- `default/hypr/bootstrap.lua`: loads reusable Luna defaults.
- `default/hypr/monitors.lua`: enables displays at their preferred mode with automatic placement.
- `default/hypr/theme.lua`: applies the selected theme through native `hl.config()`.
- `default/hypr/bindings.lua`: registers Luna's basic keyboard shortcuts.
- `default/hypr/animations.lua`: sets animation timings and horizontal workspace slides.

## Load

Requires Hyprland 0.55 or newer with Lua configuration support.

Run the configuration step to deploy the config with GNU Stow:

```sh
bash scripts/setup/config.sh
```

Stow links into `$XDG_CONFIG_HOME/hypr/hyprland.lua` (normally `~/.config/hypr/hyprland.lua`). Conflicting files, directories, or symlinks are moved beside their original location with a `.luna-backup` suffix before replacement. Existing backups are preserved using numbered suffixes, such as `.luna-backup.1`. A matching symlink is reused. Other files in a real Hyprland directory are preserved; if the Hyprland directory itself is a symlink or a file, it is backed up first.

The source step links each whole directory under `src/` into `~/.local/src/`:

```sh
bash scripts/setup/src.sh
```

For example, `~/.local/src/luna-bar` points to the checkout's `src/luna-bar`. Whole-directory links preserve the source modules' relative paths back into the checkout. Matching links are reused, and conflicting paths are backed up and replaced using the same naming convention.

The main `scripts/setup.sh` installs core packages, main packages, and fonts without package-manager confirmations, then attempts to enable and start Docker. It deploys config/source links and installs `~/.local/bin/luna` automatically. Open a new terminal after setup so the shell uses that command path. Its final installation step asks whether to install the NVIDIA driver, then setup reloads the configuration in an active Hyprland session. Individual setup steps live under `scripts/setup/`.

The configuration entry point follows symlinks back to the checkout. If copying it instead, set `LUNA_PATH` to the checkout directory before starting Hyprland. To integrate with an existing Lua config, add this at the desired point in its load order, replacing the example checkout path:

```lua
local root = "/path/to/luna"
dofile(root .. "/default/hypr/bootstrap.lua")(root)
```

The entry point supplies theme appearance, animation defaults, and the shortcuts below. Put personal overrides after the bootstrap call.

## Animations

Windows animate in 200 ms, fades in 150 ms, layers in 180 ms, and workspaces in 220 ms. Other animations inherit a 250 ms default. Workspaces slide horizontally in the direction determined by workspace order.

## Multiple monitors

`default/hypr/workspaces.lua` divides workspaces 1–10 evenly into consecutive ranges across connected monitors, ordered left to right (then top to bottom for equal horizontal positions). Two monitors get 1–5 and 6–10; three get 1–4, 5–7, and 8–10. The 0 key still selects workspace 10. Extra workspaces from an uneven split go to the leftmost monitors. Mirrored outputs do not get a separate range.

Assignments update after startup, reload, hotplug, or monitor rearrangement, moving existing numbered workspaces with their windows. With one display, all ten belong to it. Named/special workspaces and numbers above 10 are unchanged.

New outputs use their preferred resolution and refresh rate, automatic placement, and scale 1. Monitor scaling belongs in your personal display configuration. Add output-specific `hl.monitor()` rules after bootstrap for a fixed arrangement.

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
