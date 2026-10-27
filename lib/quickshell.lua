-- Shared Quickshell lifecycle: scoped shutdown, IPC, and themed app startup.
-- stop() needs neither a theme nor a desktop connection and is safe to repeat.
return function(common, root, renderer, target, label)
    local json = dofile(root .. "/lib/json.lua")
    local M = {}

    function M.ipc(method)
        return common.capture({ "qs", "ipc", "-p", M.path(), "call", target, method }, true)
    end

    -- Keep individual commands bounded so a stalled qs cannot hang a caller.
    local function command(arguments)
        local args = { "/usr/bin/timeout", "--kill-after=1s", "5s", "qs" }
        for _, argument in ipairs(arguments) do
            table.insert(args, argument)
        end
        return common.capture(args, true)
    end

    -- qs treats symlink aliases as different configs, even for the same QML file.
    local function canonical(path)
        local output, ok = common.capture({ "realpath", "-m", "--", path }, true)
        assert(ok, "Could not resolve Quickshell path: " .. path)
        return output:gsub("\n$", "")
    end

    -- Resolve lazily so importing an API does no process work. Startup, IPC, and
    -- shutdown must all use one identity through checkout and installed links.
    local resolved_path
    function M.path()
        if not resolved_path then
            resolved_path = canonical(common.succeeds({ "test", "-d", renderer }) and renderer .. "/shell.qml" or renderer)
        end
        return resolved_path
    end

    local function instances(path)
        local output, ok = command({ "list", "-a", "-j" })
        assert(ok, label .. ": could not list Quickshell instances")
        output = output:match("^%s*(.-)%s*$")
        -- qs prints plain text, even with -j, when no instances are running.
        if output == "" or output == "No running instances." then
            return {}
        end
        local result = json.decode(output)
        assert(type(result) == "table" and getmetatable(result).__json_kind == "array",
            label .. ": invalid Quickshell instance list")
        local matches = {}
        for _, instance in ipairs(result) do
            if canonical(instance.config_path) == path then
                assert(type(instance.pid) == "number" and instance.pid > 0 and instance.pid % 1 == 0,
                    "Missing Quickshell process ID")
                table.insert(matches, tostring(instance.pid))
            end
        end
        return matches
    end

    -- Kill each selected instance and confirm shutdown before restart can launch.
    -- Quickshell owns its child players and releases them during shutdown.
    function M.stop()
        assert(common.available("qs"), "Quickshell is missing; install core dependencies")
        local path = M.path()
        -- PID selection works across displays; qs still verifies ownership of the instance.
        for _, pid in ipairs(instances(path)) do
            local _, ok = command({ "kill", "--pid", pid })
            if not ok then
                -- Another caller may have stopped it between listing and killing.
                for _, remaining in ipairs(instances(path)) do
                    assert(remaining ~= pid, label .. ": could not stop Quickshell process " .. pid)
                end
            end
        end
        for _ = 1, 30 do
            if #instances(path) == 0 then
                return
            end
            common.run({ "sleep", "0.1" })
        end
        error(label .. " did not stop")
    end

    function M.run(action, environment)
        assert(type(action) == "string", "A shell action is required")
        if action == "stop" then
            return M.stop()
        end
        assert(common.available("qs"), "Quickshell is missing; install core dependencies")
        assert(os.getenv("WAYLAND_DISPLAY"), label .. " requires a Wayland session")

        -- Validate before stopping a working shell, so a broken theme cannot hide it.
        local snapshot = dofile(root .. "/lib/theme/shell.lua")(root).snapshot()
        if action == "reload" then
            M.stop()
        end

        local imports = root .. "/src/qml"
        if os.getenv("QML_IMPORT_PATH") then
            imports = imports .. ":" .. os.getenv("QML_IMPORT_PATH")
        end
        local command = { "env", "LUNA_UI_THEME=" .. snapshot, "QML_IMPORT_PATH=" .. imports }
        for key, value in pairs(environment or {}) do
            table.insert(command, key .. "=" .. value)
        end
        local renderer_command = { "qs", "-p", M.path(), "--no-duplicate" }
        if action ~= "serve" then
            table.insert(renderer_command, "--daemonize")
        end
        for _, argument in ipairs(renderer_command) do
            table.insert(command, argument)
        end
        common.run(command)
        -- D-Bus/systemd activation needs a foreground process for the shell's lifetime.
        if action == "serve" then
            return
        end
        local method = (action == "start" or action == "reload") and "ping" or action
        for _ = 1, 30 do
            local _, ok = M.ipc(method)
            if ok then
                return
            end
            common.run({ "sleep", "0.1" })
        end
        error(label .. " did not become available; check qs log -p " .. M.path())
    end
    return M
end
