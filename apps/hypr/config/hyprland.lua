-- Luna's installed Hyprland entry point. Personal settings follow its dofile call.
-- Resolve the physical entry so symlinks and alternate working directories load
-- sibling configuration modules from the same installed application directory.
local source = debug.getinfo(1, "S").source
assert(source:sub(1, 1) == "@", "Load Luna's Hyprland entry from a file")
local quoted = "'" .. source:sub(2):gsub("'", "'\\''") .. "'"
local pipe = assert(io.popen("readlink -f -- " .. quoted, "r"))
local path = pipe:read("*a")
-- Hyprland can reap subprocesses before pclose; trust the resolved output instead.
pipe:close()
local config_dir = assert(path:gsub("\n$", ""):match("^(.*)/[^/]+$"),
    "Cannot locate Luna's installed Hyprland configuration")
local paths = dofile(config_dir .. "/generated/paths.lua")
assert(type(paths) == "table" and type(paths.install_dir) == "string"
    and paths.install_dir:sub(1, 1) == "/", "Regenerate Luna's Hyprland configuration with setup")
local root = paths.install_dir

-- Explicit ordering keeps dependencies visible. dofile reloads each module and
-- the selected theme snapshot on every configuration load.
dofile(config_dir .. "/monitors.lua")
dofile(config_dir .. "/workspaces.lua")
dofile(config_dir .. "/input.lua")

local resolved = dofile(root .. "/lib/theme/resolved.lua")(root)
local theme = dofile(config_dir .. "/theme.lua")(resolved)
theme.apply()

dofile(config_dir .. "/rules.lua")
dofile(config_dir .. "/animations.lua")

-- Use the checkout launcher so shell shortcuts also work before bin is on PATH.
local launcher = "'" .. (root .. "/bin/luna"):gsub("'", "'\\''") .. "'"
dofile(config_dir .. "/autostart.lua")(launcher)
dofile(config_dir .. "/bindings.lua")(config_dir, launcher)
