-- Search live package catalogs, placing official repository results first.
return function(common, packages)
    local function show(arguments)
        local output, ok, code = common.capture(arguments)
        assert(ok or code == 1 and output == "", "Font search failed")
        local current
        local count = 0

        -- Native -Ss output uses a package header followed by its description.
        for line in output:gmatch("[^\n]+") do
            local repository, name = line:match("^(%S+)/(%S+)%s")
            if repository then
                current = { repository = repository, name = name }
            elseif current and line:match("^%s") then
                local description = line:match("^%s*(.*)")
                local text = (current.name .. " " .. description):lower()
                if text:find("font", 1, true) or text:find("typeface", 1, true) then
                    common.info(string.format("[%s] %s\n  %s", current.repository, current.name, description))
                    count = count + 1
                end
                current = nil
            end
        end

        return count
    end

    return function(options)
        local count = show({ "env", "LC_ALL=C", "pacman", "-Ss", "--color", "never", "--", options.query })

        if options.aur then
            local helper = packages.helper()
            local arguments = { "env", "LC_ALL=C", helper, "-Ss", "--aur", "--color", "never" }
            if helper == "yay" then
                table.insert(arguments, "--doublelineresults")
            end
            table.insert(arguments, "--")
            table.insert(arguments, options.query)
            count = count + show(arguments)
        end

        if count == 0 then
            common.info("No matching font packages. Search uses configured pacman catalogs; add --aur to include AUR.")
        end
    end
end
