-- Own the independent idle controller, never the user's rendering shell directly.
-- All process output is captured so callers can choose their own UI or encoding.
return function(common, root, controller, config)
    local json = dofile(root .. "/lib/json.lua")
    local shell = dofile(root .. "/lib/quickshell.lua")(common, root, controller,
        "screensaver", "Screensaver")
    config = config or dofile(root .. "/src/screensaver/src/config.lua")(common, root)
    local M = {}

    -- Bound individual requests as well as readiness loops. A wedged renderer
    -- cannot block the separate idle controller, and a wedged controller times out.
    local function ipc(method, argument)
        -- "show" is also a qs subcommand; terminate option parsing before our target.
        local command = { "/usr/bin/timeout", "--kill-after=1s", "1s", "qs", "ipc",
            "-p", shell.path(), "call", "--", "screensaver", method }
        if argument ~= nil then
            table.insert(command, tostring(argument))
        end
        return common.capture(command, true)
    end

    local function running()
        local value, ok = ipc("ping")
        return ok and value:match("^%s*(.-)%s*$") == "ready"
    end

    local function check_session()
        assert(common.available("qs"), "Quickshell is missing; install core dependencies")
        assert(os.getenv("WAYLAND_DISPLAY") and os.getenv("WAYLAND_DISPLAY") ~= "",
            "Screensaver requires a Wayland session")
    end

    -- Resolve both inputs before changing a working controller. The theme is a
    -- shared snapshot, while user settings stay separate from visual implementation.
    local function prepare()
        check_session()
        local resolved = config.get()
        local snapshot = dofile(root .. "/lib/theme/shell.lua")(root).snapshot()
        return { config = resolved, theme = json.decode(snapshot) }, snapshot
    end

    local function wait_for(predicate, seconds)
        local deadline = os.time() + seconds
        for _ = 1, seconds * 10 do
            if predicate() then
                return true
            end
            if os.time() >= deadline then
                return false
            end
            common.run({ "sleep", "0.1" })
        end
        return false
    end

    local function launch(payload, snapshot)
        if running() then
            return
        end
        local imports = root .. "/src/qml"
        if os.getenv("QML_IMPORT_PATH") and os.getenv("QML_IMPORT_PATH") ~= "" then
            imports = imports .. ":" .. os.getenv("QML_IMPORT_PATH")
        end
        -- Detach from short-lived QML bridge requests so cancelling the caller
        -- cannot terminate idle monitoring or its future automatic lock action.
        local output, ok = common.capture({ "/usr/bin/setsid", "env",
            "LUNA_UI_THEME=" .. snapshot, "LUNA_SCREENSAVER_SETTINGS=" .. json.encode(payload.config),
            "QML_IMPORT_PATH=" .. imports, "qs", "-p", shell.path(), "--daemonize", "--no-duplicate" })
        assert(ok, "Could not start screensaver controller: " .. output:match("^%s*(.-)%s*$"))
        assert(wait_for(running, 10), "Screensaver controller did not become available")
    end

    function M.start()
        local payload, snapshot = prepare()
        launch(payload, snapshot)
    end

    function M.stop()
        if running() then
            ipc("shutdown")
            wait_for(function() return not running() end, 5)
        end
        -- Confirm shutdown and clean up unresponsive/partly-started instances.
        -- The shared helper matches the canonical controller path, never all qs.
        shell.stop()
    end

    function M.restart()
        local payload, snapshot = prepare()
        M.stop()
        launch(payload, snapshot)
    end

    function M.status()
        local value, ok = ipc("status")
        if not ok then
            assert(not running(), "Could not read screensaver status")
            return "stopped"
        end
        value = value:match("^%s*(.-)%s*$")
        assert(({ idle = true, loading = true, showing = true, error = true })[value],
            "Invalid screensaver status")
        return value
    end

    local function decode_state(output)
        local ok, value = pcall(json.decode, output)
        assert(ok and type(value) == "table" and value.running == true
            and type(value.active) == "boolean" and type(value.stayAwake) == "boolean"
            and type(value.outputsOff) == "boolean" and type(value.error) == "string"
            and ({ hidden = true, loading = true, ready = true, error = true })[value.rendererState],
            "Invalid screensaver state")
        return value
    end

    function M.getState()
        local output, ok = ipc("getState")
        if not ok then
            assert(not running(), "Could not read screensaver state")
            return { running = false, active = false, stayAwake = false, outputsOff = false,
                rendererState = "hidden", error = "" }
        end
        return decode_state(output)
    end

    -- Used internally by library mutations; never starts an idle controller.
    function M.getRendererShell()
        local output, ok = ipc("getRendererShell")
        if not ok then
            assert(not running(), "Could not read applied screensaver shell")
            return nil
        end
        local path = output:gsub("\n$", "")
        assert(path:sub(1, 1) == "/" and not path:find("[\r\n%z]"),
            "Invalid applied screensaver shell")
        return path
    end

    local function wait_visible()
        assert(wait_for(function()
            local status = M.status()
            if status == "error" then
                local state = M.getState()
                error("Screensaver renderer failed" .. (state.error ~= "" and ": " .. state.error or ""))
            end
            assert(status ~= "stopped", "Screensaver controller stopped while opening the shell")
            -- A locked session declines the request, and users may dismiss before
            -- the first poll. Both settle at idle without indicating a failure.
            return status == "showing" or status == "idle"
        end, 15), "Screensaver renderer did not become available")
    end

    function M.reload()
        local payload, snapshot = prepare()
        launch(payload, snapshot)
        local _, ok = ipc("configure", json.encode(payload))
        assert(ok, "Could not reload screensaver config")
        -- A fast renderer failure can already have cleared active by this point.
        -- Inspect status even when hidden so callers can roll back a failed switch.
        wait_visible()
    end

    function M.show()
        if not running() then
            M.start()
        end
        local _, ok = ipc("show")
        assert(ok, "Could not show screensaver")
        wait_visible()
    end

    function M.hide()
        if not running() then
            return
        end
        local _, ok = ipc("hide")
        assert(ok, "Could not hide screensaver")
    end

    local function awake(method, enabled)
        if not running() then
            M.start()
        end
        local output, ok = ipc(method, enabled)
        assert(ok, "Could not update Stay awake")
        return decode_state(output)
    end

    function M.setStayAwake(enabled)
        assert(type(enabled) == "boolean", "Stay awake must be a boolean")
        return awake("setStayAwake", enabled)
    end

    function M.toggleStayAwake()
        return awake("toggleStayAwake")
    end

    return M
end
