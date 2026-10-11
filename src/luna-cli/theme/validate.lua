-- Theme exports are declarative tables, evaluated without filesystem or process APIs.
return function(common)
    local M = {}
    local required = {
        "accent", "accent_foreground", "selection", "selection_foreground", "muted",
        "background", "dark_background", "darker_background", "lighter_background",
        "foreground", "dark_foreground", "light_foreground", "bright_foreground",
    }

    local function read(directory, name, mandatory)
        local path = directory .. "/" .. name .. ".lua"
        if not common.succeeds({ "test", "-f", path }) then
            assert(not mandatory, "Missing colors.lua")
            return nil
        end
        local chunk = assert(loadfile(path, "t", {}))

        -- Bound accidental loops in a user-supplied export and always clear the hook.
        debug.sethook(function()
            error("Theme export exceeded its instruction limit")
        end, "", 100000)
        local ok, value = pcall(chunk)
        debug.sethook()
        assert(ok, name .. ".lua: " .. tostring(value))
        assert(type(value) == "table", name .. ".lua must return a table")
        return value
    end

    local function number(value, minimum, maximum, integer, name)
        assert(type(value) == "number" and value == value and value < math.huge and value >= minimum
            and value <= maximum and (not integer or value % 1 == 0), "Invalid " .. name)
    end

    local rules = {
        general = {
            gaps_in = { 0, math.huge, true }, gaps_out = { 0, math.huge, true },
            border_size = { 0, math.huge, true },
        },
        decoration = {
            rounding = { 0, 100, true }, active_opacity = { 0, 1 },
            inactive_opacity = { 0, 1 }, fullscreen_opacity = { 0, 1 },
            dim_inactive = "boolean", dim_strength = { 0, 1 },
            blur = { enabled = "boolean", size = { 1, math.huge, true }, passes = { 1, 10, true } },
            shadow = { enabled = "boolean", range = { 0, 100, true }, render_power = { 1, 4, true } },
        },
    }

    local function settings(values, schema, prefix)
        for key, value in pairs(values) do
            local rule = schema[key]
            assert(rule, "Unsupported theme setting: " .. prefix .. tostring(key))
            if rule == "boolean" then
                assert(type(value) == "boolean", prefix .. key .. " must be boolean")
            elseif rule[1] then
                number(value, rule[1], rule[2], rule[3], prefix .. key)
            else
                assert(type(value) == "table", prefix .. key .. " must be a table")
                settings(value, rule, prefix .. key .. ".")
            end
        end
    end

    function M.load(directory)
        local exports = { colors = read(directory, "colors", true) }
        local colors = exports.colors
        assert(colors.mode == "dark" or colors.mode == "light", "mode must be dark or light")
        for _, key in ipairs(required) do
            assert(colors[key], "Missing required color: " .. key)
        end
        for key, value in pairs(colors) do
            assert(type(key) == "string", "Color names must be strings")
            if key ~= "mode" then
                assert(type(value) == "string" and value:match("^#%x%x%x%x%x%x$"), "Invalid color: " .. key)
            end
        end

        exports.hyprland = read(directory, "hyprland")
        if exports.hyprland then
            settings(exports.hyprland, rules, "")
        end
        exports.fonts = read(directory, "fonts")
        for key, value in pairs(exports.fonts or {}) do
            if key == "size" or key == "mono_size" then
                number(value, 0.01, math.huge, false, key)
            else
                assert(key == "ui" or key == "mono" or key == "icons", "Unknown font field: " .. tostring(key))
                assert(type(value) == "string" and value ~= "" and not value:find("[%c]"), "Invalid font family")
            end
        end

        exports.wallpaper = read(directory, "wallpaper")
        local wallpaper = exports.wallpaper or {}
        for key in pairs(wallpaper) do
            assert(key == "sources", "Unknown wallpaper field: " .. tostring(key))
        end
        local sources = wallpaper.sources == nil and {} or wallpaper.sources
        assert(type(sources) == "table", "Wallpaper sources must be a list")
        local count = 0
        for index, source in pairs(sources) do
            assert(type(index) == "number" and index % 1 == 0 and index > 0, "Wallpaper sources must be a list")
            assert(type(source) == "string" and source ~= "" and not source:find("[%c]"), "Invalid wallpaper source")
            count = count + 1
        end
        assert(count == #sources, "Wallpaper sources must be a contiguous list")
        return exports
    end

    return M
end
