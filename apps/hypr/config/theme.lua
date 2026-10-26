-- hyprland.lua supplies Luna's shared theme reader, then calls apply() on each load.
-- Translate its resolved JSON snapshot into native Hyprland appearance settings.
return function(resolved)
    local M = {}

    -- Use the standard user config directory, including a custom XDG_CONFIG_HOME.
    -- Luna keeps the selected theme name and its resolved snapshot in this folder.
    local home = assert(os.getenv("HOME"), "HOME is required")
    local config_home = os.getenv("XDG_CONFIG_HOME")
    local config = (config_home and config_home ~= "" and config_home or home .. "/.config") .. "/luna"

    -- Read the current selection at application time so a config reload picks up changes.
    function M.apply()
        local file, failure, code = io.open(config .. "/theme", "r")

        -- No selection means no theme overrides. Other read failures must be reported,
        -- rather than silently treating an unreadable selection as an unset theme.
        if not file then
            assert(code == 2, "Cannot read Luna theme selection: " .. tostring(failure))
            return
        end

        -- The first line is a theme identifier: lowercase letters, digits, hyphens
        -- and underscores, beginning with a letter or digit.
        local name = file:read("*l")
        file:close()
        assert(name and name:match("^[a-z0-9][a-z0-9_-]*$"), "Invalid Luna theme selection")

        -- The reader validates theme.json and checks that it matches this selection.
        -- Its Hyprland section supplies gaps, borders, opacity, blur and other settings.
        local exports = resolved.read(name)
        local settings = exports.hyprland or {}
        local colors = exports.colors

        -- Keep focus colors consistent with Luna's shared palette: the focused
        -- window gets the accent border, while other windows use the muted color.
        settings.general = settings.general or {}
        settings.general.col = {
            active_border = colors.accent,
            inactive_border = colors.muted,
        }

        -- Shadow alpha controls opacity; derive hues from the shared background palette.
        local shadow = settings.decoration and settings.decoration.shadow
        if shadow then
            -- Append hexadecimal alpha: aa is about 67% opacity for the focused shadow.
            shadow.color = colors.dark_background .. "aa"

            -- Other windows use a darker background shade with 66, or 40%, opacity.
            shadow.color_inactive = colors.darker_background .. "66"
        end

        -- Submit the settings to the running config parser. Personal overrides loaded
        -- after Luna's main include can replace any of these appearance values.
        assert(hl and type(hl.config) == "function", "This adapter must run inside Hyprland's Lua config")
        hl.config(settings)
    end

    return M
end
