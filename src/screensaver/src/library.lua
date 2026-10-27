-- Local screensaver packages share the wallpaper library's Lua/file-tool model.
-- Imports and discovery are passive; the public API serializes mutations.
return function(common, root)
    local json = dofile(root .. "/lib/json.lua")
    local M = {}
    local bundled_order = { "clock", "blank", "orbit" }
    local bundled = {
        clock = root .. "/src/screensaver/src/shell/shell.qml",
        blank = root .. "/src/screensaver/examples/blank/shell.qml",
        orbit = root .. "/src/screensaver/examples/orbit/shell.qml",
    }

    local function path(value, physical, required)
        assert(type(value) == "string" and value ~= "" and not value:find("[%z\1-\31\127]"),
            "Screensaver paths must be nonempty and contain no control characters")
        if value:sub(1, 2) == "~/" then
            value = assert(os.getenv("HOME"), "HOME is required") .. value:sub(2)
        end
        assert(value:sub(1, 1) ~= "~", "Use an absolute path, relative path, or ~/ path")
        local output, ok = common.capture({ "realpath", required and "-e" or physical and "-m" or "-ms",
            "--", value }, true)
        assert(ok, "Path not found: " .. value)
        return (output:gsub("\n$", ""))
    end

    local function exists(value)
        return common.succeeds({ "test", "-e", value }) or common.succeeds({ "test", "-L", value })
    end

    local function regular(value)
        return not common.succeeds({ "test", "-L", value }) and common.succeeds({ "test", "-f", value })
    end

    local function valid_name(value)
        return type(value) == "string" and value:match("^[A-Za-z0-9][A-Za-z0-9._-]*$") ~= nil
    end

    local function name(value)
        assert(valid_name(value),
            "Use a screensaver name containing letters, numbers, dots, underscores, or hyphens")
        return value
    end

    local function parent(value)
        local result = value:match("^(.*)/[^/]+$")
        return result and result ~= "" and result or "/"
    end

    local function basename(value)
        return value:match("([^/]+)$")
    end

    local function inside(value, directory)
        return directory == "/" or value == directory or value:sub(1, #directory + 1) == directory .. "/"
    end

    function M.getDirectory()
        local data = os.getenv("XDG_DATA_HOME")
        if not data or data == "" then
            local home = os.getenv("HOME")
            assert(home and home:sub(1, 1) == "/", "HOME must be an absolute path")
            data = home .. "/.local/share"
        end
        assert(data:sub(1, 1) == "/", "XDG_DATA_HOME must be an absolute path")
        return path(data .. "/luna/screensavers")
    end

    local function directory()
        local value = M.getDirectory()
        -- Users may choose a linked data home; Luna's own descendants may not
        -- redirect package writes or deletions to unrelated directories.
        for _, candidate in ipairs({ parent(value), value }) do
            assert(not common.succeeds({ "test", "-L", candidate })
                and (not exists(candidate) or common.succeeds({ "test", "-d", candidate })),
                "Screensaver library must be a real directory: " .. candidate)
        end
        return value
    end

    local function entry(value, library)
        name(value)
        if bundled[value] then
            return { name = value, path = path(bundled[value], true), bundled = true }
        end
        local location = library .. "/" .. value
        assert(not common.succeeds({ "test", "-L", location }),
            "Screensaver library entries cannot be symlinks: " .. value)
        assert(common.succeeds({ "test", "-d", location }) and regular(location .. "/shell.qml"),
            "Screensaver not found: " .. value)
        return { name = value, path = location .. "/shell.qml", bundled = false }
    end

    function M.list()
        local library, entries = directory(), json.array()
        for _, value in ipairs(bundled_order) do
            table.insert(entries, entry(value, library))
        end
        if not exists(library) then
            return entries
        end
        local output, ok = common.capture({ "find", library, "-mindepth", "1", "-maxdepth", "1", "-print0" }, true)
        assert(ok, "Cannot read screensaver library")
        local names = {}
        for location in output:gmatch("([^%z]+)%z") do
            local value = basename(location)
            if valid_name(value) and not bundled[value]
                and (common.succeeds({ "test", "-d", location }) or common.succeeds({ "test", "-L", location })) then
                table.insert(names, value)
            end
        end
        table.sort(names)
        for _, value in ipairs(names) do
            table.insert(entries, entry(value, library))
        end
        return entries
    end

    function M.resolve(target)
        assert(type(target) == "string" and target ~= "", "Screensaver must be a name or QML file path")
        local library, selected = directory()
        if valid_name(target) and (bundled[target] or exists(library .. "/" .. target)) then
            selected = entry(target, library)
        else
            local location = path(target)
            assert(location:match("%.qml$") and common.succeeds({ "test", "-f", location }),
                "Screensaver not found: " .. target)
            location = path(location, true, true)
            for _, value in ipairs(bundled_order) do
                if location == path(bundled[value], true) then
                    selected = entry(value, library)
                    break
                end
            end
            if not selected then
                if basename(location) == "shell.qml" and parent(parent(location)) == path(library, true) then
                    selected = entry(basename(parent(location)), library)
                else
                    selected = { name = basename(location) == "shell.qml" and basename(parent(location))
                        or basename(location):gsub("%.qml$", ""), path = location, bundled = false }
                end
            end
        end
        selected.selection = selected.bundled and selected.name == "clock" and "" or selected.path
        return selected
    end

    local function protect(destination, paths)
        paths = paths or {}
        common.assert_list(paths, "Protected paths")
        for _, selected in ipairs(paths) do
            assert(type(selected) == "string", "Protected paths must contain strings")
            if selected ~= "" then
                assert(not inside(path(selected, true), path(destination, true)),
                    "Select and reload another screensaver before replacing or removing this shell")
            end
        end
    end

    -- Plan every resource before creating a destination. Hidden assets are kept;
    -- only .git is excluded. Symlinks and device/socket/pipe files are unsupported.
    local function resources(source)
        local output, ok = common.capture({ "find", source, "-mindepth", "1",
            "-name", ".git", "-prune", "-o", "-printf", "%y%p\\0" }, true)
        assert(ok, "Cannot read screensaver folder: " .. source)
        local directories, files = {}, {}
        for record in output:gmatch("([^%z]+)%z") do
            local kind, location = record:sub(1, 1), record:sub(2)
            assert(kind ~= "l", "Screensaver packages cannot contain symlinks: " .. location)
            assert(kind == "d" or kind == "f",
                "Screensaver packages may contain only regular files and folders: " .. location)
            table.insert(kind == "d" and directories or files, location:sub(#source + 2))
        end
        table.sort(directories)
        table.sort(files)
        return directories, files
    end

    local function command(arguments, message)
        local _, ok = common.capture(arguments, true)
        assert(ok, message)
    end

    function M.install(source, options)
        options = options == nil and {} or options
        assert(type(options) == "table", "Install options must be an object")
        assert(options.name == nil or type(options.name) == "string", "Screensaver name must be a string")
        assert(options.force == nil or type(options.force) == "boolean", "Force must be a boolean")
        source = path(source)
        assert(not common.succeeds({ "test", "-L", source }), "Screensaver sources cannot be symlinks: " .. source)
        local folder = common.succeeds({ "test", "-d", source })
        assert(folder and regular(source .. "/shell.qml") or not folder and source:match("%.qml$") and regular(source),
            "Install a local folder containing shell.qml or a regular .qml file")
        local default_name = folder and basename(source)
            or basename(source) == "shell.qml" and basename(parent(source)) or basename(source):gsub("%.qml$", "")
        local value = name(options.name or default_name)
        assert(not bundled[value], "Screensaver name is reserved: " .. value .. "; choose another with --name")
        local library = directory()
        local destination = library .. "/" .. value
        source = path(source, true, true)
        local resolved_destination = path(destination, true)
        assert(not inside(source, resolved_destination) and not (folder and inside(resolved_destination, source)),
            "Screensaver source and destination must not overlap")
        assert(not common.succeeds({ "test", "-L", destination })
            and (not exists(destination) or common.succeeds({ "test", "-d", destination })),
            "Screensaver destination must be a real directory: " .. value)
        protect(destination, options.protectedPaths)
        assert(not exists(destination) or options.force,
            "Screensaver already installed: " .. value .. "; use --force to replace it")
        local directories, files = {}, {}
        if folder then
            directories, files = resources(source)
        end

        command({ "mkdir", "-p", "--", library }, "Cannot create screensaver library")
        local staging, created = common.capture({ "mktemp", "-d", "--", library .. "/.install-XXXXXX" }, true)
        assert(created, "Cannot stage screensaver package")
        staging = staging:gsub("\n$", "")
        local payload, previous = staging .. "/package", staging .. "/previous"
        local moved, committed = false, false
        local success, failure = pcall(function()
            command({ "mkdir", "--", payload }, "Cannot stage screensaver package")
            for _, relative in ipairs(directories) do
                command({ "mkdir", "-p", "--", payload .. "/" .. relative }, "Cannot copy screensaver folders")
            end
            if folder then
                for _, relative in ipairs(files) do
                    command({ "cp", "--preserve=mode,timestamps", "--no-dereference", "--",
                        source .. "/" .. relative, payload .. "/" .. relative }, "Cannot copy screensaver resource: " .. relative)
                end
            else
                command({ "cp", "--preserve=mode,timestamps", "--no-dereference", "--", source, payload .. "/shell.qml" },
                    "Cannot copy screensaver shell")
            end

            -- Move the complete package into place only after every copy succeeds.
            -- Keep the previous directory until the replacement rename succeeds.
            if exists(destination) then
                assert(os.rename(destination, previous))
                moved = true
            end
            local renamed, message = os.rename(payload, destination)
            if not renamed then
                if moved then
                    local restored, restore_error = os.rename(previous, destination)
                    assert(restored, "Could not restore screensaver; previous package remains at "
                        .. previous .. ": " .. tostring(restore_error))
                    moved = false
                end
                error(message, 0)
            end
            committed = true
        end)
        -- If rollback itself fails, retain the only surviving previous package.
        if not moved or committed then
            local _, cleaned = common.capture({ "rm", "-rf", "--", staging }, true)
            assert(cleaned, "Could not clean screensaver staging folder: " .. staging)
        end
        assert(success, failure)
        return entry(value, library)
    end

    function M.removalPlan(names, protectedPaths)
        common.assert_list(names, "Screensaver names")
        assert(#names > 0, "Provide at least one installed screensaver name")
        local library, entries, seen = directory(), json.array(), {}
        for _, value in ipairs(names) do
            name(value)
            assert(not bundled[value], "Bundled screensavers cannot be removed: " .. value)
            local selected = entry(value, library)
            protect(parent(selected.path), protectedPaths)
            if not seen[value] then
                table.insert(entries, selected)
                seen[value] = true
            end
        end
        return entries
    end

    function M.remove(names, protectedPaths)
        local plan = M.removalPlan(names, protectedPaths)
        local removed = json.array()
        for _, selected in ipairs(plan) do
            command({ "rm", "-rf", "--", parent(selected.path) }, "Cannot remove screensaver: " .. selected.name)
            table.insert(removed, selected.name)
        end
        return removed
    end

    return M
end
