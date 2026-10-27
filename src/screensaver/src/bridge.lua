#!/usr/bin/lua -E
-- JSON transport for Luna.Screensaver. Behavior lives in the public Lua API.
local directory = assert(arg[0]:match("^(.*)/"), "Run the screensaver bridge by its file path")
local root = directory .. "/../../.."
local json = dofile(root .. "/lib/json.lua")
local methods = {
    getConfig = true, updateConfig = true, getConfigFile = true,
    start = true, stop = true, restart = true, reload = true,
    status = true, getState = true, show = true, hide = true,
    setStayAwake = true, toggleStayAwake = true,
    install = true, list = true, set = true, removalPlan = true, remove = true, getDirectory = true,
}

local ok, response = pcall(function()
    local request = json.decode(arg[1] or "")
    assert(type(request) == "table" and methods[request.method], "Unknown screensaver API method")
    if request.argument == json.null then
        request.argument = nil
    end
    local common = dofile(root .. "/lib/common.lua")
    local resolved, found = common.capture({ "realpath", "-e", "--", root }, true)
    assert(found, "Could not locate Luna source directory")
    root = resolved:gsub("\n$", "")
    local locked = arg[2] == "--locked"
    local screensaver = dofile(directory .. "/api.lua")(common, root, locked)
    local result
    if locked then
        common.assert_list(request.arguments, "Screensaver arguments")
        local value = screensaver[request.method](table.unpack(request.arguments))
        result = json.encode(value == nil and json.null or value)
    elseif request.method == "getConfig" then
        result = screensaver.getConfig(request.argument, "json")
    elseif request.method == "updateConfig" then
        result = screensaver.updateConfig(request.argument, "json")
    elseif request.method == "install" then
        assert(type(request.argument) == "table", "Install requires a source and optional options")
        local options = request.argument.options
        if options == json.null then
            options = nil
        end
        result = json.encode(screensaver.install(request.argument.source, options))
    else
        local value = screensaver[request.method](request.argument)
        result = json.encode(value == nil and json.null or value)
    end
    return '{"ok":true,"result":' .. result .. ',"configPath":'
        .. json.encode(screensaver.getConfigFile()) .. '}'
end)

if ok then
    print(response)
else
    print(json.encode({ ok = false, error = tostring(response) }))
    os.exit(1)
end
