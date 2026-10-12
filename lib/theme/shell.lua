-- Pass a validated theme snapshot to Quickshell at launch, without generated files.
return function(root)
    local validate = dofile(root .. "/lib/theme/validate.lua")()
    local M = {}

    local function quoted(value)
        return '"' .. value:gsub('[%z\1-\31\\"]', function(character)
            if character == '"' or character == "\\" then
                return "\\" .. character
            end
            return string.format("\\u%04x", character:byte())
        end) .. '"'
    end

    local function object(values)
        local keys, fields = {}, {}
        for key in pairs(values) do
            table.insert(keys, key)
        end
        table.sort(keys)
        for _, key in ipairs(keys) do
            local value = values[key]
            table.insert(fields, quoted(key) .. ":" .. (type(value) == "string" and quoted(value) or tostring(value)))
        end
        return "{" .. table.concat(fields, ",") .. "}"
    end

    function M.snapshot()
        local home = assert(os.getenv("HOME"), "HOME is required")
        local selection = (os.getenv("XDG_CONFIG_HOME") or home .. "/.config") .. "/luna/theme"
        local file = io.open(selection, "r")
        local name = file and file:read("*l")
        if file then
            file:close()
        end

        local directory = root .. "/themes/bundled/tokyo-night"
        if name then
            assert(name:match("^[a-z0-9][a-z0-9_-]*$"), "Invalid selected theme")
            directory = (os.getenv("XDG_DATA_HOME") or home .. "/.local/share") .. "/luna/themes/" .. name
        end
        local exports = validate.load(directory)
        return '{"colors":' .. object(exports.colors) .. ',"bar":' .. object(exports.bar or {}) .. "}"
    end

    return M
end
