-- Wallpaper CLI commands share one media library and the renderer's user TOML config.
return function(common, module_dir)
    local download = dofile(module_dir .. "/download.lua")(common)
    local files = dofile(module_dir .. "/files.lua")(common, download)
    local renderer = module_dir .. "/../../wallpaper/src/shell.qml"
    local config = dofile(module_dir .. "/config.lua")(common, module_dir)
    local backend = dofile(module_dir .. "/backend.lua")(common, renderer, config)
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
        wallpaper:command("current", "Print the saved wallpaper path.")
        wallpaper:command("dir", "Print the wallpaper library directory.")
        wallpaper:command("open", "Open the library in the default file explorer.")
        wallpaper:command("start", "Start the wallpaper renderer and restore the saved selection.")
        wallpaper:command("restart", "Restart only Luna's wallpaper renderer and reread its config.")
        return wallpaper
    end

    function M.run(options)
        if options.dir then
            common.info(files.directory)
        elseif options.open then
            assert(common.available("xdg-open"), "xdg-open is missing; install xdg-utils")
            common.run({ "mkdir", "-p", "--", files.directory })
            common.run({ "xdg-open", files.directory })
        elseif options.current then
            local path = backend.current()
            assert(path, "No wallpaper selected yet")
            common.info(path)
        elseif options.list then
            local current = backend.current()
            for _, path in ipairs(files.list()) do
                common.info((path == current and "* " or "  ") .. path)
            end
        elseif options.add then
            assert(common.available("file"), "Image validation requires the file package")
            files.add(options)
        elseif options.set or options.random then
            local path
            if options.random then
                local choices = files.list()
                assert(#choices > 0, "Wallpaper library is empty")
                if #choices > 1 then
                    for i = #choices, 1, -1 do
                        if choices[i] == backend.current() then
                            table.remove(choices, i)
                        end
                    end
                end
                path = choices[math.random(#choices)]
            else
                path = files.resolve(options.image)
            end
            path = files.absolute(path)
            files.validate(path)
            backend.apply(path)
        elseif options.start then
            backend.start()
        elseif options.restart then
            backend.restart()
        elseif options.remove then
            local paths, seen = {}, {}
            for _, name in ipairs(options.names) do
                local path = files.resolve(name, true)
                assert(files.absolute(path) ~= backend.current(), "Select another wallpaper before removing the current image")
                if not seen[path] then
                    table.insert(paths, path)
                    seen[path] = true
                end
            end

            common.info("Remove these library images?")
            for _, path in ipairs(paths) do
                common.info("  " .. path)
            end
            io.stdout:write("Continue? [y/N] ")
            io.stdout:flush()
            local answer = io.read("*l")
            if answer and (answer:lower() == "y" or answer:lower() == "yes") then
                for _, path in ipairs(paths) do
                    assert(os.remove(path))
                end
            else
                common.info("Removal cancelled.")
            end
        end
    end

    return M
end
