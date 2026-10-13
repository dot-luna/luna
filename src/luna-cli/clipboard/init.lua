-- Keep clipboard history and paste behavior shared between the menu and CLI.
return function(common, directory)
    local M = {}

    function M.register(parser)
        local command = parser:command("clipboard", "Manage clipboard history.")
        command:argument("clipboard_action"):choices({ "start", "list", "preview", "paste", "target", "delete", "clear" })
        command:argument("clipboard_id"):args("?")
        command:argument("clipboard_target"):args("?")
    end

    function M.run(options)
        local command = { "python", directory .. "/clipboard.py", options.clipboard_action }
        if options.clipboard_id then table.insert(command, options.clipboard_id) end
        if options.clipboard_target then table.insert(command, options.clipboard_target) end
        common.run(command)
    end

    return M
end
