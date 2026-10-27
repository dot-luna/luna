# Wallpapers

Use `luna w` as a short alias for `luna wallpaper` with any subcommand.

## Add

```sh
luna wallpaper add ~/Pictures/mountain.jpg ~/Pictures/forest.png
luna wallpaper add ~/Pictures/wallpapers
luna wallpaper add -r ~/Pictures/wallpapers
luna wallpaper add --force ~/Pictures/mountain.jpg
luna wallpaper add 'https://example.com/mountain.jpg' ~/Pictures/forest.png
```

- Supports local images, animated images, and videos; playback depends on Qt/mpv codecs.
- Copies media into one library; folders include subfolders only with `-r`.
- Skips identical files. Conflicting filenames require renaming or `--force`.
- Accepts multiple HTTP(S) URLs alongside local files and folders. Use direct image links.
- Uses curl, installing it through pacman if missing (sudo for normal users).
- Follows HTTP(S) redirects and validates downloaded bytes before copying the batch into the library.
- Uses URL filenames with the detected image extension; unnamed URLs use `wallpaper-<position>`. Temporary downloads are removed after success or failure.

## Select

```sh
luna wallpaper list
luna wallpaper set mountain.jpg
luna wallpaper set ~/Pictures/forest.png
luna wallpaper random
luna wallpaper get-config wallpaper.source
```

- Quickshell renders on the first available monitor using the TOML fit setting.
- Selection updates `[wallpaper].source` and reloads the renderer, preserving comments and other options. Failed loading restores the previous source.
- `random` avoids the current image when other images are available.
- `get-config wallpaper.source` prints the saved selection in any renderer state.

## Config

```sh
luna wallpaper get-config
luna wallpaper get-config wallpaper.fit
luna wallpaper get-config-file
luna wallpaper update-config '{"wallpaper":{"fit":"fill"}}'
luna wallpaper reload
luna wallpaper status
```

`get-config` reads the user file and prints the resolved config as JSON. A dotted key prints its value: scalars are plain text, tables/arrays are JSON, and missing keys produce empty stdout. `get-config-file` prints the absolute path.

`update-config` deep-merges the supplied JSON object directly into the user file and prints the resolved result. Nested tables merge; arrays replace. Both config operations work whether the renderer is running or stopped. Changes appear after an explicit `reload`. The API-name aliases `getConfig`, `updateConfig`, and `getConfigFile` are also available.

## Library

```sh
luna wallpaper dir
luna wallpaper open
luna wallpaper remove mountain.jpg forest.png
```

- `dir` prints `$XDG_DATA_HOME/luna/wallpapers`, defaulting to `~/.local/share/luna/wallpapers`.
- `open` creates the directory if needed and opens your default file explorer through `xdg-open`.
- Removal previews the batch and asks for confirmation. Select another wallpaper before removing the current image.
- External images are never deleted by `remove`. No ownership database is used.

## Startup

```sh
luna wallpaper start
luna wallpaper reload
luna wallpaper restart
luna wallpaper stop
```

- Add this command to your compositor's startup commands to restore the saved wallpaper on login.
- Repeated starts reuse Luna's running Quickshell instance.
- `stop` shuts down Luna's wallpaper renderer and its media playback, preserving the config. Calling it again is harmless.
- `reload` applies manual TOML edits in the running renderer; a stopped renderer starts first.
- `restart` rereads the config and replaces Luna wallpaper instances without stopping other Quickshell apps.
- Config: `$LUNA_WALLPAPER_CONFIG`, otherwise `$XDG_CONFIG_HOME/luna/wallpaper.toml` (default `~/.config/luna/wallpaper.toml`). See [available options](../../wallpaper/config.toml).
- Installation creates the initial user config from theme defaults.
- Requires Wayland layer shell, Quickshell, TOMLKit, `file`, and `ffmpeg`; videos also require `mpvpaper`. Library `open` uses `xdg-utils`.
