-- Translate the resolved JSON theme into native Hyprland Lua settings at config load.
return function(resolved)
    local M = {}
    local home = assert(os.getenv("HOME"), "HOME is required")
    local config = (os.getenv("XDG_CONFIG_HOME") or home .. "/.config") .. "/luna"

    function M.apply()
        local file, failure, code = io.open(config .. "/theme", "r")
        if not file then
            assert(code == 2, "Cannot read Luna theme selection: " .. tostring(failure))
            return
        end
        local name = file:read("*l")
        file:close()
        assert(name and name:match("^[a-z0-9][a-z0-9_-]*$"), "Invalid Luna theme selection")
        local exports = resolved.read(name)
        local settings = exports.hyprland or {}
        local colors = exports.colors
        settings.general = settings.general or {}
        settings.general.col = {
            active_border = colors.accent,
            inactive_border = colors.muted,
        }

        -- Shadow alpha controls opacity; derive hues from the shared background palette.
        local shadow = settings.decoration and settings.decoration.shadow
        if shadow then
            shadow.color = colors.dark_background .. "aa"
            shadow.color_inactive = colors.darker_background .. "66"
        end

        assert(hl and type(hl.config) == "function", "This adapter must run inside Hyprland's Lua config")
        hl.config(settings)
    end

    return M
end
