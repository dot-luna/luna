# Create a Luna theme

## Files

Your theme folder can live anywhere. Each export is a Lua file returning a table. Theme values are shared across components wherever supported; each component uses the settings it understands.

```text
my-theme/
├── colors.lua      Required
├── hyprland.lua    Optional
├── fonts.lua       Optional
└── wallpaper.lua   Optional
```

| Export | Provides | Installation |
| --- | --- | --- |
| `colors.lua` | Shared colors and light/dark mode | Values consumed by applications |
| `hyprland.lua` | Compositor appearance and shared visual settings | Applied to Hyprland and reused by supporting components |
| `fonts.lua` | Font families | Fonts must be installed manually |
| `wallpaper.lua` | Local images, directories, and public image URLs | Images will be imported or downloaded automatically |

`luna theme install /path/to/my-theme` validates and copies a theme, importing its wallpapers automatically. `luna theme set my-theme` merges the theme with shared defaults, writes the resolved JSON, saves the selection, and applies its light/dark system preference. Luna's [Hyprland config](../config/hypr/README.md) reads the resolved JSON at startup or on a manual reload. See the [theme CLI guide](../src/luna-cli/theme/README.md).

## Theme file rules

- Return tables containing values; do not run commands or modify files.
- `colors.lua` is required, but it may return an empty table. Every documented field is optional.
- Keep names consistent across themes. Different roles can share the same value.
- Omitted fields inherit shared defaults. Nested tables merge field by field; wallpaper source lists replace the default list.
- Exports are evaluated without process or filesystem APIs and must return declarative tables.
- Font names select preferences, not packages. Install the fonts yourself, for example with `luna font install`.

## Shared defaults and generated output

[Shared defaults](../lib/theme/defaults.lua) use Tokyo Night colors, fonts, and Hyprland appearance. Partial themes declaring `mode = "light"` use the [light palette](../lib/theme/light.lua) instead of inheriting dark surfaces.

For example, this is a valid `colors.lua`:

```lua
return {
    accent = "#82aaff",
}
```

`luna theme set <name>` writes `$XDG_CONFIG_HOME/luna/theme.json` (normally `~/.config/luna/theme.json`). It contains `version`, `name`, and complete `colors`, `fonts`, `hyprland`, and `wallpaper` sections. Font sizes, display settings, and component layout remain outside the theme. Luna Bar applies the resolved UI font family. Kitty's setup generator reads this same resolved theme and personal font preferences to produce its colors and monospace font family.

Setup writes Kitty's static `kitty.conf` and generated `theme.conf` under `$LUNA_CONFIG_DIR/kitty` (normally `~/.config/luna/kitty`). Run `bash /path/to/luna/scripts/setup/apps.sh` to regenerate them after changing themes or font preferences. Setup prepends an include to the active Kitty config if missing, preserving existing contents so personal settings can override Luna's defaults. It does not reload Kitty; theme selection alone does not regenerate these files.

Edit the installed Lua source files, then run `luna theme set <name>` again to rebuild the JSON. Reinstall first if editing the original source folder. Components read this same output when started or reloaded; they do not independently merge defaults or reread source files. Existing selections without JSON must be set again once. The output is generated data, not a user configuration file.

Theme selection does not reload components automatically. The UI uses resolved Tokyo Night defaults in memory when no theme is selected; Hyprland leaves its settings untouched until a theme is selected. Toggling system light/dark preference does not rewrite the resolved palette.

## colors.lua: base fields

`mode` is `"dark"` or `"light"`, defaulting to `"dark"`. Every other color field is an opaque `"#RRGGBB"` string.

| Field | Role |
| --- | --- |
| `mode` | Theme appearance mode |
| `accent` | Main accent color, including filled highlights |
| `accent_foreground` | Text and icons on an accent fill |
| `selection` | Selected-content background |
| `selection_foreground` | Text and icons on selection |
| `muted` | Subdued fills and decoration; not secondary text |
| `background` | Default application background |
| `dark_background` | Darker background surfaces |
| `darker_background` | Deepest background surfaces |
| `lighter_background` | Raised or lighter surfaces |
| `foreground` | Default readable text and icons |
| `dark_foreground` | Disabled or decorative elements; not ordinary secondary text |
| `light_foreground` | Lighter readable text and icons |
| `bright_foreground` | Strong text emphasis; also text on muted fills |

This example explicitly supplies the base colors. Supply only the fields you want to override.

Selecting a theme applies its `mode` to desktop apps following the system appearance preference. `luna theme toggle` changes that preference without altering these exported colors.

```lua
return {
    mode = "dark",

    accent = "#7aa2f7",
    accent_foreground = "#1a1b26",
    selection = "#292e42",
    selection_foreground = "#c0caf5",
    muted = "#414868",

    background = "#1a1b26",
    dark_background = "#13141c",
    darker_background = "#0e0e14",
    lighter_background = "#24283b",

    foreground = "#a9b1d6",
    dark_foreground = "#565f89",
    light_foreground = "#b4bee6",
    bright_foreground = "#c0caf5",
}
```

## colors.lua: additional fields

Add optional fields to the same flat table. All use the same `"#RRGGBB"` format.

| Field | Role |
| --- | --- |
| `secondary_accent` | Supporting accent color or fill |
| `secondary_accent_foreground` | Text and icons on a secondary accent fill |
| `link` | Link text and icons |
| `comment` | Readable code comments |
| `error` | Failures and errors |
| `error_foreground` | Text and icons on an error fill |
| `warning` | Potential problems requiring attention |
| `warning_foreground` | Text and icons on a warning fill |
| `notice` | Attention-worthy notices without warning severity |
| `notice_foreground` | Text and icons on a notice fill |
| `success` | Successful actions and positive states |
| `success_foreground` | Text and icons on a success fill |
| `info` | Informational states |
| `info_foreground` | Text and icons on an informational fill |
| `error_emphasis` | Stronger error color |
| `warning_emphasis` | Stronger warning color |
| `success_emphasis` | Stronger success color |
| `info_emphasis` | Stronger informational color |
| `link_emphasis` | Stronger link text or icon color |
| `secondary_accent_emphasis` | Stronger supporting accent color |

