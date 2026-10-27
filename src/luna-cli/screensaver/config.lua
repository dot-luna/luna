-- Seconds of inactivity; zero disables a timer independently.
return function(common, root)
    local json = dofile(root .. "/lib/json.lua")
    local directory = (os.getenv("XDG_CONFIG_HOME") or assert(os.getenv("HOME")) .. "/.config") .. "/luna"
    local M = { path = directory .. "/idle.json" }

    function M.read()
        local values = { screensaver_seconds = 300, lock_seconds = 600 }
        local file, message, code = io.open(M.path, "r")
        if file then
            local saved = json.decode(file:read("*a"))
            file:close()
            assert(type(saved) == "table", "Idle settings must be an object")
            for key, value in pairs(saved) do
                assert(values[key] ~= nil, "Unknown idle setting: " .. tostring(key))
                assert(type(value) == "number" and value % 1 == 0 and value >= 0 and value <= 86400,
                    "Idle timeouts must be whole seconds from 0 to 86400")
                values[key] = value
            end
        else
            assert(code == 2, message)
        end
        return values
    end

    function M.set(setting, seconds)
        local key = ({ screensaver = "screensaver_seconds", lock = "lock_seconds" })[setting]
        assert(key, "Unknown idle setting")
        assert(seconds and seconds % 1 == 0 and seconds >= 0 and seconds <= 86400,
            "Idle timeouts must be whole seconds from 0 to 86400")
        local values = M.read()
        values[key] = seconds
        common.run({ "mkdir", "-p", "--", directory })
        local file = assert(io.open(M.path .. ".tmp", "w"))
        assert(file:write(json.encode(values), "\n"))
        assert(file:close())
        assert(os.rename(M.path .. ".tmp", M.path))
        return values
    end

    return M
end
