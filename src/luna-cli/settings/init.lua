-- Launch Luna Settings with the same resolved theme and lifecycle as the desktop shells.
return function(common, directory)
    local root = directory .. "/../../.."
    local shell = dofile(root .. "/lib/quickshell.lua")(common, root,
        directory .. "/../../luna-settings", "settings", "Luna Settings")
    local M = {}

    function M.register(parser)
        local command = parser:command("settings", "Open Luna Settings.")
        command:argument("settings_action", "Action"):args("?"):default("open")
            :choices({ "open", "start", "reload", "stop" })
        return command
    end

    function M.run(options)
        shell.run(options.settings_action or "open")
    end

    return M
end
