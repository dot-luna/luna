-- Open the preferred terminal using the focused terminal's working directory.
return function(common, directory)
    local M = {}

    function M.register(parser)
        local command = parser:command("terminal", "Open the default terminal in the focused terminal's folder.")
        command:option("--pid", "Use a captured window process; 0 opens at home.")
            :target("terminal_pid")
            :convert(function(value) return value:match("^%d+$") end)
    end

    function M.run(options)
        local arguments = { "python3", directory .. "/terminal.py" }
        if options.terminal_pid then
            table.insert(arguments, "--pid")
            table.insert(arguments, options.terminal_pid)
        end
        common.run(arguments)
    end

    return M
end
