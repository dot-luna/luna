-- Shared Lua config operations, independent of an app or file format.
-- TOML persistence belongs to lib/toml.lua; callers supply their own defaults.
return function(json)
    local M = {}

    -- Decoded arrays/null carry metadata; ordinary Lua sequences are arrays too.
    function M.isObject(value)
        if type(value) ~= "table" then
            return false
        end
        local metadata = getmetatable(value)
        local kind = metadata and metadata.__json_kind
        return kind == "object" or kind == nil and #value == 0
    end

    local function copy(value)
        if type(value) ~= "table" then
            return value
        end
        local metadata = getmetatable(value)
        if metadata and metadata.__json_kind == "null" then
            return value
        end
        local result = setmetatable({}, metadata)
        for key, item in pairs(value) do
            result[key] = copy(item)
        end
        return result
    end

    -- Merge nested objects, replace arrays/scalars, and leave both inputs untouched.
    -- Mark empty Lua arrays with json.array({}) to distinguish them from empty objects.
    function M.merge(base, overrides)
        if not M.isObject(overrides) then
            return copy(overrides)
        end
        local result = M.isObject(base) and copy(base) or {}
        for key, value in pairs(overrides) do
            result[key] = M.merge(result[key], value)
        end
        return result
    end

    -- Resolve an app's user file without reading or creating it.
    function M.path(relative, environment)
        local path = environment and os.getenv(environment)
        if not path or path == "" then
            local directory = os.getenv("XDG_CONFIG_HOME")
            if not directory or directory == "" then
                directory = assert(os.getenv("HOME"), "HOME is required") .. "/.config"
            end
            path = directory .. "/" .. relative
        end
        assert(path:sub(1, 1) == "/", "Config path must be absolute")
        return path
    end

    -- Dots address nested table keys; missing paths return nil, preserving false/0.
    function M.get(document, key)
        if key == nil or key == "" then
            return document
        end
        assert(type(key) == "string", "Config key must be a dotted string")
        if key:sub(1, 1) == "." or key:sub(-1) == "." or key:find("..", 1, true) then
            return nil
        end
        local value = document
        for part in key:gmatch("[^.]+") do
            if not M.isObject(value) then
                return nil
            end
            value = value[part]
        end
        return value
    end

    -- Lua receives values; the JSON bridge and CLI request their output encoding.
    function M.format(value, format)
        if format == "json" then
            return json.encode(value == nil and json.null or value)
        elseif format == "text" then
            if value == nil or value == json.null then
                return ""
            elseif type(value) ~= "table" then
                return tostring(value)
            end
            return json.encode(value)
        end
        return value
    end

    return M
end
