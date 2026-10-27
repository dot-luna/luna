# Luna Screensaver

The controller owns idle timers, Stay awake, display power, and renderer lifecycle.
A separate QML process provides the visuals. Luna's bundled clock and custom
renderers use the same surface and session helpers. A renderer failure leaves the
controller and automatic lock timer running.

## Structure

| Path | Responsibility |
| --- | --- |
| `src/api.lua` | Public Lua API, validated config, and controller operations. |
| `src/library.lua` | Named shell installation, selection, and removal. |
| `src/shell/controller.qml` | Persistent idle controller and IPC endpoint. |
| `src/shell/shell.qml` | Bundled clock renderer, running only while visible. |
| `src/shell/` | Quickshell client, session, and surface components. |
| `examples/blank/shell.qml` | Black fullscreen renderer. |
| `examples/orbit/shell.qml` | Custom renderer example using theme tokens and settings. |
| `../../apps/luna-screensaver/` | Shared defaults and installation descriptor. |
| `../luna-cli/screensaver/` | CLI adapter to the public API. |

## Configuration

The personal file is `$LUNA_SCREENSAVER_CONFIG`, otherwise
`$XDG_CONFIG_HOME/luna/screensaver.toml` (normally
`~/.config/luna/screensaver.toml`). Overrides must be absolute paths. Runtime config
is independent of `LUNA_CONFIG_DIR`, which selects the installed app config store.

```toml
[idle]
screensaver_seconds = 300
lock_seconds = 600
display_off_seconds = 0

[renderer]
shell = ""

[settings]
```

Each timer accepts whole seconds from `0` to `86400`; zero disables only that
automatic action. The delays measure inactivity independently, rather than adding
one delay after another. Wayland idle inhibitors, such as those requested by media
players, pause automatic actions. Stay awake pauses automatic actions without
changing the saved delays. Manual screensaver, lock, suspend, and hibernate remain
available.

An empty `renderer.shell` selects the bundled clock. To supply a custom shell, use
an absolute filename or a `~/` path ending in `.qml`. `[settings]` contains options
defined by that renderer. A black renderer draws black surfaces while keeping
displays on; `idle.display_off_seconds` powers the displays off instead.

Defaults come from
[`apps/luna-screensaver/config/screensaver.toml`](../../apps/luna-screensaver/config/screensaver.toml).
Setup copies them to a missing personal file once. Later installs refresh the
installed defaults and preserve the personal file, including unfinished edits,
permissions, and ordinary symlinks. No old `idle.json` settings are read or migrated.

Reads merge missing options from defaults without writing them into the personal
file. Updates deep-merge tables and replace arrays, preserving TOML comments and
untouched fields. Invalid known values reject the whole update before writing;
unknown fields remain available to custom renderers. Reading or changing config
does not start or reload the controller. Apply changes with an explicit `reload()`
or `luna screensaver reload`. Reload preserves Stay awake; restart resets it.

## Commands

```sh
luna screensaver                     # Show now; start the controller if needed.
luna screensaver install ./my-clock  # Copy a directory containing shell.qml.
luna screensaver list
luna screensaver set my-clock        # Select and apply without showing when idle.
luna screensaver set clock           # Restore the bundled clock.
luna screensaver remove my-clock     # Preview and confirm removal.
luna screensaver dir
luna screensaver start               # Start the hidden idle controller.
luna screensaver hide
luna screensaver stop
luna screensaver restart
luna screensaver reload
luna screensaver status
luna screensaver state
luna screensaver get-config
luna screensaver get-config idle.lock_seconds
luna screensaver get-config-file
luna screensaver update-config '{"idle":{"screensaver_seconds":300}}'
luna screensaver reload
```

`show` is also available explicitly. `getConfig`, `updateConfig`, and `getConfigFile`
are accepted spellings of the corresponding config commands, matching wallpaper.
Config objects and state print JSON; scalar values print plain text and missing
keys produce empty stdout. `status` returns `stopped`, `idle`, `loading`, `showing`,
or `error`. State includes `running`, `active`, `stayAwake`, `outputsOff`,
`rendererState`, and `error`. `rendererState` is `hidden`, `loading`, `ready`, or
`error`; it describes the rendering process separately from the idle controller.

The existing idle and Stay awake controls use the same API:

