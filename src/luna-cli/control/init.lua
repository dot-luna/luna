-- Route hardware keys through the running bar so controls and feedback share state.
return function(common, directory)
    local root = directory .. "/../../.."
    local bar = dofile(root .. "/src/luna-cli/bar/init.lua")(common, root .. "/src/luna-cli/bar")
    local M = {}

    function M.register(parser)
        local command = parser:command("control", "Adjust volume, microphone, brightness, or media playback.")
        command:argument("control_action"):choices({ "volume-up", "volume-down", "volume-mute", "mic-mute",
            "brightness-up", "brightness-down", "play-pause", "next", "previous" })
        return command
    end

    function M.run(options)
        local arguments = { "qs", "ipc", "-p", root .. "/src/luna-bar", "call", "bar", "control", options.control_action }
        local output, ready = common.capture(arguments, true)
        local response = output:match("^%s*(.-)%s*$")
        if not ready or (response ~= "true" and response ~= "false") then
            bar.run({ bar_action = "start" })
            common.run(arguments)
        end
    end

    return M
end
