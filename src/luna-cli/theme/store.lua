-- Installed theme copies use XDG data storage; selection is a name, not generated config.
return function(common, validate, wallpapers, download, mode)
    local M = {}
    local home = assert(os.getenv("HOME"), "HOME is required")
    M.directory = (os.getenv("XDG_DATA_HOME") or home .. "/.local/share") .. "/luna/themes"
    local config = (os.getenv("XDG_CONFIG_HOME") or home .. "/.config") .. "/luna"
    local selection = config .. "/theme"

    local function name_valid(name)
        assert(type(name) == "string" and name:match("^[a-z0-9][a-z0-9_-]*$"),
            "Theme names use lowercase letters, digits, hyphens, or underscores; use --name to choose one")
        return name
    end

    function M.path(name)
        if not name then
            return M.directory
        end
        local path = M.directory .. "/" .. name_valid(name)
        assert(common.succeeds({ "test", "-d", path }) and not common.succeeds({ "test", "-L", path }),
            "Installed theme not found: " .. name)
        return path
    end

    function M.current()
        local file = io.open(selection, "r")
        if not file then
            return nil
        end
        local name = file:read("*l")
        file:close()
        return name and name_valid(name) or nil
    end

    function M.list()
        if not common.succeeds({ "test", "-d", M.directory }) then
            return {}
        end
        local output, ok = common.capture({ "find", M.directory, "-mindepth", "1", "-maxdepth", "1", "-type", "d", "-printf", "%f\\0" })
        assert(ok, "Cannot list themes")
        local names = {}
        for name in output:gmatch("([^%z]+)%z") do
            if name:match("^[a-z0-9][a-z0-9_-]*$") then
                table.insert(names, name)
            end
        end
        table.sort(names)
        return names
    end

    local function font_report(exports)
        if not exports.fonts then
            return
        end
        for _, role in ipairs({ "ui", "mono", "icons" }) do
            local family = exports.fonts[role]
            if family then
                common.info("Font " .. role .. ": " .. family .. " (must be installed manually)")
            end
        end
    end

    function M.install(options)
        local output, ok = common.capture({ "realpath", "-e", "--", options.folder }, true)
        assert(ok, "Theme folder not found")
        local source = output:gsub("\n$", "")
        assert(common.succeeds({ "test", "-d", source }), "Theme source must be a directory")
        local name = name_valid(options.name or source:match("([^/]+)$"))
        local destination = M.directory .. "/" .. name
        assert(not source:find("[%c]"), "Theme path cannot contain control characters")
        assert(not common.succeeds({ "test", "-e", destination }) or options.force,
            "Theme already installed; use --force to replace it")
        assert(not common.succeeds({ "test", "-L", destination }), "Installed theme cannot be a symlink")

        -- Validate before copying, then again on the staged copy that will be installed.
        validate.load(source)
        common.run({ "mkdir", "-p", "--", M.directory })
        local library, resolved = common.capture({ "realpath", "-e", "--", M.directory })
        assert(resolved, "Cannot resolve theme library")
        library = library:gsub("\n$", "")
        assert(source ~= "/" and library ~= source and library:sub(1, #source + 1) ~= source .. "/",
            "Theme source cannot contain the installation directory")
        local temporary, created = common.capture({ "mktemp", "-d", M.directory .. "/.install-XXXXXX" })
        assert(created, "Cannot stage theme")
        temporary = temporary:gsub("\n$", "")
        -- Canonical staging paths also support XDG directories reached through symlinks.
        local canonical, canonical_ok = common.capture({ "realpath", "-e", "--", temporary })
        if not canonical_ok then
            common.run({ "rm", "-rf", "--", temporary })
            error("Cannot resolve temporary theme directory")
        end
        temporary = canonical:gsub("\n$", "")
        local staged, backup = temporary .. "/theme", temporary .. "/previous"
        local success, message = pcall(function()
            -- Dereference bundled links so the installed copy survives source removal.
            common.run({ "mkdir", "--", staged })
            common.run({ "cp", "-aL", "--", source .. "/.", staged })
            local exports = validate.load(staged)
            local targets = {}
            for _, value in ipairs((exports.wallpaper or {}).sources or {}) do
                if download.is_url(value) then
                    table.insert(targets, value)
                else
                    assert(value:sub(1, 1) ~= "/", "Wallpaper paths must be relative to the theme")
                    local resolved = wallpapers.absolute(staged .. "/" .. value)
                    assert(resolved:sub(1, #staged + 1) == staged .. "/", "Wallpaper source escapes the theme folder")
                    table.insert(targets, resolved)
                end
            end
            if #targets > 0 then
                assert(common.available("file"), "Wallpaper import requires the file package")
                wallpapers.add({ targets = targets })
            end

            -- Keep the previous copy until the replacement has been renamed into place.
            local replaced = common.succeeds({ "test", "-e", destination })
            if replaced then
                assert(os.rename(destination, backup))
            end
            local committed, failure = os.rename(staged, destination)
            if not committed and replaced then
                assert(os.rename(backup, destination))
            end
            assert(committed, failure)
            common.info("Installed theme: " .. name)
            font_report(exports)
        end)
        common.run({ "rm", "-rf", "--", temporary })
        assert(success, message)
    end

    function M.set(name, force)
        local exports = validate.load(M.path(name))
        if M.current() == name and not force then
            mode.apply(exports.colors.mode)
            common.info("Theme already selected: " .. name)
            return
        end
        common.run({ "mkdir", "-p", "--", config })
        local file = assert(io.open(selection .. ".tmp", "w"))
        assert(file:write(name, "\n"))
        assert(file:close())
        local success, restore = pcall(mode.apply, exports.colors.mode, force)
        if not success then
            os.remove(selection .. ".tmp")
            error(restore)
        end
        local selected, failure = os.rename(selection .. ".tmp", selection)
        if not selected then
            restore()
            os.remove(selection .. ".tmp")
            error(failure)
        end
        common.info("Selected theme: " .. name .. " (" .. exports.colors.mode .. " system appearance)")
    end

    function M.remove(names)
        local paths, seen = {}, {}
        for _, name in ipairs(names) do
            assert(name ~= M.current(), "Select another theme before removing the current theme")
            local path = M.path(name)
            if not seen[path] then
                table.insert(paths, path)
                seen[path] = true
            end
        end
        common.info("Remove these installed theme copies?")
        for _, path in ipairs(paths) do
            common.info("  " .. path)
        end
        io.stdout:write("Continue? [y/N] ")
        io.stdout:flush()
        local answer = io.read("*l")
        if answer and (answer:lower() == "y" or answer:lower() == "yes") then
            for _, path in ipairs(paths) do
                common.run({ "rm", "-rf", "--", path })
            end
        else
            common.info("Removal cancelled.")
        end
    end

    return M
end
