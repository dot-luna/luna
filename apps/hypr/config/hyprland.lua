-- Luna's installed Hyprland entry point. Personal settings follow its dofile call.
-- Settings after that include in your personal hyprland.lua can override these defaults.

-- Resolve the physical entry so symlinks and alternate working directories load
-- sibling configuration modules from the same installed application directory.
local source = debug.getinfo(1, "S").source
assert(source:sub(1, 1) == "@", "Load Luna's Hyprland entry from a file")

-- Shell quoting keeps spaces and apostrophes in the config path intact for readlink.
local quoted = "'" .. source:sub(2):gsub("'", "'\\''") .. "'"
local pipe = assert(io.popen("readlink -f -- " .. quoted, "r"))
local path = pipe:read("*a")
-- Hyprland can reap subprocesses before pclose; trust the resolved output instead.
pipe:close()
local config_dir = assert(path:gsub("\n$", ""):match("^(.*)/[^/]+$"),
    "Cannot locate Luna's installed Hyprland configuration")

-- Setup records the actual checkout here so shared libraries and commands still
-- resolve when Luna is installed somewhere other than its usual location.
local paths = dofile(config_dir .. "/generated/paths.lua")
assert(type(paths) == "table" and type(paths.install_dir) == "string"
    and paths.install_dir:sub(1, 1) == "/", "Regenerate Luna's Hyprland configuration with setup")
local root = paths.install_dir

-- Explicit ordering keeps dependencies visible. dofile reloads each module and
-- the selected theme snapshot on every configuration load.
-- Set fallback display modes, positions and scaling before workspace assignment.
dofile(config_dir .. "/monitors.lua")

-- Register automatic workspace redistribution for startup and monitor changes.
dofile(config_dir .. "/workspaces.lua")

-- Configure keyboard repeat, touchpad behavior, split preservation and gestures.
dofile(config_dir .. "/input.lua")

-- Read Luna's selected theme through the shared resolver, then apply its
-- Hyprland settings and palette before the remaining desktop rules are loaded.
local resolved = dofile(root .. "/lib/theme/resolved.lua")(root)
local theme = dofile(config_dir .. "/theme.lua")(resolved)
theme.apply()

-- Place special windows and apply effects to Luna's layer-shell surfaces.
dofile(config_dir .. "/rules.lua")

-- Apply the shared easing curve and durations for windows, panels and workspaces.
dofile(config_dir .. "/animations.lua")

-- Use the checkout launcher so shell shortcuts also work before bin is on PATH.
local launcher = "'" .. (root .. "/bin/luna"):gsub("'", "'\\''") .. "'"

-- Register services to start with the session; a config reload does not restart them.
dofile(config_dir .. "/autostart.lua")(launcher)

-- Register all shortcut groups after their supporting settings and rules are ready.
dofile(config_dir .. "/bindings.lua")(config_dir, launcher)
