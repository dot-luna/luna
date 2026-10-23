#!/usr/bin/lua -E
-- Print theme.conf for setup to stage beside kitty.conf. Extra arguments are ignored.
local function generate()
    -- Resolve the script before loading helpers so symlinks and other working
    -- directories still use the checkout containing this generator.
    local quoted_path = "'" .. arg[0]:gsub("'", "'\\''") .. "'"
    local pipe = assert(io.popen("readlink -f -- " .. quoted_path, "r"))
    local path = pipe:read("*a")
    assert(pipe:close(), "Cannot locate the Kitty theme generator")
    local root = assert(path:gsub("\n$", ""):match("^(.*)/apps/kitty/scripts/[^/]+$"),
        "Kitty theme generator must remain inside the Luna checkout")
    local theme = dofile(root .. "/lib/theme/resolved.lua")(root).active()
    local colors = theme.colors

    -- Buffer the complete configuration so a broken selection or font preference
    -- cannot produce a partial theme on stdout.
    local lines = { "# Generated from Luna's active theme; rerun setup to refresh." }
    local function option(name, value)
        lines[#lines + 1] = name .. " " .. value
    end

    lines[#lines + 1] = "\n# Personal monospace preferences override the theme's font family."
    option("font_family", theme.fonts.mono)
    option("bold_font", "auto")
    option("italic_font", "auto")
    option("bold_italic_font", "auto")

    lines[#lines + 1] = "\n# Terminal text, cursor, and selected text."
    option("background", colors.background)
    option("foreground", colors.foreground)
    option("cursor", colors.accent)
    option("cursor_text_color", colors.accent_foreground)
    option("selection_background", colors.selection)
    option("selection_foreground", colors.selection_foreground)

    lines[#lines + 1] = "\n# Window borders and tab labels share Luna's surface and accent colors."
    option("active_border_color", colors.accent)
    option("inactive_border_color", colors.muted)
    option("bell_border_color", colors.warning)
    option("active_tab_background", colors.accent)
    option("active_tab_foreground", colors.accent_foreground)
    option("inactive_tab_background", colors.lighter_background)
    option("inactive_tab_foreground", colors.foreground)
    option("tab_bar_background", colors.dark_background)

    -- ANSI uses black, red, green, yellow, blue, magenta, cyan, and white.
    -- Emphasis roles provide the corresponding bright colors for either mode.
    lines[#lines + 1] = "\n# ANSI colors 0-7, followed by their emphasized variants 8-15."
    local palette = {
        "dark_background", "error", "success", "warning",
        "link", "secondary_accent", "info", "light_foreground",
        "dark_foreground", "error_emphasis", "success_emphasis", "warning_emphasis",
        "link_emphasis", "secondary_accent_emphasis", "info_emphasis", "bright_foreground",
    }
    for index, role in ipairs(palette) do
        option("color" .. (index - 1), colors[role])
    end

    assert(io.stdout:write(table.concat(lines, "\n"), "\n"))
    assert(io.stdout:flush())
end

local ok, message = pcall(generate)
if not ok then
    local detail = tostring(message):gsub("^.-:%d+: ", "")
    io.stderr:write("Cannot generate Kitty theme: " .. detail .. "\n")
    os.exit(1)
end
