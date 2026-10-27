-- Generate the initial wallpaper settings from the theme installed in step 9.
return function(ctx)
    local theme = ctx.theme()
    local json = dofile(ctx.root .. "/lib/json.lua")
    local toml = dofile(ctx.root .. "/lib/toml.lua")(dofile(ctx.root .. "/lib/common.lua"), json)
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

    -- Start with the shared defaults and let TOMLKit encode the theme-specific edits.
    -- Only this staged copy changes; the checked-in defaults stay untouched.
    ctx.write("wallpaper.toml", ctx.read("config/wallpaper.toml"))
    toml.update(ctx.output .. "/wallpaper.toml", {
        wallpaper = { source = source, background_color = theme.colors.background },
    })
end
