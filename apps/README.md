# App configurations

Step 10 (`scripts/setup/10-setup-app-configs.lua`) reads `apps/order.lua` and sets up
only the listed apps, in that order:

```lua
return {
    "kitty",
    "mpv",
    "luna-wallpaper",
    "luna-screensaver",
    "starship",
    "zsh",
    "zen",
    "hypr",
}
```

If an app depends on another app during setup, place that prerequisite first.
Zsh and Starship's config setup currently works in either order: Zsh reads the
Starship config when a shell starts. Add new apps to this list explicitly;
unlisted folders are ignored. Removing an entry skips setup and keeps any existing
installed files. Duplicate names and missing listed descriptors fail before setup
publishes files.

Each app has an `app.lua` descriptor and keeps native configuration in `config/`,
with optional templates outside it:

```text
kitty/
    app.lua
    build.lua
    config/kitty.conf
    templates/theme.conf
```

The descriptor declares what to copy and how to connect it:

```lua
return {
    config = "config",
    builder = "build.lua", -- Omit when the configuration is entirely static.
    connections = {
        {
            type = "kitty",
            source = "kitty.conf",
            target = "kitty/kitty.conf",
            directory_env = "KITTY_CONFIG_DIRECTORY",
        },
    },
}
```

Files from `config/` are copied to `$LUNA_CONFIG_DIR/<app>/`. Use native entry names
such as `kitty.conf`, `hyprland.lua`, or `userChrome.css`; each can include files
under `generated/`. Builders and templates remain in the checkout.

`build.lua` returns a function. Kitty's complete builder is:

```lua
return function(ctx)
    ctx.render("templates/theme.conf", "generated/theme.conf", ctx.theme())
end
```

A template contains ordinary native configuration with literal placeholders:

```conf
font_family {{fonts.mono}}
background {{colors.background}}
foreground {{colors.foreground}}
```

`ctx.render(template, output, values)` replaces dotted names from `values`; a
missing value fails the build. It does not evaluate expressions or escape values.
Quote values for their destination syntax when needed, as Zen's builder does for
CSS font names. `ctx.read(path)` reads an app-relative file and
`ctx.write(path, text)` writes a staged output. `ctx.theme()` loads Luna's resolved
theme lazily, so static configs do not depend on a selected theme.

The context also provides `root` (checkout), `source` (app folder), `output`
(temporary staging folder), `destination` (final app folder), and `config_dir`
(Luna's config store). Embed final paths in generated files, never `output`.
`ctx.quote(value)` quotes shell arguments; `ctx.warn(message)` reports optional
builder failures. Builders may generate local files, such as mise completions.

Connections are optional and may contain multiple entries. `source` is relative
to the installed app; `target` is relative to `$XDG_CONFIG_HOME`, or `$HOME` with
`base = "home"`. `directory_env` overrides the directory while retaining the
target filename; `file_env` overrides the whole target path.

| Type | Connection |
| --- | --- |
| `kitty` | Native `include`, preserving personal settings afterward. |
| `lua` | `dofile`; Hyprland also supports migration of Luna's old loader. |
| `shell` | A quoted `source` line, used by Zsh. |
| `mpv` | Managed defaults in native config and bindings files; respects `MPV_HOME` and legacy paths. |
| `zen` | Existing-profile discovery, CSS imports, and managed font/preferences in `user.js`. |
| `wallpaper` | Seed a missing personal TOML from the selected theme; preserve existing user settings. |
| `screensaver` | Seed a missing personal TOML with idle and renderer defaults; preserve existing user settings. |

Luna wallpaper defaults live in `apps/luna-wallpaper/config/wallpaper.toml`.
Setup creates `$XDG_CONFIG_HOME/luna/wallpaper.toml` (or `$LUNA_WALLPAPER_CONFIG`)
once. Later installs refresh
the defaults under `$LUNA_CONFIG_DIR/luna-wallpaper/` and keep the personal file.

Luna screensaver defaults live in `apps/luna-screensaver/config/screensaver.toml`.
Setup creates `$XDG_CONFIG_HOME/luna/screensaver.toml` (or
`$LUNA_SCREENSAVER_CONFIG`) only when missing. Later installs preserve it and refresh
the defaults under `$LUNA_CONFIG_DIR/luna-screensaver/`. These personal config paths
are independent of the installed app store. Neither app imports older formats.

mpv and Zen use their existing format-specific adapters without `source` or
`target` fields. Starship has no connection: Zsh selects its installed config
through `STARSHIP_CONFIG`. Optional `retired` paths name files owned by older Luna
layouts; setup removes those after successful installation and keeps other files.

All files for an app are staged and its connections checked before publishing.
Build failures leave that app's installed files intact. Required copy or connection
failures stop setup. Personal contents, permissions and ordinary symlinks are
preserved; conflicting directory links are rejected. Back up files you want to
keep first; setup creates no backups.

Refresh all configurations:

```sh
/usr/bin/lua -E /path/to/luna/scripts/setup/10-setup-app-configs.lua
```

Set `LUNA_SETUP_APP=kitty` to refresh one listed app; this does not install other
entries automatically. The older per-app `.sh` entry points are small compatibility
wrappers around the same installer.

Package installation, browser extension policies, downloads, service changes,
and session reloads belong in their separate setup steps. Zen extensions and
Better Find Bar run in step 14 (`app-extras`), which can be skipped independently.
