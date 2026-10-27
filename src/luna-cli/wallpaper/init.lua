-- Command-line adapter: compose Luna's media library and the wallpaper app's API.
-- Argument parsing, interactive prompts, and user-facing output stay in this file.
return function(common, module_dir)
    local luna = dofile(module_dir .. "/../../../lib/luna.lua")(module_dir .. "/../../..", common)
    local files = luna.wallpapers
    local wallpaper = luna.wallpaper
    local json = dofile(module_dir .. "/../../../lib/json.lua")
    local M = {}

    function M.register(parser)
        local wallpaper = parser:command("wallpaper w", "Manage wallpapers and Quickshell rendering.")
        wallpaper:require_command(false)

        local add = wallpaper:command("add", "Add image URLs, local media, or folders to the library.")
        add:argument("targets", "HTTP(S) image URLs, media files, or folders"):args("+")
        add:flag("-r --recursive", "Include subfolders")
        add:flag("--force", "Replace existing library images")

        local set = wallpaper:command("set", "Apply wallpaper media by library name or file path.")
        set:argument("image")

        local remove = wallpaper:command("remove", "Preview and remove library images.")
        remove:argument("names"):args("+")

        wallpaper:command("list", "List library images and mark the current selection.")
        wallpaper:command("random", "Apply a random library image.")
        local get = wallpaper:command("get-config getConfig", "Print resolved config or one dotted key."):target("get_config")
        get:argument("config_key", "Optional dotted key, such as wallpaper.source"):args("?")
        local update = wallpaper:command("update-config updateConfig", "Deep-merge a JSON object into the config."):target("update_config")
        update:argument("config_changes", "Partial config as a JSON object")
        wallpaper:command("get-config-file getConfigFile", "Print the absolute config file path."):target("get_config_file")
        wallpaper:command("status", "Print the wallpaper renderer state.")
        wallpaper:command("dir", "Print the wallpaper library directory.")
        wallpaper:command("open", "Open the library in the default file explorer.")
        wallpaper:command("start", "Start the wallpaper renderer and restore the saved selection.")
        wallpaper:command("stop", "Stop Luna's wallpaper renderer and its media playback.")
        wallpaper:command("restart", "Restart only Luna's wallpaper renderer and reread its config.")
        wallpaper:command("reload", "Reread wallpaper config without replacing the running renderer.")
        return wallpaper
    end

    function M.run(options)
        if options.get_config then
            local value = wallpaper.getConfig(options.config_key, "text")
            if value ~= "" then
                io.stdout:write(value, "\n")
            end
        elseif options.update_config then
            common.info(wallpaper.updateConfig(json.decode(options.config_changes), "json"))
        elseif options.get_config_file then
            common.info(wallpaper.getConfigFile())
        elseif options.status then
            common.info(wallpaper.status())
        elseif options.dir then
            common.info(files.directory)
        elseif options.open then
            assert(common.available("xdg-open"), "xdg-open is missing; install xdg-utils")
            common.run({ "mkdir", "-p", "--", files.directory })
            common.run({ "xdg-open", files.directory })
        elseif options.list then
            local current = wallpaper.getConfig("wallpaper.source")
            for _, path in ipairs(files.list()) do
                common.info((path == current and "* " or "  ") .. path)
            end
        elseif options.add then
            assert(common.available("file"), "Image validation requires the file package")
            files.add(options)
        elseif options.set or options.random then
            local path
            if options.random then
                path = files.random(wallpaper.getConfig("wallpaper.source"))
            else
                path = files.resolve(options.image)
            end
            path = files.absolute(path)
            files.validate(path)
            local previous = wallpaper.getConfig("wallpaper.source")
            wallpaper.updateConfig({ wallpaper = { source = path } })
            local ok, message = pcall(wallpaper.reload)
            if not ok then
                -- Selection is config plus reload. Restore the saved source if the
                -- renderer rejects it, and attempt to show the previous media again.
                wallpaper.updateConfig({ wallpaper = { source = previous } })
                pcall(wallpaper.reload)
                error(message, 0)
            end
            common.info("Wallpaper set: " .. path)
        elseif options.start then
            wallpaper.start()
        elseif options.stop then
            wallpaper.stop()
        elseif options.restart then
            wallpaper.restart()
        elseif options.reload then
            wallpaper.reload()
            common.info("Wallpaper config reloaded.")
        elseif options.remove then
            local paths = files.removalPlan(options.names, wallpaper.getConfig("wallpaper.source"))

            common.info("Remove these library images?")
            for _, path in ipairs(paths) do
                common.info("  " .. path)
            end
            io.stdout:write("Continue? [y/N] ")
            io.stdout:flush()
            local answer = io.read("*l")
            if answer and (answer:lower() == "y" or answer:lower() == "yes") then
                files.remove(paths, wallpaper.getConfig("wallpaper.source"))
            else
                common.info("Removal cancelled.")
            end
        end
    end

    return M
end
