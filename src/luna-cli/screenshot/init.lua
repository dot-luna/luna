-- Share the same screenshot capture and clipboard behavior between shortcuts and the menu.
return function(common, directory)
    local M = {}

    function M.register(parser)
        local command = parser:command("screenshot", "Save a screenshot and copy its image to the clipboard.")
        command:argument("screenshot_action", "Capture area"):args("?"):default("region")
            :choices({ "region", "screen", "window", "all" })
        return command
    end

    function M.run(options)
        common.run({ "python", directory .. "/screenshot.py", options.screenshot_action or "region" })
    end

    return M
end
