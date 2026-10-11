-- Theme commands manage copies and selection; application config generation comes later.
return function(common, module_dir)
    local validate = dofile(module_dir .. "/validate.lua")(common)
    local wallpaper_dir = module_dir .. "/../wallpaper"
    local download = dofile(wallpaper_dir .. "/download.lua")(common)
    local wallpapers = dofile(wallpaper_dir .. "/files.lua")(common, download)
    local store = dofile(module_dir .. "/store.lua")(common, validate, wallpapers, download)
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
        theme:command("set", "Save a selection without applying appearance settings."):argument("name")
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
            store.set(options.name)
        elseif options.remove then
            store.remove(options.names)
        end
    end

    return M
end
