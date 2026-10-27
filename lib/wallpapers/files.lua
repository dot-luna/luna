-- Luna's media library, shared by wallpaper commands and theme installation.
-- Import and discover ordinary files without controlling the wallpaper renderer.
return function(common, download)
    local M = {}
    local home = assert(os.getenv("HOME"), "HOME is required")
    local data_home = os.getenv("XDG_DATA_HOME")
    M.directory = (data_home and data_home ~= "" and data_home or home .. "/.local/share") .. "/luna/wallpapers"
    local extensions = { png = true, jpg = true, jpeg = true, webp = true, bmp = true, svg = true,
        gif = true, apng = true, avif = true, mp4 = true, m4v = true, webm = true,
        mkv = true, mov = true, avi = true, ogv = true }

    local function supported(path)
        return extensions[path:lower():match("%.(%w+)$")] == true
    end

    function M.validate(path)
        assert(common.succeeds({ "test", "-f", path }), "Media file not found: " .. path)
        assert(not path:find("[%z\1-\31]"), "Wallpaper paths cannot contain control characters")
        -- Inspect actual bytes so set accepts images, animations, and videos regardless
        -- of their extension. Folder scanning uses common extensions to skip other files.
        local mime, ok = common.capture({ "file", "--brief", "--mime-type", "--", path })
        assert(ok and (mime:match("^image/") or mime:match("^video/")), "Not image or video media: " .. path)
    end

    function M.absolute(path)
        local output, ok = common.capture({ "realpath", "-e", "--", path }, true)
        assert(ok, "Path not found: " .. path)
        return output:gsub("\n$", "")
    end

    -- Folder imports filter common suffixes. The library includes every imported
    -- file, since direct imports are validated by content and may have no suffix.
    local function scan(directory, recursive, filter_extensions)
        local arguments = { "find", directory }
        if not recursive then
            table.insert(arguments, "-maxdepth")
            table.insert(arguments, "1")
        end
        for _, value in ipairs({ "-type", "f", "-print0" }) do
            table.insert(arguments, value)
        end
        local output, ok = common.capture(arguments)
        assert(ok, "Cannot scan folder: " .. directory)
        local paths = {}
        for path in output:gmatch("([^%z]+)%z") do
            if not filter_extensions or supported(path) then
                table.insert(paths, path)
            end
        end
        table.sort(paths)
        return paths
    end

    function M.list()
        if not common.succeeds({ "test", "-d", M.directory }) then
            return {}
        end
        return scan(M.directory, true)
    end

    function M.resolve(name, library_only)
        local matches = {}
        for _, path in ipairs(M.list()) do
            if path == name or path:match("([^/]+)$") == name then
                table.insert(matches, path)
            end
        end

        if not library_only and #matches == 0 and common.succeeds({ "test", "-f", name }) then
            return M.absolute(name)
        end
        assert(#matches > 0, "Wallpaper not found: " .. name)
        assert(#matches == 1, "Ambiguous wallpaper; use its full library path: " .. name)
        return matches[1]
    end

    -- Pick another library entry when possible; applying it belongs to the wallpaper API.
    function M.random(current)
        local choices = M.list()
        assert(#choices > 0, "Wallpaper library is empty")
        if #choices > 1 then
            for index = #choices, 1, -1 do
                if choices[index] == current then
                    table.remove(choices, index)
                end
            end
        end
        return choices[math.random(#choices)]
    end

    -- Resolve the whole batch before a prompt or deletion. Never remove external
    -- files or the saved wallpaper; callers provide current state from the app API.
    function M.removalPlan(names, current)
        local paths, seen = {}, {}
        for _, name in ipairs(names) do
            local path = M.resolve(name, true)
            assert(M.absolute(path) ~= current, "Select another wallpaper before removing the current image")
            if not seen[path] then
                table.insert(paths, path)
                seen[path] = true
            end
        end
        return paths
    end

    function M.remove(names, current)
        for _, path in ipairs(M.removalPlan(names, current)) do
            assert(os.remove(path))
        end
    end

    local function add_local(options)
        local plan, seen = {}, {}
        for _, input in ipairs(options.targets) do
            local source = M.absolute(input)
            local paths = { source }
            if common.succeeds({ "test", "-d", source }) then
                paths = scan(source, options.recursive, true)
                assert(#paths > 0, "No supported images in folder: " .. input)
            end

            -- Validate the batch and filename conflicts before copying anything.
            for _, path in ipairs(paths) do
                M.validate(path)
                local name = path:match("([^/]+)$")
                local destination = M.directory .. "/" .. name
                if seen[name] then
                    assert(common.succeeds({ "cmp", "-s", "--", seen[name], path }),
                        "Different images share a filename: " .. name)
                else
                    seen[name] = path
                    if common.succeeds({ "test", "-e", destination }) and not options.force then
                        assert(common.succeeds({ "cmp", "-s", "--", path, destination }),
                            "Different image already installed: " .. name .. "; rename it or use --force")
                    end
                    table.insert(plan, { source = path, destination = destination })
                end
            end
        end

        common.run({ "mkdir", "-p", "--", M.directory })
        for _, entry in ipairs(plan) do
            local same = common.succeeds({ "test", entry.source, "-ef", entry.destination })
            if same or not options.force and common.succeeds({ "test", "-f", entry.destination }) then
                common.info("Already installed: " .. entry.destination)
            else
                common.run({ "cp", "--", entry.source, entry.destination })
                common.info("Added: " .. entry.destination)
            end
        end
    end

    function M.add(options)
        local has_urls = false
        for _, input in ipairs(options.targets) do
            has_urls = has_urls or download.is_url(input)
        end
        if not has_urls then
            return add_local(options)
        end

        download.prepare()
        local temporary, ok = common.capture({ "mktemp", "-d" })
        assert(ok, "Cannot create a temporary download directory")
        temporary = temporary:gsub("\n$", "")

        -- Always clean staged downloads, including network or batch-validation failures.
        local success, message = pcall(function()
            local staged = { targets = {}, force = options.force, recursive = options.recursive }
            for index, input in ipairs(options.targets) do
                table.insert(staged.targets, download.is_url(input)
                    and download.fetch(input, temporary, index) or input)
            end
            add_local(staged)
        end)
        common.run({ "rm", "-rf", "--", temporary })
        assert(success, message)
    end

    return M
end
