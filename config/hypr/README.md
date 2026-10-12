# Hyprland

## Layout

- `config/hypr/.config/hypr/hyprland.lua`: Stow-managed entry point and place for personal overrides.
- `default/hypr/bootstrap.lua`: loads reusable Luna defaults.
- `default/hypr/theme.lua`: applies the selected theme through native `hl.config()`.
- `default/hypr/bindings.lua`: registers Luna's basic keyboard shortcuts.

## Load

Requires Hyprland 0.55 or newer with Lua configuration support.

- Run the setup script to deploy the config with GNU Stow:

```sh
bash scripts/setup-config.sh
```

- Use `--force` to remove a conflicting old Hyprland entry point before Stowing Luna's file.
- The main `setup.sh` runs this step after package installation.
- Stow links into `$XDG_CONFIG_HOME/hypr/hyprland.lua` (normally `~/.config/hypr/hyprland.lua`). Other files in the existing Hyprland directory are preserved.
- The entry point follows symlinks back to the checkout. If copying it instead, set `LUNA_PATH` to the checkout directory before starting Hyprland.
- To integrate with an existing Lua config, add this at the desired point in its load order, replacing the example checkout path:

```lua
local root = "/path/to/luna"
dofile(root .. "/default/hypr/bootstrap.lua")(root)
```

The entry point supplies theme appearance and the shortcuts below. Put personal overrides after the bootstrap call.

## Keybindings

| Shortcut | Action |
| --- | --- |
| Super + Return | Open Kitty |
| Super + Shift + Return | Open Zen |
| Super + W | Close the active window |
| Super + 1–9 | Switch to workspace 1–9 |
| Super + 0 | Switch to workspace 10 |
| Super + Ctrl + B | Focus Luna Bar |
| Super + Ctrl + Space | Toggle the control center |

## Theme behavior

- Reads `$XDG_CONFIG_HOME/luna/theme`, with the normal `~/.config` fallback.
- Loads the installed theme from `$XDG_DATA_HOME/luna/themes`, with the normal `~/.local/share` fallback.
- Maps `accent` and `muted` to active and inactive borders.
- Applies the optional `hyprland.lua` settings directly and derives shadow colors from background tokens.
- No selected theme leaves Hyprland's other settings intact. Invalid or missing selected themes report a config error.
- Theme exports are validated with the same rules used by `luna theme install`.
- No generated config files or automatic live reloads are used.

```sh
luna theme set tokyo-night
hyprctl reload
```

Reload manually when you want the newly selected appearance applied. The adapter does not install fonts or select a wallpaper.
