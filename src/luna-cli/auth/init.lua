-- Keep desktop authorization in its own supervised, themed Quickshell process.
return function(common, directory)
    local root = directory .. "/../../.."
    local shell = dofile(root .. "/lib/quickshell.lua")(common, root,
        directory .. "/../../luna-polkit/src/shell", "auth", "Luna authentication")
    local M = {}

    function M.register(parser)
        local command = parser:command("auth", "Manage Luna administrator password prompts.")
        command:argument("auth_action", "Action"):args("?"):default("start")
            :choices({ "start", "status", "stop", "restart", "serve" })
        return command
    end

    function M.run(options)
        local action = options.auth_action or "start"
        if action == "serve" then
            shell.run("serve")
            return
        end

        local arguments = { "python", directory .. "/service.py", root, action }
        if action == "start" or action == "restart" then
            -- Resolve preferences before the service manager touches a working agent.
            local snapshot = dofile(root .. "/lib/theme/shell.lua")(root).snapshot()
            table.insert(arguments, 1, "LUNA_UI_THEME=" .. snapshot)
            table.insert(arguments, 1, "env")
        end
        common.run(arguments)
    end

    return M
end
