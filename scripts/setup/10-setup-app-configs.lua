#!/usr/bin/lua -E
-- Configure apps in the declared order; builders finish before files are published.
-- Extra arguments are ignored. LUNA_SETUP_APP selects one app for focused reruns.
local pipe = assert(io.popen("readlink -f -- '" .. arg[0]:gsub("'", "'\\''") .. "'", "r"))
local path = pipe:read("*a"):gsub("\n$", "")
assert(pipe:close(), "Cannot locate application setup")
local root = assert(path:match("^(.*)/scripts/setup/[^/]+$"))
local common = dofile(root .. "/lib/common.lua")
local json = dofile(root .. "/lib/json.lua")
common.setup_logging()

local function install()
    local selected = os.getenv("LUNA_SETUP_APP")
    assert(not selected or selected:match("^[a-z][a-z0-9_-]*$"), "Invalid LUNA_SETUP_APP")
    local order = dofile(root .. "/apps/order.lua")
    common.assert_list(order, "App setup order")
    local names = {}
    for _, name in ipairs(order) do
        assert(type(name) == "string" and name:match("^[a-z][a-z0-9_-]*$"),
            "Invalid app name in apps/order.lua")
        assert(not names[name], "Duplicate app in apps/order.lua: " .. name)
        names[name] = true
    end
    assert(not selected or names[selected],
        "App is not listed in apps/order.lua: " .. (selected or ""))
    if #order == 0 then
        common.info("No app configurations listed.")
        return
    end

    -- Validate the full selection before the publisher changes any app files.
    local apps = {}
    for _, name in ipairs(order) do
        if not selected or selected == name then
            local source = root .. "/apps/" .. name
            local app = dofile(source .. "/app.lua")
            assert(type(app) == "table", "App descriptor must return a table: " .. name)
            common.assert_list(app.connections or {}, name .. " connections")
            common.assert_list(app.retired or {}, name .. " retired files")
            apps[#apps + 1] = '{"name":' .. json.encode(name)
                .. ',"source":' .. json.encode(source)
                .. ',"config":' .. json.encode(app.config)
                .. ',"builder":' .. json.encode(app.builder or false)
                .. ',"connections":' .. json.encode(app.connections or {}, true)
                .. ',"retired":' .. json.encode(app.retired or {}, true) .. '}'
        end
    end
    local publisher = assert(io.popen(common.command({ "/usr/bin/python3",
        root .. "/scripts/setup/app-configs.py" }), "w"))
    assert(publisher:write('{"apps":[', table.concat(apps, ","), ']}\n'))
    assert(publisher:close(), "Application configuration setup failed")
end

local ok, message = pcall(install)
if not ok then
    common.error(tostring(message))
    os.exit(1)
end
