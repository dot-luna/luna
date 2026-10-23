#!/usr/bin/lua -E
-- Print browser/content styles and font defaults as JSON for setup. Extra arguments are ignored.
local function generate()
    -- Resolve symlinks before loading the shared theme helpers from this checkout.
    local quoted_path = "'" .. arg[0]:gsub("'", "'\\''") .. "'"
    local pipe = assert(io.popen("readlink -f -- " .. quoted_path, "r"))
    local path = pipe:read("*a")
    assert(pipe:close(), "Cannot locate the Zen theme generator")
    local root = assert(path:gsub("\n$", ""):match("^(.*)/apps/zen/scripts/[^/]+$"),
        "Zen theme generator must remain inside the Luna checkout")
    local theme = dofile(root .. "/lib/theme/resolved.lua")(root).active()
    local json = dofile(root .. "/lib/theme/json.lua")
    local colors = theme.colors

    -- Theme validation excludes control characters; quote the remaining CSS string
    -- delimiters so font names cannot introduce declarations or escape sequences.
    local function css_string(value)
        return '"' .. value:gsub('[\\"]', function(character)
            return "\\" .. character
        end) .. '"'
    end

    -- An imported sheet can inherit its parent's encoding without this leading
    -- declaration, which would corrupt non-ASCII font names in personal CSS.
    local header = '@charset "UTF-8";\n/* Generated from Luna\'s active theme; rerun setup to refresh. */\n'
    local chrome = { header, '@-moz-document url("chrome://browser/content/browser.xhtml") {' }
    local content = header
    local function declaration(name, value)
        chrome[#chrome + 1] = "        " .. name .. ": " .. value .. " !important;"
    end

    -- Keep these settings inside the browser document: websites retain their own
    -- colors and fonts, including their preferred light/dark appearance.
    chrome[#chrome + 1] = "    :root {"
    declaration("color-scheme", colors.mode)
    declaration("--toolbar-color-scheme", colors.mode)
    declaration("--luna-ui-font", css_string(theme.fonts.ui) .. ", sans-serif")
    local roles = {
        { "--zen-primary-color", "accent" },
        { "--zen-colors-primary", "dark_background" },
        { "--zen-colors-secondary", "lighter_background" },
        { "--zen-colors-tertiary", "background" },
        { "--zen-colors-hover-bg", "selection" },
        { "--zen-colors-primary-foreground", "foreground" },
        { "--zen-colors-border", "muted" },
        { "--zen-colors-border-contrast", "muted" },
        { "--zen-colors-input-bg", "dark_background" },
        { "--zen-branding-bg", "background" },
        { "--zen-branding-bg-reverse", "foreground" },
        { "--zen-dialog-background", "lighter_background" },
        { "--zen-in-content-dialog-background", "lighter_background" },
        { "--zen-urlbar-background", "dark_background" },
        { "--zen-input-border-color", "muted" },
        { "--zen-toolbar-element-bg", "lighter_background" },
        { "--zen-toolbar-element-bg-hover", "selection" },
        { "--zen-sidebar-notification-bg", "lighter_background" },
        { "--zen-sidebar-themed-icon-fill", "foreground" },
        { "--toolbox-background-color", "background" },
        { "--toolbox-background-color-inactive", "background" },
        { "--toolbox-textcolor", "foreground" },
        { "--toolbar-background-color", "background" },
        { "--toolbar-color", "foreground" },
        { "--toolbar-field-background-color", "dark_background" },
        { "--toolbar-field-color", "foreground" },
        { "--toolbar-field-focus-background-color", "lighter_background" },
        { "--toolbar-field-focus-color", "foreground" },
        { "--toolbarbutton-background-color-hover", "selection" },
        { "--toolbarbutton-background-color-active", "muted" },
        { "--arrowpanel-background", "lighter_background" },
        { "--arrowpanel-color", "foreground" },
        { "--arrowpanel-border-color", "muted" },
        { "--panel-separator-color", "muted" },
        { "--input-color", "foreground" },
        { "--input-bgcolor", "dark_background" },
        { "--input-border-color", "muted" },
        { "--focus-outline-color", "accent" },
        { "--link-color", "link" },
        { "--link-color-hover", "link_emphasis" },
        { "--in-content-primary-button-background", "accent" },
        { "--in-content-primary-button-background-hover", "accent" },
        { "--in-content-primary-button-background-active", "accent" },
        { "--in-content-primary-button-text-color", "accent_foreground" },
    }
    for _, entry in ipairs(roles) do
        declaration(entry[1], colors[entry[2]])
    end
    chrome[#chrome + 1] = "    }"

    -- Zen writes workspace gradients on these elements directly, so inherited
    -- root variables alone would not replace their inline background values.
    chrome[#chrome + 1] = "\n    :root, .zen-browser-generic-background {"
    for _, name in ipairs({
        "--zen-main-browser-background", "--zen-main-browser-background-old",
        "--zen-main-browser-background-toolbar", "--zen-main-browser-background-toolbar-old",
    }) do
        declaration(name, colors.background)
    end
    declaration("--zen-background-opacity", "1")
    chrome[#chrome + 1] = "    }"

    chrome[#chrome + 1] = "\n    .tabbrowser-tab {"
    declaration("--tab-background-color-selected", colors.selection)
    declaration("--zen-essential-tab-selected-bg", colors.selection)
    declaration("--zen-essential-tab-selected-bg-hover", colors.selection)
    chrome[#chrome + 1] = "    }"
    chrome[#chrome + 1] = '\n    .tabbrowser-tab:is([visuallyselected], [multiselected="true"]) {'
    declaration("color", colors.selection_foreground)
    chrome[#chrome + 1] = "    }"

    -- Target text controls instead of replacing icon fonts or image contents.
    chrome[#chrome + 1] = [[

    :root, #navigator-toolbox, #sidebar-box, #urlbar, #searchbar,
    .tab-label, .toolbarbutton-text, menu, menuitem, menulist,
    button, input, textarea, select {
        font-family: var(--luna-ui-font) !important;
    }

    ::selection {]]
    declaration("background-color", colors.selection)
    declaration("color", colors.selection_foreground)
    chrome[#chrome + 1] = "    }"

    -- Zero opts into square corners. Positive Luna rounding leaves every native
    -- Zen/site radius alone, rather than imposing a different numeric radius.
    if theme.hyprland.decoration.rounding == 0 then
        chrome[#chrome + 1] = "\n    :root {"
        for _, name in ipairs({
            "--zen-border-radius", "--zen-webview-border-radius", "--zen-native-inner-radius",
            "--button-border-radius", "--toolbarbutton-border-radius", "--tab-border-radius",
            "--arrowpanel-border-radius", "--panel-border-radius",
            "--border-radius-small", "--border-radius-medium", "--border-radius-large",
            "--border-radius-xlarge", "--border-radius-circle",
        }) do
            declaration(name, "0px")
        end
        chrome[#chrome + 1] = [[
    }

    /* Cover hardcoded corners too; leave masks, icons and canvas drawings intact. */
    *, *::before, *::after {
        border-radius: 0 !important;
    }]]
        content = content .. [[
/* Only ordinary websites receive the square-corner override. */
@-moz-document url-prefix("http://"), url-prefix("https://") {
    *, *::before, *::after {
        border-radius: 0 !important;
    }
}
]]
    end
    chrome[#chrome + 1] = "}"

    -- Emit only after both styles and JSON encoding succeed, so setup can reject
    -- invalid themes without replacing either installed stylesheet partially.
    -- Profile preferences use raw family names; CSS escaping applies only to the
    -- browser stylesheet. Website font declarations remain under each site's control.
    local output = json.encode({
        chrome = table.concat(chrome, "\n") .. "\n",
        content = content,
        fonts = { ui = theme.fonts.ui, mono = theme.fonts.mono },
    })
    assert(io.stdout:write(output, "\n"))
    assert(io.stdout:flush())
end

local ok, message = pcall(generate)
if not ok then
    local detail = tostring(message):gsub("^.-:%d+: ", "")
    io.stderr:write("Cannot generate Zen theme: " .. detail .. "\n")
    os.exit(1)
end
