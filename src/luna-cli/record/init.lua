-- Keep menu actions, shortcuts, and the bar's stop button on one recording backend.
return function(common, directory)
    local M = {}

    function M.register(parser)
        local command = parser:command("record", "Record a screen or region into ~/Videos/Recordings.")
        command:argument("record_action"):args("?"):default("region")
            :choices({ "region", "screen", "stop", "toggle", "status" })
        return command
    end

    function M.run(options)
        common.run({ "python", directory .. "/record.py", options.record_action or "region" })
    end

    return M
end
