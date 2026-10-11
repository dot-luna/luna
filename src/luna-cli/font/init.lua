-- Register font commands and coordinate package and user-file operations.
return function(common, module_dir)
    local packages = dofile(module_dir .. "/packages.lua")(common)
    local local_fonts = dofile(module_dir .. "/local.lua")(common)
    local search = dofile(module_dir .. "/search.lua")(common, packages)
    local M = {}

    function M.register(parser)
        local font = parser:command("font", "Search, install, list, and remove fonts.")
        font:require_command(false)

        local find = font:command("search", "Search configured pacman catalogs; optionally include AUR.")
        find:argument("query", "Font name or search expression")
        find:flag("--aur", "Include AUR results after official repository results")

        local install = font:command("install", "Install packages, font files, or folders in one batch.")
        install:argument("targets", "Package names or local paths"):args("+")
        install:flag("--aur", "Use AUR for package targets; local paths are unaffected")
        install:flag("-r --recursive", "Scan font folders recursively")
        install:flag("--force", "Reinstall packages and local font files")

        local remove = font:command("remove", "Resolve names to font packages or user font files.")
        remove:argument("names", "Package name, font family, filename, or installed path"):args("+")

        font:command("list", "List installed font families, styles, files, and sources.")
        font:command("refresh", "Refresh the font cache.")

        return font
    end

    local function require_tools(names)
        for _, name in ipairs(names) do
            assert(common.available(name), "Missing command: " .. name .. "; install fontconfig/core dependencies")
        end
    end

    -- Fontconfig reveals actual installed families, including manually added files.
    local function installed()
        local output, ok = common.capture({ "fc-list", "--format", "%{file}\t%{family}\t%{style}\n" })
        assert(ok, "Cannot list installed fonts")
        local entries = {}
        for line in output:gmatch("[^\n]+") do
            local path, family, style = line:match("^(.-)\t(.-)\t(.*)$")
            if path then
                table.insert(entries, { path = path, family = family, style = style })
            end
        end
        table.sort(entries, function(a, b)
            return a.family .. a.style .. a.path < b.family .. b.style .. b.path
        end)

        return entries
    end

    local function family_matches(families, name)
        for family in families:gmatch("[^,\n]+") do
            if family:match("^%s*(.-)%s*$"):lower() == name:lower() then
                return true
            end
        end

        return false
    end

    local function list()
        local sources = {}
        local owners = packages.owners()
        common.info("SOURCE\tFAMILY\tSTYLE\tFILE")
        for _, entry in ipairs(installed()) do
            local owner = owners[entry.path]
            local source = "local"
            if owner then
                sources[owner] = sources[owner] or packages.source(owner) .. ":" .. owner
                source = sources[owner]
            end
            common.info(table.concat({ source, entry.family, entry.style, entry.path }, "\t"))
        end
    end

    local function install(options)
        local package_names, paths = {}, {}
        for _, target in ipairs(options.targets) do
            if local_fonts.is_path(target) then
                table.insert(paths, target)
            else
                packages.validate(target)
                table.insert(package_names, target)
            end
        end

        -- Validate all local input and helper requirements before modifying anything.
        local plan = local_fonts.plan(paths, options.recursive, options.force)
        if options.aur and #package_names > 0 then
            packages.helper()
            assert(not common.is_root(), "AUR installation must run as a normal user")
        end

        packages.install(package_names, options)
        local_fonts.install(plan, options.force)
        local_fonts.refresh()
    end

    local function remove(options)
        local selected_local, selected_packages = {}, {}
        local entries = installed()
        local owners = packages.owners()

        -- Resolve the whole batch first: ambiguous or unknown names cause no removal.
        for _, name in ipairs(options.names) do
            local choices = {}
            for _, entry in ipairs(entries) do
                local filename = entry.path:match("([^/]+)$")
                if not owners[entry.path] and local_fonts.removable(entry.path)
                    and (entry.path == name or filename == name or family_matches(entry.family, name)) then
                    -- Family matches group weights in one folder; exact paths disambiguate.
                    local key = "local:" .. (entry.path == name and entry.path or entry.path:match("^(.*)/"))
                    choices[key] = choices[key] or { paths = {} }
                    choices[key].paths[entry.path] = true
                end
            end

            -- Exact package removal also works when fontconfig's cache is stale.
            if name:match("^[%w@._+%-]+$") and common.succeeds({ "pacman", "-Q", "--", name }) then
                local files, ok = common.capture({ "pacman", "-Qlq", "--", name }, true)
                if ok and (files:lower():match("%.ttf\n") or files:lower():match("%.otf\n") or files:lower():match("%.ttc\n")) then
                    choices["package:" .. name] = { package = name }
                end
            end

            -- Exact package names and installed family names both identify owners.
            for _, entry in ipairs(entries) do
                local owner = owners[entry.path]
                if owner and (owner == name or family_matches(entry.family, name)) then
                    choices["package:" .. owner] = { package = owner }
                end
            end

            local keys = {}
            for key in pairs(choices) do
                table.insert(keys, key)
            end
            table.sort(keys)
            assert(#keys > 0, "No removable user font or installed font package matches: " .. name)
            assert(#keys == 1, "Ambiguous font '" .. name .. "': " .. table.concat(keys, ", ") .. "; use a package name or full installed file path")

            local choice = choices[keys[1]]
            if choice.package then
                selected_packages[choice.package] = true
            else
                for path in pairs(choice.paths) do
                    selected_local[path] = true
                end
            end
        end

        local package_names = {}
        for name in pairs(selected_packages) do
            table.insert(package_names, name)
        end
        table.sort(package_names)

        common.info("Removal plan (packages may contain multiple font families):")
        for _, name in ipairs(package_names) do
            common.info("  [" .. packages.source(name) .. "] " .. name)
        end
        local paths = {}
        for path in pairs(selected_local) do
            table.insert(paths, path)
        end
        table.sort(paths)
        for _, path in ipairs(paths) do
            common.info("  [local] " .. path)
        end

        io.stdout:write("Remove these fonts? [y/N] ")
        io.stdout:flush()
        local answer = io.read("*l")
        if not answer or (answer:lower() ~= "y" and answer:lower() ~= "yes") then
            common.info("Removal cancelled.")
            return
        end

        packages.remove(package_names)
        for _, path in ipairs(paths) do
            assert(local_fonts.removable(path), "Font is no longer in a user font directory: " .. path)
            assert(os.remove(path))
        end
        local_fonts.refresh()
    end

    function M.run(options)
        if options.search then
            require_tools({ "pacman" })
            search(options)
        else
            require_tools({ "fc-list", "fc-scan", "fc-cache", "pacman" })
            if options.install then
                install(options)
            elseif options.remove then
                remove(options)
            elseif options.list then
                list()
            elseif options.refresh then
                local_fonts.refresh()
            end
        end
    end

    return M
end
