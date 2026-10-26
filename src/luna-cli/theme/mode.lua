-- Publish the per-user appearance preference through GSettings and GTK settings.
return function(common, ini)
    local M = {}
    local home = assert(os.getenv("HOME"), "HOME is required")
    local config = os.getenv("XDG_CONFIG_HOME") or home .. "/.config"
    local saved = config .. "/luna/theme-mode"
    local schema, key = "org.gnome.desktop.interface", "color-scheme"

    local function preference()
        assert(common.available("gsettings"), "gsettings is missing; install core dependencies")
        local value, ok = common.capture({ "gsettings", "get", schema, key }, true)
        assert(ok, "Desktop color-scheme is unavailable; install gsettings-desktop-schemas and run in your user session")
        local parsed = value:match("'([%w-]+)'")
        assert(parsed == "default" or parsed == "prefer-dark" or parsed == "prefer-light", "Unknown desktop color-scheme")
        return parsed
    end

    function M.current(fallback)
        local value = preference()
        if value == "prefer-dark" then
            return "dark"
        elseif value == "prefer-light" then
            return "light"
        end
        local file = io.open(saved, "r")
        if file then
            local mode = file:read("*l")
            file:close()
            if mode == "dark" or mode == "light" then
                return mode
            end
        end
        return fallback or "light"
    end

    local function read(path)
        local file = io.open(path, "r")
        if not file then
            assert(not common.succeeds({ "test", "-e", path }), "Cannot read settings: " .. path)
            return nil
        end
        local content = file:read("*a")
        assert(file:close())
        return content
    end

    function M.apply(mode, force)
        assert(mode == "dark" or mode == "light", "Mode must be dark or light")
        local previous = preference()

        -- Read all originals before making changes; existing application settings survive.
        local changes = {}
        for _, version in ipairs({ "gtk-3.0", "gtk-4.0" }) do
            local path = config .. "/" .. version .. "/settings.ini"
            local old = read(path)
            table.insert(changes, {
                path = path, old = old,
                content = ini.set(old or "", "Settings", "gtk-application-prefer-dark-theme", mode == "dark" and "1" or "0"),
            })
        end
        table.insert(changes, { path = saved, old = read(saved), content = mode .. "\n" })

        local matches = previous == "prefer-" .. mode
        for _, change in ipairs(changes) do
            change.needed = force or change.old ~= change.content
            matches = matches and not change.needed
        end
        if matches and not force then
            common.info("System appearance already set: " .. mode)
            return function() end
        end
        local change_preference = force or previous ~= "prefer-" .. mode
        if change_preference then
            local writable, ok = common.capture({ "gsettings", "writable", schema, key }, true)
            assert(ok and writable:match("^true%s*$"), "Desktop color-scheme is not writable")
        end

        local preference_changed = false

        local function restore()
            if preference_changed then
                local _, restored = common.capture({ "gsettings", "set", schema, key, previous }, true)
                if not restored then
                    common.error("Could not restore the previous desktop color-scheme")
                end
            end
            for _, change in ipairs(changes) do
                if change.committed then
                    if change.old then
                        common.replace_file(change.path, change.old)
                    else
                        assert(os.remove(change.path))
                    end
                end
            end
        end

        local success, message = pcall(function()
            for _, change in ipairs(changes) do
                if change.needed then
                    common.run({ "mkdir", "-p", "--", change.path:match("^(.*)/") })
                    change.staged = common.stage_file(change.path, change.content)
                end
            end
            if change_preference then
                preference_changed = true
                common.run({ "gsettings", "set", schema, key, "prefer-" .. mode })
            end
            assert(preference() == "prefer-" .. mode, "Desktop color-scheme was not saved")
            for _, change in ipairs(changes) do
                if change.needed then
                    assert(os.rename(change.staged, change.path))
                    change.staged = nil
                    change.committed = true
                end
            end
        end)
        if not success then
            local restored, failure = pcall(restore)
            if not restored then
                common.error("Could not fully restore appearance settings: " .. tostring(failure))
            end
        end
        for _, change in ipairs(changes) do
            if change.staged then
                os.remove(change.staged)
            end
        end
        assert(success, message)
        return restore
    end

    return M
end
