-- Own only Luna's wallpaper Quickshell instance; preserve other shell components.
return function(common, renderer)
    local M = {}
    local home = assert(os.getenv("HOME"), "HOME is required")
    local config = (os.getenv("XDG_CONFIG_HOME") or home .. "/.config") .. "/luna"
    M.selection = config .. "/wallpaper"

    function M.current()
        local file = io.open(M.selection, "r")
        if not file then
            return nil
        end
        local path = file:read("*l")
        file:close()
        return path ~= "" and path or nil
    end

    local function ipc(method, path)
        local arguments = { "qs", "ipc", "-p", renderer, "call", "wallpaper", method }
        if path then
            table.insert(arguments, path)
        end
        return common.capture(arguments, true)
    end

    function M.start()
        assert(common.available("qs"), "Quickshell is missing; install core dependencies")
        assert(os.getenv("WAYLAND_DISPLAY"), "Wallpaper rendering requires a Wayland session")
        common.run({ "qs", "-p", renderer, "--daemonize", "--no-duplicate" })
    end

    function M.apply(path)
        M.start()

        -- Wait briefly for IPC registration after starting a new instance.
        local ready = false
        for _ = 1, 30 do
            local _, ok = ipc("set", path)
            if ok then
                ready = true
                break
            end
            common.run({ "sleep", "0.1" })
        end
        assert(ready, "Wallpaper renderer did not become available")

        -- Persist only after Qt successfully decodes the image. Restore on failure.
        for _ = 1, 30 do
            local status, ok = ipc("status")
            if ok and status:match("ready") then
                common.run({ "mkdir", "-p", "--", config })
                local file = assert(io.open(M.selection .. ".tmp", "w"))
                assert(file:write(path, "\n"))
                assert(file:close())
                assert(os.rename(M.selection .. ".tmp", M.selection))
                common.info("Wallpaper set: " .. path)
                return
            end
            if ok and status:match("error") then
                break
            end
            common.run({ "sleep", "0.1" })
        end

        ipc("set", M.current() or "")
        error("Quickshell could not load the wallpaper; previous selection preserved")
    end

    return M
end
