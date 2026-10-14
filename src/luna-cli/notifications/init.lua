-- Keep the notification provider under the user service manager; UI commands use bar IPC.
return function(common, directory)
    local root = directory .. "/../../.."
    local bar = dofile(directory .. "/../bar/init.lua")(common, directory .. "/../bar")
    local M = {}

    function M.register(parser)
        local command = parser:command("notifications", "Open notifications or manage Luna's notification service.")
        command:argument("notifications_action", "Action"):args("?"):default("open")
            :choices({ "open", "dnd", "status", "clear", "setup", "start" })
        return command
    end

    function M.run(options)
        local action = options.notifications_action or "open"
        if action == "status" then
            local output, running = common.capture({ "qs", "ipc", "-p", directory .. "/../../luna-bar",
                "call", "bar", "notificationStatus" }, true)
            common.info(running and output:gsub("\n$", "") or '{"running":false}')
            return
        end

        -- Invalid preferences must not stop the current bar or notification daemon.
        dofile(root .. "/lib/theme/shell.lua")(root).snapshot()
        dofile(directory .. "/../bar/config.lua")(common, root).snapshot()
        common.run({ "python", directory .. "/service.py", root })
        if action == "setup" or action == "start" then
            return
        end
        local methods = { open = "notifications", dnd = "dnd", clear = "clearNotifications" }
        assert(methods[action], "Unknown notifications action")
        bar.run({ bar_action = methods[action] })
    end

    return M
end
