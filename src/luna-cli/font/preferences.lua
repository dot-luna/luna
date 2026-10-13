-- Expose installed family choices and persist UI/mono preferences for all Luna consumers.
return function(common, directory)
    local root = directory .. "/../../.."
    local json = dofile(root .. "/lib/theme/json.lua")
    local preferences = dofile(root .. "/lib/theme/fonts.lua")(root)
    local resolved = dofile(root .. "/lib/theme/resolved.lua")(root)
    local M = {}

    function M.families(role)
        local output, ok = common.capture({ "fc-list", "--format", "%{family[0]}\t%{spacing}\n" })
        assert(ok, "Cannot list installed font families")
        local families = {}
        for line in output:gmatch("[^\n]+") do
            local family = line:match("^(.-)\t(.*)$")
            if family and family ~= "" then
                families[family] = true
            end
        end
        local current = resolved.active().fonts[role]
        local results = {}
        for family in pairs(families) do
            table.insert(results, { name = family, family = family, current = family == current })
        end
        table.sort(results, function(a, b) return a.name:lower() < b.name:lower() end)
        return results
    end

    function M.set(role, family)
        local found = false
        for _, entry in ipairs(M.families(role)) do
            found = found or entry.family == family
        end
        assert(found, "Font family is not installed for " .. role)
        local theme = resolved.active()
        local values = preferences.read()
        values[role], theme.fonts[role] = family, family
        common.run({ "mkdir", "-p", "--", preferences.path:match("^(.*)/") })
        local function publish(path, content)
            local file = assert(io.open(path .. ".tmp", "w"))
            assert(file:write(content .. "\n"))
            assert(file:close())
            assert(os.rename(path .. ".tmp", path))
        end
        publish(preferences.path, json.encode(values))
        publish(resolved.path, json.encode(theme))

        -- Running shells update in place; inactive shells read the saved JSON on startup.
        if common.available("qs") and os.getenv("WAYLAND_DISPLAY") then
            for _, item in ipairs({ { "launcher", "launcher" }, { "luna-bar", "bar" }, { "screensaver", "screensaver" } }) do
                common.capture({ "qs", "ipc", "-p", root .. "/src/" .. item[1],
                    "call", item[2], "applyFonts", json.encode(theme.fonts) }, true)
            end
        end
        common.info(json.encode(theme.fonts))
    end

    return M
end
