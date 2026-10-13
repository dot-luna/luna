-- Use Hyprlock's Wayland session lock and PAM; Luna never handles passwords.
return function(common, directory)
    local root = directory .. "/../../.."
    local resolved = dofile(root .. "/lib/theme/resolved.lua")(root)
    local M = {}

    function M.register(parser)
        return parser:command("lock", "Lock the session; unlock with your system password.")
    end

    function M.run()
        assert(os.getenv("WAYLAND_DISPLAY"), "Locking requires a Wayland session")
        assert(common.available("hyprlock"), "Hyprlock is missing; install core dependencies")
        local theme = resolved.active()
        local cache = (os.getenv("XDG_CACHE_HOME") or assert(os.getenv("HOME")) .. "/.cache") .. "/luna"
        common.run({ "mkdir", "-p", "--", cache })
        local path, ok = common.capture({ "mktemp", cache .. "/hyprlock-XXXXXX.conf" })
        assert(ok, "Cannot create lock configuration")
        path = path:gsub("\n$", "")

        -- Strip config metacharacters from font names; all colors/numbers are validated.
        local font = theme.fonts.ui:gsub("[#{}$\\\r\n]", "")
        local function color(value)
            return "rgb(" .. value:sub(2) .. ")"
        end
        local content = string.format([[
general {
    hide_cursor = true
}
background {
    monitor =
    color = %s
}
label {
    monitor =
    text = $TIME
    color = %s
    font_family = %s
    font_size = 64
    position = 0, 100
    halign = center
    valign = center
}
input-field {
    monitor =
    size = 320, 52
    outline_thickness = %d
    rounding = %d
    outer_color = %s
    inner_color = %s
    font_color = %s
    check_color = %s
    fail_color = %s
    font_family = %s
    placeholder_text = Password
    fail_text = Incorrect password
    fade_on_empty = false
    position = 0, -20
    halign = center
    valign = center
}
]], color(theme.colors.background), color(theme.colors.foreground), font,
            theme.hyprland.general.border_size, theme.hyprland.decoration.rounding,
            color(theme.colors.muted), color(theme.colors.lighter_background),
            color(theme.colors.foreground), color(theme.colors.accent), color(theme.colors.error), font)
        local file = assert(io.open(path, "w"))
        assert(file:write(content))
        assert(file:close())
        local success, message = pcall(common.run, { "hyprlock", "--config", path, "--grace", "0" })
        os.remove(path)
        assert(success, message)
    end

    return M
end
