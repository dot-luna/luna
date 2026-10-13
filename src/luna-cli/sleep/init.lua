-- Delegate sleep sequencing to the helper that waits for compositor lock readiness.
return function(common, directory)
    local M = {}
    function M.register(parser)
        parser:command("suspend", "Lock the session and suspend to RAM.")
        parser:command("hibernate", "Lock and hibernate when disk-backed resume is configured.")
    end
    function M.run(options)
        common.run({ "python3", directory .. "/sleep.py", options.hibernate and "hibernate" or "suspend",
            directory .. "/../../../bin/luna" })
    end
    return M
end
