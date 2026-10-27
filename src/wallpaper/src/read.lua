#!/usr/bin/lua -E
-- Config transport: the renderer reads validated JSON; TOMLKit uses --validate
-- to check its merged JSON on stdin before writing. Rules stay in config.lua.
local directory = assert(arg[0]:match("^(.*)/"), "Run the config reader by its file path")
local root = directory .. "/../../.."

local ok, result = pcall(function()
    local config = dofile(directory .. "/config.lua")(dofile(root .. "/lib/common.lua"), root)

    if arg[1] == "--validate" then
        local json = dofile(root .. "/lib/json.lua")
        config.resolve(json.decode(io.read("*a")))
        return
    end

    -- API callers may inspect defaults before installation, but rendering requires
    -- a user file. A missing/unreadable file must produce the black error fallback.
    local file = assert(io.open(config.file(), "r"), "Config file is missing or unreadable")
    file:close()
    return config.get(nil, "json")
end)

if ok then
    if result then
        print(result)
    end
else
    io.stderr:write(tostring(result), "\n")
    os.exit(1)
end
