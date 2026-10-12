# Theme CLI

## Install

```sh
luna theme install /path/to/theme
luna theme install /path/to/theme --name my-theme
luna theme install /path/to/theme --force
luna theme install themes/bundled/tokyo-night
```

- Validates partial exports and their resolved defaults before installing a complete folder copy. `colors.lua` must exist but may return an empty table.
- Names default to the source folder name. Use lowercase letters, digits, hyphens, or underscores; start with a letter or digit.
- Existing themes require `--force`. Failed validation leaves the installed copy intact.
- Exports return literal tables; process and filesystem APIs are unavailable during evaluation.
- Declared wallpapers are imported automatically, including public HTTP(S) downloads. Conflicting wallpaper filenames fail rather than replacing unrelated library images.
- Font preferences are reported for manual installation. No font packages are installed.
- The source folder can be removed after installation.

## List and locate

```sh
luna theme list
luna theme path
luna theme path tokyo-night
```

- Installed copies: `$XDG_DATA_HOME/luna/themes`, defaulting to `~/.local/share/luna/themes`.
- `list` marks the selected theme with `*`; `path` prints the library or a named installed folder.

## Select

```sh
luna theme set tokyo-night
luna theme set tokyo-night --force
luna theme current
```

- Selection: `$XDG_CONFIG_HOME/luna/theme`, defaulting to `~/.config/luna/theme`.
- `set` merges the installed exports with shared defaults, validates the result, writes `~/.config/luna/theme.json` (respecting `$XDG_CONFIG_HOME`), applies the resolved `colors.mode`, and saves the selection.
- An unchanged selection and identical resolved output are skipped unless `--force` is supplied. Setting the same theme again rebuilds missing or changed output.
- Luna's [Hyprland config](../../../config/hypr/README.md) reads the generated JSON on its next startup or manual reload. Theme selection does not trigger a live reload or change the wallpaper.

After editing installed theme files, run `luna theme set <name>` again, then reload the consuming components. Existing selections from before JSON generation must be set again once. Luna Bar applies the resolved UI font family; terminal font integration remains separate.

## Light and dark mode

```sh
luna theme mode
luna theme mode dark
luna theme mode light
luna theme toggle
luna theme mode toggle
luna theme mode dark --force
```

- `mode` prints the effective light/dark preference. `toggle` switches it.
- Persists the desktop preference with GSettings and updates GTK 3/4's dark-theme preference, preserving unrelated settings.
- Also stores the selected mode in `$XDG_CONFIG_HOME/luna/theme-mode`, defaulting to `~/.config/luna/theme-mode`.
- Already-matching settings are skipped. `--force` rewrites them.
- Mode changes preserve the installed theme palette; selecting a theme again reapplies that theme's declared mode.
- Run in your user desktop session. Requires `glib2`, `gsettings-desktop-schemas`, and `dconf`, included in core dependencies.
- Apps following system appearance receive the preference through the desktop settings portal. On Hyprland, the installed GTK portal supplies these settings.
- App-specific appearance overrides may take precedence; some legacy apps need restarting to read GTK settings. This does not configure fixed Qt themes or rewrite application palettes.
- A failed change restores previous settings and leaves the selected theme and resolved output intact.

## Remove

```sh
luna theme remove tokyo-night other-theme
```

- Validates the batch, previews installed copies, and asks for confirmation.
- Select another theme before removing the current one.
- Source folders and imported wallpapers remain intact.

## Create a theme

See the [theme author guide](../../../themes/README.md) for shared defaults and partial exports.
