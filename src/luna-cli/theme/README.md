# Theme CLI

## Install

```sh
luna theme install /path/to/theme
luna theme install /path/to/theme --name my-theme
luna theme install /path/to/theme --force
luna theme install themes/bundled/tokyo-night
```

- Validates required colors and optional exports before installing a complete folder copy.
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
- `set` validates the installed export, applies its `colors.mode` as the system appearance preference, and saves its name.
- Matching settings and an unchanged selection are skipped unless `--force` is supplied.
- Luna's [Hyprland config](../../../config/hypr/README.md) reads the selected theme on its next startup or manual reload. Theme selection does not trigger a live reload or change the wallpaper.

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
- A failed change restores previous settings and leaves the selected theme intact.

## Remove

```sh
luna theme remove tokyo-night other-theme
```

- Validates the batch, previews installed copies, and asks for confirmation.
- Select another theme before removing the current one.
- Source folders and imported wallpapers remain intact.

## Create a theme

See the [theme author guide](../../../themes/README.md) for required fields and optional exports.