- Status colors can color text or icons on a normal background.
- When a fill is overridden without its matching `_foreground`, Luna chooses black or white for readable text. Explicit foregrounds are preserved.
- Emphasis means visual intensity, not necessarily greater brightness.
- Filled emphasis variants reuse their base role's foreground. Overriding a base role without its emphasis variant makes the variant follow that base color. Check explicit emphasis colors against the foreground.
- Links remain text or icon colors; they do not need a paired foreground.

See [Tokyo Night's complete color export](bundled/tokyo-night/colors.lua).

## hyprland.lua

Return a nested table using Hyprland's setting sections. Every section and field is optional.

`general` and `decoration` are tables; `decoration.blur` and `decoration.shadow` are nested tables.

| Field path | Type / units | Role |
| --- | --- | --- |
| `general.gaps_in` | Nonnegative integer, layout pixels | Space between windows |
| `general.gaps_out` | Nonnegative integer, layout pixels | Space between windows and screen edges |
| `general.border_size` | Nonnegative integer, layout pixels | Window border thickness |
| `decoration.rounding` | Integer, 0–100 layout pixels | Window corner radius |
| `decoration.active_opacity` | Number, 0–1 | Focused window opacity |
| `decoration.inactive_opacity` | Number, 0–1 | Unfocused window opacity |
| `decoration.fullscreen_opacity` | Number, 0–1 | Fullscreen window opacity |
| `decoration.blur.enabled` | Boolean | Enable background blur |
| `decoration.blur.size` | Positive integer | Blur size |
| `decoration.blur.passes` | Integer, 1–10 | Blur passes; more increases GPU work |
| `decoration.shadow.enabled` | Boolean | Enable window shadows |
| `decoration.shadow.range` | Integer, 0–100 pixels | Shadow extent |
| `decoration.shadow.render_power` | Integer, 1–4 | Shadow falloff strength |

```lua
return {
    general = {
        gaps_in = 5,
        gaps_out = 5,
        border_size = 1,
    },

    decoration = {
        rounding = 0,
        active_opacity = 0.90,
        inactive_opacity = 0.85,
        fullscreen_opacity = 1,

        blur = {
            enabled = true,
            size = 10,
            passes = 3,
        },

        shadow = {
            enabled = true,
            range = 12,
            render_power = 3,
        },
    },
}
```

Keep monitor scaling, inactive-window dimming, keybindings, input behavior, and window rules in the user's Hyprland configuration. This table declares appearance values; it is not a standalone Hyprland configuration.

The adapter derives active and inactive border colors from `accent` and `muted`. When shadow settings are supplied, it derives shadow colors from `dark_background` and `darker_background`. The Hyprland adapter applies theme settings with `hl.config()`. Supporting components can reuse appearance values such as rounding and opacity from this table. Personal Hyprland overrides remain separate from the shared theme values.

See [Tokyo Night's Hyprland export](bundled/tokyo-night/hyprland.lua).

## fonts.lua

Every field is optional. Use font family names recognized by Fontconfig.

| Field | Type / units | Role |
| --- | --- | --- |
| `ui` | String | Interface font family |
| `mono` | String | Terminal and code font family |

```lua
return {
    ui = "Outfit",
    mono = "Iosevka Nerd Font",
}
```

Fonts must be installed manually. Applying a theme will not install font packages or files. Luna's interface uses SVG icons and does not require an icon font. Font sizes, application padding, and layout belong in user/application configuration, outside the theme.

See [Tokyo Night's font export](bundled/tokyo-night/fonts.lua).

## wallpaper.lua

| Field | Type | Role |
| --- | --- | --- |
| `sources` | Optional ordered list of strings | Local image paths, directories, or public direct image URLs |

```lua
return {
    sources = {
        "wallpapers",
        "images/night.png",
        "https://example.com/mountain.jpg",
    },
}
```

- Local paths are relative to the theme folder, regardless of where it lives or where commands run.
- A directory supplies its supported image files without scanning subdirectories recursively.
- Files, directories, and URLs can be mixed. Omit `sources` or use an empty list to supply no wallpapers.
- Supported formats: PNG, JPEG, WebP, BMP, and SVG.
- URLs must be public HTTP(S) direct image links requiring no authentication. Gallery pages are not image sources.
- `luna theme install` copies local images and downloads URL images into Luna's wallpaper library automatically.
- Conflicting filenames fail without replacing unrelated wallpapers. Rename conflicting images before installing.
- Importing wallpapers does not select or display one; use `luna wallpaper set` separately.

See [Tokyo Night's wallpaper export](bundled/tokyo-night/wallpaper.lua).

## Check your theme

- Check every Lua export with `luac -p`.
- Check ordinary text, links, and comments against their actual backgrounds; aim for at least 4.5:1 contrast.
- Check every fill/foreground pair, including emphasis variants.
- Keep low-contrast decoration separate from readable text.
- Confirm local wallpaper paths exist and URL sources return supported images.
- Confirm your selected font families are installed.

```sh
luac -p /path/to/my-theme/colors.lua
luac -p /path/to/my-theme/hyprland.lua
luac -p /path/to/my-theme/fonts.lua
luac -p /path/to/my-theme/wallpaper.lua
```

Run checks only for the files your theme supplies.
