-- Package operations retain package-manager prompts and never enable AUR implicitly.
return function(common)
    local M = {}

    function M.helper()
        for _, name in ipairs({ "yay", "paru" }) do
            if common.available(name) then
                return name
            end
        end

        error("AUR helper missing; run scripts/setup/4-setup-aur-helper.sh first")
    end

    function M.validate(name)
        assert(name:match("^[%w@._+%-]+$"), "Invalid package name: " .. name)
    end

    -- Prefix privileged package operations only when the caller is unprivileged.
    local function privileged(arguments)
        if not common.is_root() then
            assert(common.available("sudo"), "sudo is required")
            table.insert(arguments, 1, "sudo")
        end

        common.run(arguments)
    end

    function M.install(names, options)
        if #names == 0 then
            return
        end

        local pending = {}
        for _, name in ipairs(names) do
            M.validate(name)
            if options.force or not common.succeeds({ "pacman", "-Q", "--", name }) then
                table.insert(pending, name)
            else
                common.info("Already installed: " .. name)
            end
        end

        if #pending == 0 then
            return
        end

        local arguments
        if options.aur then
            assert(not common.is_root(), "AUR installation must run as a normal user")
            arguments = { M.helper(), "-S", "--aur" }
        else
            arguments = { "pacman", "-Syu" }
        end

        -- Only the menu adapter opts into unattended package confirmations.
        if options.menu_confirm then
            table.insert(arguments, "--noconfirm")
            if options.aur and arguments[1] == "yay" then
                for _, value in ipairs({ "--answerclean", "None", "--answerdiff", "None", "--answeredit", "None", "--sudoloop" }) do
                    table.insert(arguments, value)
                end
            end
        end
        if not options.force then
            table.insert(arguments, "--needed")
        end
        table.insert(arguments, "--")
        for _, name in ipairs(pending) do
            table.insert(arguments, name)
        end

        if options.aur then
            common.run(arguments)
        else
            privileged(arguments)
        end

        for _, name in ipairs(pending) do
            assert(common.succeeds({ "pacman", "-Q", "--", name }), "Package not installed: " .. name)
        end
    end

    -- Read ownership once per listing instead of launching pacman for every font.
    function M.owners()
        local output, ok = common.capture({ "env", "LC_ALL=C", "pacman", "-Ql" })
        assert(ok, "Cannot read installed package files")
        local owners = {}
        for line in output:gmatch("[^\n]+") do
            local name, path = line:match("^(%S+) (.+)$")
            if path and (path:lower():match("%.ttf$") or path:lower():match("%.otf$") or path:lower():match("%.ttc$")) then
                owners[path] = name
            end
        end

        return owners
    end

    function M.source(name)
        -- Foreign packages can be from AUR or a manually installed package archive.
        return common.succeeds({ "pacman", "-Qm", "--", name }) and "foreign" or "pacman"
    end

    function M.remove(names, options)
        if #names == 0 then
            return
        end

        local arguments = { "pacman", "-R" }
        if options and options.menu_confirm then
            table.insert(arguments, "--noconfirm")
        end
        table.insert(arguments, "--")
        for _, name in ipairs(names) do
            M.validate(name)
            table.insert(arguments, name)
        end

        -- No recursive dependency removal: pacman previews the selected packages.
        privileged(arguments)
    end

    return M
end
