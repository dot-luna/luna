-- Wallpaper runtime control, shared by API callers instead of owned by the CLI.
-- Target only this app's Quickshell instance; persistence belongs to the config API.
return function(common, root, renderer)
    local shell = dofile(root .. "/lib/quickshell.lua")(common, root, renderer, "wallpaper", "Wallpaper")
    local M = { stop = shell.stop }

    local function check_session()
        assert(common.available("qs"), "Quickshell is missing; install core dependencies")
        assert(os.getenv("WAYLAND_DISPLAY") and os.getenv("WAYLAND_DISPLAY") ~= "",
            "Wallpaper rendering requires a Wayland session")
    end

    local function launch()
        check_session()
        -- The renderer outlives its caller. Give it a separate session so cancelling
        -- a QML bridge request cannot terminate the desktop wallpaper it started.
        local output, ok = common.capture({ "/usr/bin/setsid", "qs", "-p", shell.path(), "--daemonize", "--no-duplicate" })
        assert(ok, "Could not start wallpaper renderer: " .. output)
    end

    function M.start()
        launch()
    end

    function M.restart()
        check_session()
        M.stop()
        launch()
    end

    -- Commands share a bounded registration wait, including when the app starts cold.
    local function request(method)
        launch()
        for _ = 1, 100 do
            local _, ok = shell.ipc(method)
            if ok then
                return
            end
            common.run({ "sleep", "0.1" })
        end
        error("Wallpaper renderer did not become available")
    end

    -- Report stopped without launching anything; other results describe the live renderer.
    function M.status()
        local status, ok = shell.ipc("status")
        return ok and status:match("^%s*(.-)%s*$") or "stopped"
    end

    -- Config parsing, probing, and decoding each have bounded startup deadlines.
    -- Allow sixty seconds overall; callers decide how a failed operation is handled.
    local function wait_ready()
        for _ = 1, 600 do
            local status = M.status()
            if status == "ready" then
                return true
            elseif status == "error" then
                return false
            end
            common.run({ "sleep", "0.1" })
        end
        return false
    end

    -- Apply manual TOML edits in the running process. Failed reads use its dark fallback.
    function M.reload()
        request("reload")
        assert(wait_ready(), "Wallpaper could not reload its config; check the wallpaper logs")
    end

    return M
end
