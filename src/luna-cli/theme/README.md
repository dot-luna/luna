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
luna theme current
```

- Selection: `$XDG_CONFIG_HOME/luna/theme`, defaulting to `~/.config/luna/theme`.
- `set` validates the installed export and saves its name. It does not generate configs, reload applications, or change the wallpaper.

## Remove

```sh
luna theme remove tokyo-night other-theme
```

- Validates the batch, previews installed copies, and asks for confirmation.
- Select another theme before removing the current one.
- Source folders and imported wallpapers remain intact.

## Create a theme

See the [theme author guide](../../../themes/README.md) for required fields and optional exports.
