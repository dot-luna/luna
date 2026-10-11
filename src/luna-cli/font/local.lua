-- Install user font files directly; fontconfig and pacman provide discovery.
return function(common)
    local M = {}
    local home = assert(os.getenv("HOME"), "HOME is required")
    local data = os.getenv("XDG_DATA_HOME") or home .. "/.local/share"
    M.directory = data .. "/fonts/luna"

    -- Only unowned fonts in user font directories can be removed as local files.
    function M.removable(path)
        local resolved, ok = common.capture({ "realpath", "-e", "--", path }, true)
        if not ok then
            return false
        end
        resolved = resolved:gsub("\n$", "")

        for _, directory in ipairs({ data .. "/fonts", home .. "/.local/share/fonts", home .. "/.fonts" }) do
            local root, found = common.capture({ "realpath", "-m", "--", directory }, true)
            root = root:gsub("\n$", "")
            if found and resolved:sub(1, #root + 1) == root .. "/" then
                return true
            end
        end

        return false
    end

    function M.refresh()
        common.run({ "fc-cache", "-f" })
    end

    local function supported(path)
        local extension = path:lower():match("%.(%w+)$")
        return extension == "ttf" or extension == "otf" or extension == "ttc"
    end

    function M.is_path(value)
        return value:find("/", 1, true) or common.succeeds({ "test", "-e", value }) or supported(value)
    end

    -- Build and validate the complete file plan before copying any fonts.
    function M.plan(inputs, recursive, force)
        local plan, seen = {}, {}

        for _, input in ipairs(inputs) do
            local absolute, ok = common.capture({ "realpath", "-e", "--", input }, true)
            assert(ok, "Local path does not exist: " .. input)
            absolute = absolute:gsub("\n$", "")
            local files = {}

            if common.succeeds({ "test", "-d", absolute }) then
                local arguments = { "find", absolute }
                if not recursive then
                    table.insert(arguments, "-maxdepth")
                    table.insert(arguments, "1")
                end
                for _, value in ipairs({ "-type", "f", "-print0" }) do
                    table.insert(arguments, value)
                end
                local output, found = common.capture(arguments)
                assert(found, "Cannot scan folder: " .. input)
                for path in output:gmatch("([^%z]+)%z") do
                    if supported(path) then
                        table.insert(files, path)
                    end
                end
                table.sort(files)
                assert(#files > 0, "No supported fonts in folder: " .. input)
            else
                assert(supported(absolute), "Expected a .ttf, .otf, or .ttc file: " .. input)
                files = { absolute }
            end

            for _, path in ipairs(files) do
                local family, scanned = common.capture({ "fc-scan", "--format", "%{family}\n", "--", path }, true)
                assert(scanned and family ~= "", "Invalid font file: " .. path)
                local name = path:match("([^/]+)$")
                local destination = M.directory .. "/" .. name

                -- Detect collisions before package installs or file copies begin.
                if seen[name] then
                    assert(common.succeeds({ "cmp", "-s", "--", seen[name], path }),
                        "Different fonts share a filename in this batch: " .. name)
                else
                    seen[name] = path
                    if common.succeeds({ "test", "-e", destination }) and not force then
                        assert(common.succeeds({ "cmp", "-s", "--", destination, path }),
                            "A different font already uses " .. name .. "; rename it or use --force")
                    end
                    table.insert(plan, { name = name, destination = destination, source = path })
                end
            end
        end

        return plan
    end

    function M.install(plan, force)
        for _, entry in ipairs(plan) do
            -- Skip matching files; --force copies again unless source is the target.
            local exists = common.succeeds({ "test", "-f", entry.destination })
            local same_file = common.succeeds({ "test", entry.source, "-ef", entry.destination })
            if same_file or exists and not force then
                common.info("Already installed [local]: " .. entry.name)
            else
                common.run({ "mkdir", "-p", "--", M.directory })
                common.run({ "cp", "--", entry.source, entry.destination })
                common.info("Installed [local]: " .. entry.name)
            end
        end
    end

    return M
end
