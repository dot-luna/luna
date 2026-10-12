-- Own Luna Bar's instance through the shared themed shell lifecycle.
return function(common, directory)
    local root = directory .. "/../../.."
    local shell = dofile(root .. "/lib/quickshell.lua")(common, root, directory .. "/../../bar", "bar", "Luna Bar")
    local M = {}

    function M.register(parser)
        local command = parser:command("bar", "Start or control Luna Bar.")
        command:argument("bar_action", "Action"):args("?"):default("start")
            :choices({ "start", "reload", "stop", "focus", "controls" })
        return command
    end

    function M.run(options)
        shell.run(options.bar_action or "start")
    end

    return M
end
