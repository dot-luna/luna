-- Own the bar's Quickshell instance; manual reload takes a fresh theme snapshot.
return function(common, directory)
    local root = directory .. "/../../.."
    local renderer = directory .. "/../../bar"
    local theme = dofile(root .. "/lib/theme/shell.lua")(root)
    local M = {}

    function M.register(parser)
        local bar = parser:command("bar", "Start or control Luna Bar.")
        bar:argument("bar_action", "Action"):args("?"):default("start")
            :choices({ "start", "reload", "stop", "focus", "controls" })
        return bar
    end

    local function ipc(method)
        return common.capture({ "qs", "ipc", "-p", renderer, "call", "bar", method }, true)
    end

    function M.run(options)
        assert(common.available("qs"), "Quickshell is missing; install core dependencies")
        assert(os.getenv("WAYLAND_DISPLAY"), "Luna Bar requires a Wayland session")
        local action = options.bar_action
        local snapshot
        if action ~= "stop" then
            -- Validate before stopping a working bar, so a broken theme cannot hide it.
            snapshot = theme.snapshot()
        end
        if action == "reload" or action == "stop" then
            local _, running = ipc("ping")
            if running then
                ipc("stop")
                for _ = 1, 30 do
                    local _, alive = ipc("ping")
                    if not alive then
                        break
                    end
                    common.run({ "sleep", "0.1" })
                end
                local _, alive = ipc("ping")
                assert(not alive, "Bar did not stop")
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
        local method = (action == "focus" or action == "controls") and action or "ping"
        for _ = 1, 30 do
            local _, ok = ipc(method)
            if ok then
                return
            end
            common.run({ "sleep", "0.1" })
        end
        error("Bar did not become available; check qs log -p " .. renderer)
    end

    return M
end
