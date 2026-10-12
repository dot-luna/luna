-- Share themed shell lifecycle and bounded IPC startup checks between Luna tools.
return function(common, root, renderer, target, label)
    local theme = dofile(root .. "/lib/theme/shell.lua")(root)
    local M = {}

    function M.ipc(method)
        return common.capture({ "qs", "ipc", "-p", renderer, "call", target, method }, true)
    end

    function M.run(action)
        assert(type(action) == "string", "A shell action is required")
        assert(common.available("qs"), "Quickshell is missing; install core dependencies")
        assert(os.getenv("WAYLAND_DISPLAY"), label .. " requires a Wayland session")
        local snapshot
        if action ~= "stop" then
            -- Validate before stopping a working shell, so a broken theme cannot hide it.
            snapshot = theme.snapshot()
        end
        if action == "reload" or action == "stop" then
            local _, running = M.ipc("ping")
            if running then
                M.ipc("stop")
                for _ = 1, 30 do
                    local _, alive = M.ipc("ping")
                    if not alive then
                        break
                    end
                    common.run({ "sleep", "0.1" })
                end
                local _, alive = M.ipc("ping")
                assert(not alive, label .. " did not stop")
            end
            if action == "stop" then
                return
            end
        end

        local imports = root .. "/src/qml"
        if os.getenv("QML_IMPORT_PATH") then
            imports = imports .. ":" .. os.getenv("QML_IMPORT_PATH")
        end
        common.run({ "env", "LUNA_UI_THEME=" .. snapshot, "QML_IMPORT_PATH=" .. imports,
            "qs", "-p", renderer, "--daemonize", "--no-duplicate" })
        local method = (action == "start" or action == "reload") and "ping" or action
        for _ = 1, 30 do
            local _, ok = M.ipc(method)
            if ok then
                return
            end
            common.run({ "sleep", "0.1" })
        end
        error(label .. " did not become available; check qs log -p " .. renderer)
    end
    return M
end
