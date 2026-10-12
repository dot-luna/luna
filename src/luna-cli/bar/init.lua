-- Own Luna Bar's instance through the shared themed shell lifecycle.
return function(common, directory)
    local root = directory .. "/../../.."
    local config = dofile(directory .. "/config.lua")(common, root)
    local shell = dofile(root .. "/lib/quickshell.lua")(common, root, directory .. "/../../luna-bar", "bar", "Luna Bar")
    local M = {}

    function M.register(parser)
        local command = parser:command("bar", "Start or control Luna Bar.")
        command:argument("bar_action", "Action"):args("?"):default("start")
            :choices({ "start", "reload", "stop", "focus", "controls" })
        return command
    end

    function M.run(options)
        local action = options.bar_action or "start"
        local environment = action ~= "stop" and { LUNA_BAR_CONFIG = config.snapshot() } or nil
        shell.run(action, environment)
    end

    return M
end
