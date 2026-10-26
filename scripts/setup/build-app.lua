#!/usr/bin/lua -E
-- Internal builder entry point; all output goes to a temporary app directory.
local pipe = assert(io.popen("readlink -f -- '" .. arg[0]:gsub("'", "'\\''") .. "'", "r"))
local path = pipe:read("*a"):gsub("\n$", "")
assert(pipe:close(), "Cannot locate the app builder")
local root = assert(path:match("^(.*)/scripts/setup/[^/]+$"))
local common = dofile(root .. "/lib/common.lua")
common.setup_logging()

local ok, message = pcall(function()
    local source, output, destination, config_dir = table.unpack(arg)
    local app = dofile(source .. "/app.lua")
    local builder = assert(loadfile(source .. "/" .. app.builder))()
    assert(type(builder) == "function", "App builder must return a function")
    builder(dofile(root .. "/lib/apps.lua")(root, source, output, destination, config_dir))
end)
if not ok then
    common.error("App build failed: " .. tostring(message))
    os.exit(1)
end
