-- Search live package catalogs, placing official repository results first.
return function(common, packages, json)
    local function collect(arguments, entries)
        local output, ok, code = common.capture(arguments)
        assert(ok or code == 1 and output == "", "Font search failed")
        local current
        local count = 0

        -- Native -Ss output uses a package header followed by its description.
        for line in output:gmatch("[^\n]+") do
            local repository, name = line:match("^(%S+)/(%S+)%s")
            if repository then
                current = { repository = repository, name = name, installed = line:find("[installed", 1, true) ~= nil }
            elseif current and line:match("^%s") then
                local description = line:match("^%s*(.*)")
                local text = (current.name .. " " .. description):lower()
                if text:find("font", 1, true) or text:find("typeface", 1, true) then
                    current.description = description
                    current.installed = current.installed or false
                    table.insert(entries, current)
                    count = count + 1
                end
                current = nil
            end
        end

        return count
    end

    return function(options)
        local entries = {}
        collect({ "env", "LC_ALL=C", "pacman", "-Ss", "--color", "never", "--", options.query }, entries)

        local warning = ""
        if options.aur then
            local ok, message = pcall(function()
                local helper = packages.helper()
                local arguments = { "env", "LC_ALL=C", helper, "-Ss", "--aur", "--color", "never" }
                if helper == "yay" then
                    table.insert(arguments, "--doublelineresults")
                end
                table.insert(arguments, "--")
                table.insert(arguments, options.query)
                collect(arguments, entries)
            end)
            if not ok then
                if not options.json then
                    error(message)
                end
                warning = "AUR search unavailable; showing repository results."
            end
        end

        if options.json then
            common.info('{"results":' .. json.encode(entries, true) .. ',"warning":' .. json.encode(warning) .. '}')
        else
            for _, entry in ipairs(entries) do
                common.info(string.format("[%s] %s\n  %s", entry.repository, entry.name, entry.description))
            end
            if #entries == 0 then
                common.info("No matching font packages. Search uses configured pacman catalogs; add --aur to include AUR.")
            end
        end
    end
end
