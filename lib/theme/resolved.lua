-- Resolve partial themes once and share the resulting JSON with every consumer.
return function(root)
    local M = {}
    local validate = dofile(root .. "/lib/theme/validate.lua")()
    local json = dofile(root .. "/lib/theme/json.lua")
    local defaults = dofile(root .. "/lib/theme/defaults.lua")
    local fonts = dofile(root .. "/lib/theme/fonts.lua")(root)
    local home = assert(os.getenv("HOME"), "HOME is required")
    local config_home = os.getenv("XDG_CONFIG_HOME")
    local config = (config_home and config_home ~= "" and config_home or home .. "/.config") .. "/luna"
    M.path = config .. "/theme.json"

    local function merge(base, overrides)
        local result = {}
        for key, value in pairs(base) do
            result[key] = type(value) == "table" and merge(value, {}) or value
        end
        for key, value in pairs(overrides) do
            result[key] = type(value) == "table" and merge(result[key] or {}, value) or value
        end
        return result
    end

    local function foreground(fill)
        local luminance = 0
        for index, weight in ipairs({ 0.2126, 0.7152, 0.0722 }) do
            local channel = tonumber(fill:sub(index * 2, index * 2 + 1), 16) / 255
            channel = channel <= 0.04045 and channel / 12.92 or ((channel + 0.055) / 1.055) ^ 2.4
            luminance = luminance + channel * weight
        end
        return (luminance + 0.05) / 0.05 >= 1.05 / (luminance + 0.05) and "#000000" or "#ffffff"
    end

    function M.resolve(exports, name)
        validate.values(exports)
        local base = defaults
        if exports.colors and exports.colors.mode == "light" then
            base = merge(defaults, { colors = dofile(root .. "/lib/theme/light.lua") })
        end
        local result = merge(base, exports)
        local colors = exports.colors or {}
        -- An overridden fill needs a readable foreground unless the author supplies one.
        for _, role in ipairs({ "accent", "selection", "secondary_accent", "error", "warning", "notice", "success", "info" }) do
            if colors[role] and not colors[role .. "_foreground"] then
                result.colors[role .. "_foreground"] = foreground(colors[role])
            end
        end
        for _, role in ipairs({ "secondary_accent", "error", "warning", "success", "info", "link" }) do
            if colors[role] and not colors[role .. "_emphasis"] then
                result.colors[role .. "_emphasis"] = colors[role]
            end
        end
        -- Wallpaper lists replace defaults rather than merging by numeric index.
        result.wallpaper.sources = (exports.wallpaper or {}).sources or {}
        result.version = 1
        result.name = name or "tokyo-night"
        validate.values(result)
        return fonts.apply(result)
    end

    function M.encode(exports)
        return json.encode(exports) .. "\n"
    end

    function M.read(name)
        local file = assert(io.open(M.path, "r"), "Resolved theme missing; run luna theme set " .. name)
        local content = file:read("*a")
        file:close()
        local result = json.decode(content)
        assert(type(result) == "table" and result.version == 1 and result.name == name,
            "Resolved theme does not match selection; run luna theme set " .. name)
        validate.values(result)
        local function complete(values, schema)
            assert(type(values) == "table", "Incomplete resolved theme; run luna theme set " .. name)
            for key, value in pairs(schema) do
                assert(values[key] ~= nil, "Incomplete resolved theme: " .. key)
                if type(value) == "table" then
                    complete(values[key], value)
                end
            end
        end
        complete(result, defaults)
        return fonts.apply(result)
    end

    function M.active()
        local file, failure, code = io.open(config .. "/theme", "r")
        if not file then
            assert(code == 2, failure)
            return M.resolve({})
        end
        local name = file:read("*l")
        file:close()
        assert(name and name:match("^[a-z0-9][a-z0-9_-]*$"), "Invalid selected theme")
        return M.read(name)
    end

    return M
end
