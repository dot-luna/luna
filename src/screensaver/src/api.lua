-- Public screensaver API, shared by Lua, QML, and the command-line adapter.
-- Imports are passive; config edits never start or reconfigure the controller.
return function(common, root, locked)
    local directory = root .. "/src/screensaver/src"
    local json = dofile(root .. "/lib/json.lua")
    local config = dofile(directory .. "/config.lua")(common, root)
    local runtime = dofile(directory .. "/runtime.lua")(common, root,
        directory .. "/shell/controller.qml", config)
    local library = dofile(directory .. "/library.lua")(common, root)

    local M = {
        getConfig = config.get,
        updateConfig = config.update,
        getConfigFile = config.file,
        start = runtime.start,
        stop = runtime.stop,
        restart = runtime.restart,
        reload = runtime.reload,
        status = runtime.status,
        getState = runtime.getState,
        show = runtime.show,
        hide = runtime.hide,
        setStayAwake = runtime.setStayAwake,
        toggleStayAwake = runtime.toggleStayAwake,
        getDirectory = library.getDirectory,
    }

    local function canonical(path)
        if path == "" then
            path = directory .. "/shell/shell.qml"
        elseif path:sub(1, 2) == "~/" then
            path = assert(os.getenv("HOME"), "HOME is not set") .. path:sub(2)
        end
        -- Missing selected files should not hide otherwise usable library entries.
        local output, ok = common.capture({ "realpath", "-m", "--", path }, true)
        assert(ok, "Could not resolve screensaver path")
        return (output:gsub("\n$", ""))
    end

    -- Disk edits do not reload the controller. Protect both its applied selection
    -- and the saved choice, including a hidden renderer waiting for the next idle.
    local function protected_paths()
        local paths = { canonical(config.get("renderer.shell")) }
        local applied = runtime.getRendererShell()
        if applied then
            table.insert(paths, canonical(applied))
        end
        return paths
    end

    function M.list()
        local selected = canonical(config.get("renderer.shell"))
        local entries = library.list()
        for _, entry in ipairs(entries) do
            entry.current = canonical(entry.path) == selected
        end
        return entries
    end

    function M.install(source, options)
        options = options == nil and {} or options
        assert(type(options) == "table", "Install options must be an object")
        return library.install(source, { name = options.name, force = options.force,
            protectedPaths = options.force == true and protected_paths() or nil })
    end

    function M.set(target)
        local entry = library.resolve(target)
        local previous = config.get("renderer.shell")
        config.update({ renderer = { shell = entry.selection } })
        local ok, message = pcall(runtime.reload)
        if not ok then
            local restored, failure = pcall(config.update, { renderer = { shell = previous } })
            if restored then
                local reapplied, reload_error = pcall(runtime.reload)
                if not reapplied then
                    message = tostring(message) .. "\nPrevious selection saved; reload failed: " .. tostring(reload_error)
                end
            else
                message = tostring(message) .. "\nCould not restore previous selection: " .. tostring(failure)
            end
            error(message, 0)
        end
        entry.current = true
        return entry
    end

    function M.removalPlan(names)
        return library.removalPlan(names, protected_paths())
    end

    function M.remove(names)
        return library.remove(names, protected_paths())
    end

    -- Serialize selection, controller startup and file changes together. Checking
    -- the current shell outside this lock would let concurrent removal delete a
    -- newly selected package. flock releases its lock even if a caller exits.
    if not locked then
        for _, method in ipairs({ "install", "set", "remove", "updateConfig",
            "start", "restart", "reload", "show", "setStayAwake", "toggleStayAwake" }) do
            M[method] = function(...)
                local request = json.encode({ method = method, arguments = json.array({ ... }) })
                local parent = assert(library.getDirectory():match("^(.*)/[^/]+$"))
                assert(not common.succeeds({ "test", "-L", parent }),
                    "Screensaver data directory cannot be a symlink")
                assert(common.succeeds({ "mkdir", "-p", "--", parent }),
                    "Could not create screensaver data directory")
                local lock = parent .. "/.screensaver.lock"
                assert(not common.succeeds({ "test", "-L", lock }), "Screensaver lock cannot be a symlink")
                -- Detached controllers must never inherit the lock descriptor.
                local output, ok = common.capture({ "flock", "--exclusive", "--close", "--timeout", "30", "--",
                    lock, "/usr/bin/lua", "-E", directory .. "/bridge.lua", request, "--locked" }, true)
                local decoded, response = pcall(json.decode, output)
                assert(decoded and type(response) == "table",
                    "Could not complete screensaver command; another command may still be running")
                assert(ok and response.ok, response.error or "Screensaver command failed")
                if response.result ~= json.null then
                    return response.result
                end
            end
        end
    end

    return M
end
