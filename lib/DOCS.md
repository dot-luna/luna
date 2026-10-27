# Shared Lua helpers

Config helpers contain no app-specific options. Load them with the checkout root:

```lua
local json = dofile(root .. "/lib/json.lua")
local config = dofile(root .. "/lib/config.lua")(json)
local toml = dofile(root .. "/lib/toml.lua")(dofile(root .. "/lib/common.lua"), json)

local path = config.path("luna/example.toml", "LUNA_EXAMPLE_CONFIG")
local resolved = config.merge(defaults, toml.read(path))
local value = config.get(resolved, "appearance.font")
toml.update(path, { appearance = { font = "Sans" } })
```

- [`config.lua`](config.lua): `merge(base, overrides)` recursively merges objects and replaces arrays/scalars without mutating inputs. Themes, wallpaper, and screensaver use it for defaults. `get(document, key?)` reads dotted table keys; `isObject(value)` distinguishes tables from arrays/null. `path(relative, env?)` resolves an absolute user config path from the override, XDG, or HOME. `format(value, "json" | "text")` formats API/CLI output; text mode prints missing values as empty strings.
- [`toml.lua`](toml.lua): `read(path)` reads the file each time; a missing file returns an empty table. `update(path, changes, options?)` deep-merges into the file with TOMLKit, preserving comments and untouched options. Arrays replace; null and empty patches leave values unchanged. Writes are atomic, preserve permissions, and follow personal symlinks. Set `options.protectedRoot` to forbid edits inside a checkout. `options.validate` accepts a command argument array: the command receives the merged document as JSON on stdin, and must exit successfully before any write. No operation starts or reloads an app.
- [`json.lua`](json.lua): `encode`, `decode`, `null`, and `array`. Decoded empty arrays and objects retain their shape. Use `json.array({})` for an empty Lua array; an ordinary `{}` means an object.

Apps supply their own defaults and validation schemas. Pure Lua merging resolves effective settings; TOMLKit merges file edits separately so comments and TOML-only data remain intact. TOML dates and nonfinite numbers are returned as null through the JSON transport, while their file contents remain unchanged.

[`validation.lua`](validation.lua) exposes the bundled [Tableshape 2.7.0](vendor/tableshape/README.md) as `types`, plus `object(fields)` for open object schemas that reject JSON arrays and null. No separate dependency installation is needed. Use Tableshape directly for enums, ranges, optional fields, and nested schemas:

```lua
local validation = dofile(root .. "/lib/validation.lua")(root)
local types = validation.types
local schema = validation.object({
    appearance = validation.object({
        mode = types.one_of({ "light", "dark" }),
        font = types.string:is_optional(),
    }),
})
assert(schema:check_value(resolved))
```

Validation reports an error; it never filters invalid fields, changes values, or writes files. Wallpaper and screensaver validate the merged result before saving a partial update.

[`quickshell.lua`](quickshell.lua) shares app lifecycle operations. Load it with `(common, root, renderer, ipcTarget, label)` and call `stop()` to stop all instances of that renderer and wait for shutdown. `renderer` accepts a QML file or directory, including symlinks; `path()` resolves the canonical filename used by startup, IPC, and shutdown. Stopping is repeatable and needs neither a valid theme nor a Wayland connection. Wallpaper and the themed shell commands use this Lua helper; stopping requires only Quickshell and coreutils.

[`luna.lua`](luna.lua) exposes application APIs through `luna.wallpaper` and
`luna.screensaver`, each with `getConfig`, `updateConfig`, `getConfigFile`, and
explicit lifecycle operations. Their CLI and QML clients call the same API.
Screensaver also exposes `install`, `list`, `set`, `removalPlan`, `remove`, and
`getDirectory` for its shell library, and controls visibility and Stay awake. Its
separate controller remains responsible for idle actions while custom shells render.
See the [wallpaper](../src/wallpaper/DOCS.md) and
[screensaver](../src/screensaver/DOCS.md) API documentation.
