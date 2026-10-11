-- Translate the installed theme into native Hyprland Lua settings at config load.
return function(validate)
    local M = {}
    local home = assert(os.getenv("HOME"), "HOME is required")
    local config = (os.getenv("XDG_CONFIG_HOME") or home .. "/.config") .. "/luna"
    local data = (os.getenv("XDG_DATA_HOME") or home .. "/.local/share") .. "/luna/themes"

    function M.apply()
        local file, failure, code = io.open(config .. "/theme", "r")
        if not file then
            assert(code == 2, "Cannot read Luna theme selection: " .. tostring(failure))
            return
        end
        local name = file:read("*l")
        file:close()
        assert(name and name:match("^[a-z0-9][a-z0-9_-]*$"), "Invalid Luna theme selection")
        local directory = data .. "/" .. name

        -- Reuse installation validation and read fresh tables on every startup/reload.
        local exports = validate.load(directory)
        local settings = exports.hyprland or {}
        -- Monitor rules use hl.monitor, not hl.config; keep them out of its table.
        local monitor = settings.monitor
        settings.monitor = nil
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
        if monitor and monitor.scale then
            hl.monitor({ output = "", scale = monitor.scale })
        end
    end

    return M
end