```sh
luna idle set screensaver 300
luna idle set lock 600
luna idle set display 900
luna idle status
luna awake on
luna awake off
luna awake toggle
luna awake status
```

`luna idle set` saves and applies one timer. `luna awake status` (or `luna awake`)
returns `{"enabled":true}` or `{"enabled":false}`. Stay awake is shared with the
Luna menu and control center and resets on stop, restart, or logout.

Hyprland runs `luna screensaver start` at session startup. Reloading Hyprland config
does not rerun the startup hook. Run it manually to start the controller in an
existing session.

## Shell library

Keep any number of shells installed and select one at a time, like wallpaper:

```sh
luna screensaver install ./my-clock
luna screensaver install ./aurora.qml --name aurora
luna screensaver list
luna screensaver set aurora
luna screensaver set blank
luna screensaver set orbit
luna screensaver set clock
luna screensaver remove my-clock aurora
```

The library lives at `$XDG_DATA_HOME/luna/screensavers`, normally
`~/.local/share/luna/screensavers`. `dir` prints the absolute directory. Installing
a directory copies its `shell.qml` and supporting files, excluding `.git`. Packages
must contain regular files and directories; symlinks and special files are rejected.
Installing a standalone `.qml` file copies only that file as `shell.qml`; install
the containing package directory when it uses local components or assets. The
source stays untouched, and Luna renders the installed copy. Use relative asset
paths within packages so they remain usable after copying.

`--name` chooses the installed name; otherwise Luna uses the source directory name
or the QML filename without its extension. A file named `shell.qml` uses its parent
directory's name. Names begin with a letter or number and may also contain dots,
underscores, and hyphens. `install` neither selects the shell
nor starts or reloads the controller. `--force` replaces an existing inactive
package. Luna protects the saved selection and the controller's currently applied
package from replacement or removal, including after unapplied config edits.
The bundled names `clock`, `blank`, and `orbit` are always available and cannot be
overwritten or removed. `list` marks the selected installed or bundled shell with `*`.

`set NAME_OR_QML_PATH` saves the selection and reloads the controller, starting it
if needed. It preserves Stay awake and a visible screensaver remains visible; an
idle controller stays hidden. If applying fails, Luna restores the previous
selection and attempts to reload it. Direct paths let you develop a shell without
installing a copy. Settings remain in the shared `[settings]` config table;
installing or selecting a shell does not change them.

`remove NAME...` validates the full selection before asking for confirmation.
Use `-y` or `--yes` to skip the prompt in scripts. Removal deletes only installed
copies; use `set` to choose and apply another shell first if the package is protected.

## Lua API

```lua
local luna = dofile(root .. "/lib/luna.lua")(root)

local config = luna.screensaver.getConfig()
luna.screensaver.install("/path/to/my-clock", { name = "my-clock" })
luna.screensaver.set("my-clock")
luna.screensaver.updateConfig({ idle = { lock_seconds = 600 } })
luna.screensaver.reload()
```

| Method | Behavior |
| --- | --- |
| `install(source, options?)` | Copy a local package directory or QML file and return its entry. Options: `name`, `force`. Does not select or reload. |
| `list()` | Return bundled and installed entries with `name`, `path`, `bundled`, and `current`. |
| `set(nameOrPath)` | Select and apply a shell, returning its entry. Restore the previous selection if applying fails. |
| `removalPlan(names)` | Validate a list of installed names and return their entries without removing anything. |
| `remove(names)` | Validate and remove installed packages; return the removed names. No interactive prompt. |
| `getDirectory()` | Return the absolute library directory without creating it. |
| `getConfig(key?)` | Read resolved settings or a dotted key, such as `idle.lock_seconds`; a missing key returns `nil`. |
| `updateConfig(changes)` | Save a partial table and return the resolved config. |
| `getConfigFile()` | Return the absolute personal path, even when the file is missing or malformed. |
| `start()` | Start the hidden idle controller, reusing an existing instance. |
| `stop()` | Stop the controller and its renderer; already stopped is a no-op. |
| `restart()` | Replace the controller, start hidden, and reset Stay awake. |
| `reload()` | Apply current config, starting if needed and preserving Stay awake in an existing controller. |
| `status()` | Return lifecycle status without starting anything. |
| `getState()` | Read the current controller state without starting anything. |
| `show()` | Start if needed and display the configured renderer. |
| `hide()` | Dismiss the renderer without starting a stopped controller. |
| `setStayAwake(enabled)` | Start if needed, set a boolean Stay awake value, and return the state. |
| `toggleStayAwake()` | Start if needed, toggle Stay awake, and return the state. |

