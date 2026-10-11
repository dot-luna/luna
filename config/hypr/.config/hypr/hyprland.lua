-- Luna's Hyprland entry point; load shared defaults before personal overrides.
local root = os.getenv("LUNA_PATH")

-- Follow config symlinks back to the checkout without depending on the current cwd.
-- A copied entry point instead needs LUNA_PATH set to the Luna checkout directory.
if not root or root == "" then
    local source = debug.getinfo(1, "S").source:sub(2)
    local quoted = "'" .. source:gsub("'", "'\\''") .. "'"
    local pipe = assert(io.popen("readlink -f -- " .. quoted, "r"))
    local path = pipe:read("*l")
    -- Hyprland may reap subprocesses before pclose; use the resolved output instead.
    pipe:close()
    root = path and path:match("^(.*)/config/hypr/%.config/hypr/[^/]+$")
end
assert(root, "Set LUNA_PATH to the Luna checkout directory")

-- dofile runs again on each config load, so saved theme changes are not cached.
dofile(root .. "/default/hypr/bootstrap.lua")(root)

-- Add personal Hyprland settings below; later hl.config calls override theme values.
