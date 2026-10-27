#!/usr/bin/lua -E
-- Short-lived JSON transport for Luna.Wallpaper in QML. All wallpaper behavior
-- stays in api.lua; this process only dispatches one request and encodes its result.
local directory = assert(arg[0]:match("^(.*)/"), "Run the wallpaper bridge by its file path")
local root = directory .. "/../../.."
local json = dofile(root .. "/lib/json.lua")

-- Keep the public method list explicit. A request cannot invoke arbitrary Lua code
-- or select installation/library operations through this wallpaper-only client.
local methods = {
    getConfig = true, updateConfig = true, getConfigFile = true,
    reload = true, status = true, start = true, stop = true, restart = true,
}
local ok, response = pcall(function()
    local request = json.decode(arg[1] or "")
    assert(type(request) == "table" and methods[request.method], "Unknown wallpaper API method")
    if request.argument == json.null then
        request.argument = nil
    end
    local common = dofile(root .. "/lib/common.lua")
    local wallpaper = dofile(directory .. "/api.lua")(common, root)
    local result

    -- Config methods encode resolved values directly, including empty arrays,
    -- false/zero, and null for missing dotted keys.
    if request.method == "getConfig" then
        result = wallpaper.getConfig(request.argument, "json")
    elseif request.method == "updateConfig" then
        result = wallpaper.updateConfig(request.argument, "json")
    else
        local value = wallpaper[request.method](request.argument)
        result = json.encode(value == nil and json.null or value)
    end
    return '{"ok":true,"result":' .. result .. ',"configPath":' .. json.encode(wallpaper.getConfigFile()) .. '}'
end)

-- stdout is always a single JSON reply; stderr may also contain actionable parser
-- or process errors. A nonzero exit lets clients reject incomplete operations.
if ok then
    print(response)
else
    print(json.encode({ ok = false, error = tostring(response) }))
    os.exit(1)
end
