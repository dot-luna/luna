#!/usr/bin/lua -E
-- Resolve config as JSON; TOMLKit uses --validate before committing file edits.
local directory = assert(arg[0]:match("^(.*)/"), "Run the config reader by its file path")
local root = directory .. "/../../.."
local ok, result = pcall(function()
    local config = dofile(directory .. "/config.lua")(dofile(root .. "/lib/common.lua"), root)
    if arg[1] == "--validate" then
        config.resolve(dofile(root .. "/lib/json.lua").decode(io.read("*a")))
        return
    end
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
