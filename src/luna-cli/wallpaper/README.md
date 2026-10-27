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
luna wallpaper current
```

- Quickshell renders on the first available monitor using the TOML fit setting.
- Selection is saved in `[wallpaper].source` after successful media loading, preserving comments and other options.
- `random` avoids the current image when other images are available.
- `current` prints the saved selection, even when the renderer is stopped.

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
luna wallpaper restart
```

- Add this command to your compositor's startup commands to restore the saved wallpaper on login.
- Repeated starts reuse Luna's running Quickshell instance.
- `restart` rereads the config and replaces old/new Luna wallpaper instances without stopping other Quickshell apps.
- Config: `$LUNA_WALLPAPER_CONFIG`, otherwise `$XDG_CONFIG_HOME/luna/wallpaper.toml` (default `~/.config/luna/wallpaper.toml`). See [available options](../../wallpaper/config.toml).
- Installation creates the user config. Standalone starts migrate the old `luna/wallpaper` selection only when TOML is absent.
- Requires Wayland layer shell, Quickshell, TOMLKit, `file`, and `ffmpeg`; videos also require `mpvpaper`. Library `open` uses `xdg-utils`.
