-- Shared emoji and GIF backends for the Insert menu and terminal callers.
return function(common, directory)
    local M = {}

    function M.register(parser)
        local command = parser:command("insert", "Search and insert emoji or GIFs.")
        command:argument("insert_action"):choices({ "emoji", "gifs", "paste-emoji", "paste-giphy", "configure" })
        command:argument("insert_arguments"):args("*")
    end

    function M.run(options)
        local backend = dofile(directory .. "/backend.lua")(common, directory)
        local action, arguments = options.insert_action, options.insert_arguments
        if action == "configure" then
            common.run({ "bash", directory .. "/configure.sh" })
        elseif action == "gifs" then
            backend.giphy(arguments[1] or "", arguments[2])
        else
            backend[action:gsub("-", "_")](table.unpack(arguments))
        end
    end

    return M
end
