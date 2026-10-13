-- Personal font choices override theme defaults without changing installed themes.
return function(root)
    local json = dofile(root .. "/lib/theme/json.lua")
    local validate = dofile(root .. "/lib/theme/validate.lua")()
    local config = (os.getenv("XDG_CONFIG_HOME") or assert(os.getenv("HOME")) .. "/.config") .. "/luna"
    local M = { path = config .. "/fonts.json" }

    function M.read()
        local file, message, code = io.open(M.path, "r")
        if not file then
            assert(code == 2, message)
            return {}
        end
        local values = json.decode(file:read("*a"))
        file:close()
        validate.values({ fonts = values })
        return values
    end

    function M.apply(theme)
        for role, family in pairs(M.read()) do
            theme.fonts[role] = family
        end
        return theme
    end

    return M
end
