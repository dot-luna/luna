# Luna Wallpaper API

The [Lua API](src/api.lua) owns wallpaper config and renderer control. Load `lib/luna.lua` with the checkout path to use `luna.wallpaper`. Quickshell-specific QML, JS, and video components live in `src/shell/`; Lua app logic lives in `src/`.

| Method | Result / behavior |
| --- | --- |
| `getConfig(key?)` | Read the user file and return its resolved config, or a dotted key such as `wallpaper.source`. Missing keys return `nil` in Lua / `null` in QML. |
| `updateConfig(changes)` | Deep-merge a partial table into the user file and return the resolved config. |
| `getConfigFile()` | Return the absolute user config path, even if the file is missing or malformed. |
| `reload()` | Apply the file's current settings; start the renderer if needed. |
| `status()` | Return `stopped`, `loading`, `ready`, or `error` without starting the renderer. |
| `start()` | Start the renderer, reusing an existing instance. |
| `stop()` | Stop this wallpaper renderer and its media playback. Already stopped is a no-op; the config stays unchanged. |
| `restart()` | Replace this wallpaper renderer and read its config again. |

Config methods always read/edit the user file, whether the renderer is running or stopped. They never reload it. Call `reload()` explicitly to apply edits. Nested tables merge; arrays replace whole values. TOML comments and untouched fields survive edits. Tableshape validates the resolved config in Lua. Missing options use defaults; invalid known values fail reads and reject the entire update before writing. The renderer consumes this validated result and falls back to black on any error. Defaults come from [`apps/luna-wallpaper/config/wallpaper.toml`](../../apps/luna-wallpaper/config/wallpaper.toml), shared by setup, Lua, and QML. The default fit is `fill`. Reads and unrelated edits never copy missing defaults into the user file. Unknown fields are retained; `null` is invalid for known options; nulls in unrelated fields are left unchanged because TOML has no null value.

The file is `$LUNA_WALLPAPER_CONFIG`, otherwise `$XDG_CONFIG_HOME/luna/wallpaper.toml` (default `~/.config/luna/wallpaper.toml`). See [available options](config.toml). First installation copies the full defaults with the theme's media and background; later installs preserve that user file. Copied values remain overrides until removed. No old config formats are migrated.

Quickshell apps use `import Luna 1.0 as Luna` and the same methods on [Luna.Wallpaper](src/shell/Wallpaper.qml). Requests run in order and emit `completed(method, result)` or `failed(method, message)`. Bind to `busy`, `error`, `config`, `state`, and `configPath`. `config` is the last whole-config response; keyed reads return through `completed` without replacing it. Call a getter to refresh after manual edits. Importing the client starts no wallpaper process.

The [CLI](../luna-cli/wallpaper/README.md) prints the whole config and table/array values as JSON, scalar values as plain text, and missing keys as empty stdout. Lua returns values and QML emits results; neither prints the config automatically.

Shared merging, dotted lookup, paths, JSON, TOML, and Quickshell shutdown operations live in [`lib/`](../../lib/DOCS.md). Luna's separate media library is `luna.wallpapers` in `lib/wallpapers/`. The CLI combines both APIs; installation stays in `apps/` and `scripts/setup/`.