Lifecycle, show, and hide methods return no value. Config validation and
persistence follow wallpaper's API, using shared [`lib/` helpers](../../lib/DOCS.md).
Luna's compositor idle monitor runs in the controller; no Hypridle daemon is required.

## QML client

Use `import Luna 1.0 as Luna` and the same methods on `Luna.Screensaver`.
Requests run in order and emit `completed(method, result)` or
`failed(method, message)`. Importing the singleton starts no screensaver process.
Library operations use the same names and arguments, for example
`Luna.Screensaver.install("/path/to/my-clock", { name: "my-clock" })` and
`Luna.Screensaver.set("my-clock")`. Only the CLI provides removal confirmation;
QML callers should confirm before calling `remove(["my-clock"])`.

Bind to `busy`, `error`, `config`, `configPath`, `state`, and `stateData`.
`config` holds the last whole-config response; keyed reads emit their result
without replacing it. `state` holds lifecycle status, initially `unknown`;
`stateData` holds a controller snapshot, initially `null`. Convenience properties
`active` and `stayAwake` are false until a snapshot is available. Use `getState()`
to refresh; Stay awake operations also update the snapshot. Start, restart, reload,
show, and hide invalidate the old snapshot rather than assuming the renderer is
ready. A successful stop records the stopped state.

`list()` updates the cached `library` array and `getDirectory()` updates
`libraryPath`. Installing or removing a shell invalidates `library`; changing
config does too because it may change the selected entry. `set()` invalidates
`library`, `config`, and the controller state snapshot. Read these again when your
UI needs fresh values. Failed requests preserve the last successful snapshots.

## Custom rendering shells

Copy one of the example shells to a personal directory, then select its path:

```sh
luna screensaver set ~/.config/luna/screensavers/my-clock/shell.qml
luna screensaver show
```

Use `install DIRECTORY` and `set NAME` when you want an independent library copy.

The entry point is a complete Quickshell shell. It owns layout and visual effects;
Luna supplies import paths, the resolved theme, and the current config snapshot.
Create one `Luna.ScreensaverSurface` per screen:

```qml
import QtQuick
import Quickshell
import Luna 1.0 as Luna

ShellRoot {
    Variants {
        model: Quickshell.screens

        Luna.ScreensaverSurface {
            id: surface
            required property var modelData
            screen: modelData

            Text {
                anchors.centerIn: parent
                text: surface.settings.message || ""
                color: Luna.Theme.foreground
                font.family: Luna.Theme.uiFont
            }
        }
    }
}
```

The helper creates fullscreen surfaces, hides the cursor, handles keyboard and
mouse dismissal, selects keyboard focus, and reports renderer readiness. Its
default children are visual content. It exposes `settings`, `outputActive`, and
`renderingActive`; bind animation and timer `running` properties to
`surface.renderingActive`. The renderer is unloaded when hidden, and inactive
outputs should not spend resources animating. Read colors, fonts, borders, and
rounding from `Luna.Theme`, just as in other Luna shells.

For custom window handling, `Luna.ScreensaverSession` exposes `config`, `settings`,
`managed`, and `focusedScreen`, plus `ready()` and `dismiss()`. Report readiness
only after your surfaces are present, and route wake input to `dismiss()`. The
session helper requires the managed environment supplied by the controller; it
does not start a controller itself. Prefer `ScreensaverSurface` unless you need
to implement window and input handling yourself.

The controller launches renderers only while requested and remains alive if one
fails. Check `luna screensaver state` for useful error details. Selecting a new
shell with `set` applies it immediately. Editing its settings through the config
requires `reload`; changes never rewrite the shell.
Changing Luna's font preferences refreshes a visible renderer with the new theme
snapshot. This restarts that rendering process while preserving the controller
and Stay awake state.

## Locking

The screensaver is a visual overlay, not authentication. Automatic locking calls
`luna lock`, which uses Hyprlock. Dismissing a screensaver never unlocks a locked
session. Rendering custom content does not replace the lock or its password flow.
