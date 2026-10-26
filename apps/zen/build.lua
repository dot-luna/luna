-- Substitute theme values into CSS; profile edits belong to the shared installer.
return function(ctx)
    local theme = ctx.theme()
    local json = dofile(ctx.root .. "/lib/theme/json.lua")

    -- Font families are CSS strings, so quote their delimiters before insertion.
    local ui_font = '"' .. theme.fonts.ui:gsub('[\\"]', function(character)
        return "\\" .. character
    end) .. '"'
    local square = theme.hyprland.decoration.rounding == 0
    local values = {
        colors = theme.colors,
        ui_font = ui_font,
        square_chrome = square and ctx.read("templates/square-chrome.css") or "",
        square_content = square and ctx.read("templates/square-content.css") or "",
    }

    ctx.render("templates/userChrome.css", "generated/userChrome.css", values)
    ctx.render("templates/userContent.css", "generated/userContent.css", values)
    ctx.write("generated/fonts.json", json.encode(theme.fonts) .. "\n")
end
