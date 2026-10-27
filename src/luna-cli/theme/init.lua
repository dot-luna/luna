-- Theme commands install sources and publish a complete resolved theme on selection.
return function(common, module_dir)
    local resolved = dofile(module_dir .. "/../../../lib/theme/resolved.lua")(module_dir .. "/../../..")
    local validate = dofile(module_dir .. "/../../../lib/theme/validate.lua")()
    local wallpaper_dir = module_dir .. "/../../../lib/wallpapers"
    local download = dofile(wallpaper_dir .. "/download.lua")(common)
    local wallpapers = dofile(wallpaper_dir .. "/files.lua")(common, download)
    local ini = dofile(module_dir .. "/../../../lib/ini.lua")
    local mode = dofile(module_dir .. "/mode.lua")(common, ini)
    local store = dofile(module_dir .. "/store.lua")(common, validate, wallpapers, download, mode, resolved)
    local M = {}

    function M.register(parser)
        local theme = parser:command("theme", "Manage theme copies and saved selection.")
        theme:require_command(false)
        local install = theme:command("install", "Validate and copy a local theme folder.")
        install:argument("folder")
        install:option("--name", "Installed theme name (defaults to folder name)")
        install:flag("--force", "Replace an installed theme")
        theme:command("list", "List installed themes and mark the selected theme.")
        theme:command("current", "Print the selected theme name.")
        theme:command("path", "Print the theme library or an installed theme's path."):argument("name"):args("?")
        local set = theme:command("set", "Select a theme and apply its system light/dark preference.")
        set:argument("name")
        set:flag("--force", "Reapply appearance settings even when already set")
        local appearance = theme:command("mode", "Read or change the system light/dark preference.")
        appearance:argument("appearance", "dark, light, or toggle"):args("?"):choices({ "dark", "light", "toggle" })
        appearance:flag("--force", "Reapply matching appearance settings")
        theme:command("toggle", "Toggle the system light/dark preference.")
            :flag("--force", "Rewrite all appearance settings")
        theme:command("remove", "Preview and remove installed theme copies."):argument("names"):args("+")
        return theme
    end

    function M.run(options)
        if options.install then
            store.install(options)
        elseif options.list then
            local current = store.current()
            for _, name in ipairs(store.list()) do
                common.info((name == current and "* " or "  ") .. name)
            end
        elseif options.current then
            common.info(assert(store.current(), "No theme selected yet"))
        elseif options.path then
            common.info(store.path(options.name))
        elseif options.set then
            store.set(options.name, options.force)
        elseif options.mode or options.toggle then
            local appearance = options.toggle and "toggle" or options.appearance
            if appearance then
                if appearance == "toggle" then
                    local name = store.current()
                    local fallback = name and resolved.resolve(validate.load(store.path(name))).colors.mode or nil
                    appearance = mode.current(fallback) == "dark" and "light" or "dark"
                end
                mode.apply(appearance, options.force)
                common.info("System appearance: " .. appearance)
            else
                local name = store.current()
                local fallback = name and resolved.resolve(validate.load(store.path(name))).colors.mode or nil
                common.info(mode.current(fallback))
            end
        elseif options.remove then
            store.remove(options.names)
        end
    end

    return M
end
