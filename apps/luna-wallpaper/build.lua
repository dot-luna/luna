-- Generate the initial wallpaper settings from the theme installed in step 9.
return function(ctx)
    local theme = ctx.theme()
    local json = dofile(ctx.root .. "/lib/theme/json.lua")
    local data_home = os.getenv("XDG_DATA_HOME")
    data_home = data_home and data_home ~= "" and data_home or os.getenv("HOME") .. "/.local/share"
    assert(data_home:sub(1, 1) == "/", "XDG_DATA_HOME must be an absolute path")

    -- Only installed theme-relative files are candidates. URLs and folders need
    -- no downloads or scanning here; an empty source keeps the theme background.
    local source = ""
    for _, relative in ipairs(theme.wallpaper.sources) do
        local inside = relative:sub(1, 1) ~= "/" and not relative:match("^https?://")
        for part in relative:gmatch("[^/]+") do
            if part == ".." then
                inside = false
            end
        end
        local path = data_home .. "/luna/themes/" .. theme.name .. "/" .. relative
        if inside and os.execute("test -f " .. ctx.quote(path)) then
            source = path
            break
        end
    end

    -- JSON string escaping also works inside TOML basic strings. Remove only the
    -- surrounding quotes because the native template already provides them.
    ctx.render("config/wallpaper.toml", "wallpaper.toml", {
        source = json.encode(source):sub(2, -2),
        background = json.encode(theme.colors.background):sub(2, -2),
    })
end
