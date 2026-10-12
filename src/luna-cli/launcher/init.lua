-- Own Luna Launcher's instance through the shared themed shell lifecycle.
return function(common, directory)
    local root = directory .. "/../../.."
    local shell = dofile(root .. "/lib/quickshell.lua")(common, root, directory .. "/../../launcher", "launcher", "Luna Launcher")
    local M = {}

    function M.register(parser)
        local command = parser:command("launcher", "Search and launch installed applications.")
        command:argument("launcher_action", "Action"):args("?"):default("open")
            :choices({ "open", "toggle", "start", "reload", "stop" })
        return command
    end

    function M.run(options)
        shell.run(options.launcher_action or "open")
    end

    return M
end
