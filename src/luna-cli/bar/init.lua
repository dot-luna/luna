-- Own Luna Bar's instance through the shared themed shell lifecycle.
return function(common, directory)
    local root = directory .. "/../../.."
    local config = dofile(directory .. "/config.lua")(common, root)
    local shell = dofile(root .. "/lib/quickshell.lua")(common, root, directory .. "/../../luna-bar", "bar", "Luna Bar")
    local M = {}

    function M.register(parser)
        local command = parser:command("bar", "Start or control Luna Bar.")
        command:argument("bar_action", "Action"):args("?"):default("start")
            :choices({ "start", "reload", "stop", "serve", "focus", "controls", "notifications", "dnd", "notificationStatus", "clearNotifications" })
        return command
    end

    function M.run(options)
        local action = options.bar_action or "start"
        local environment = action ~= "stop" and { LUNA_BAR_CONFIG = config.snapshot() } or nil
        local config_home = os.getenv("XDG_CONFIG_HOME") or assert(os.getenv("HOME")) .. "/.config"
        local unit = io.open(config_home .. "/systemd/user/luna-notifications.service", "r")
        if unit then
            unit:close()
        end
        -- Once notification activation is installed, keep the bar inside its service.
        if unit and action ~= "serve" then
            if action ~= "stop" then
                dofile(root .. "/lib/theme/shell.lua")(root).snapshot()
            end
            local operation = action == "stop" and "stop" or action == "reload" and "restart" or "start"
            common.run({ "systemctl", "--user", operation, "luna-notifications.service" })
            if action == "stop" then
                return
            end
            local method = (action == "start" or action == "reload") and "ping" or action
            for _ = 1, 30 do
                local output, ready = shell.ipc(method)
                if ready then
                    if action == "notificationStatus" then common.info(output:gsub("\n$", "")) end
                    return
                end
                common.run({ "sleep", "0.1" })
            end
            error("Luna Bar did not become available; check systemctl --user status luna-notifications.service")
        end
        shell.run(action, environment)
    end

    return M
end
