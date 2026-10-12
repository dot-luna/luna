-- JSON codec for resolved themes; never evaluates generated content as Lua code.
local M = {}

local function quote(value)
    return '"' .. value:gsub('[%z\1-\31\\"]', function(character)
        if character == '"' or character == "\\" then
            return "\\" .. character
        end
        return string.format("\\u%04x", character:byte())
    end) .. '"'
end

function M.encode(value, array)
    if type(value) == "string" then
        return quote(value)
    elseif type(value) == "number" or type(value) == "boolean" then
        return tostring(value)
    end
    assert(type(value) == "table", "Unsupported theme JSON value")
    local fields = {}
    if array then
        for _, item in ipairs(value) do
            table.insert(fields, M.encode(item))
        end
        return "[" .. table.concat(fields, ",") .. "]"
    end
    local keys = {}
    for key in pairs(value) do
        table.insert(keys, key)
    end
    table.sort(keys)
    for _, key in ipairs(keys) do
        table.insert(fields, quote(key) .. ":" .. M.encode(value[key], key == "sources"))
    end
    return "{" .. table.concat(fields, ",") .. "}"
end

function M.decode(source)
    local position = 1
    local parse
    local function whitespace()
        position = source:find("%S", position) or #source + 1
    end
    local function character()
        whitespace()
        return source:sub(position, position)
    end
    local function string_value()
        assert(source:sub(position, position) == '"', "Expected JSON string")
        position = position + 1
        local parts = {}
        while position <= #source do
            local c = source:sub(position, position)
            position = position + 1
            if c == '"' then
                return table.concat(parts)
            elseif c == "\\" then
                local escaped = source:sub(position, position)
                position = position + 1
                local escapes = { ['"'] = '"', ['\\'] = '\\', ['/'] = '/', b = '\b', f = '\f', n = '\n', r = '\r', t = '\t' }
                if escaped == "u" then
                    local hex = source:sub(position, position + 3)
                    assert(hex:match("^%x%x%x%x$"), "Invalid JSON escape")
                    local code = tonumber(hex, 16)
                    position = position + 4
                    -- Generated strings use Unicode directly; escaped control bytes are ASCII.
                    assert(code < 128, "Theme JSON expects non-ASCII characters as UTF-8")
                    table.insert(parts, string.char(code))
                else
                    local decoded = assert(escapes[escaped], "Invalid JSON escape")
                    table.insert(parts, decoded)
                end
            else
                assert(c:byte() >= 32, "Invalid JSON control character")
                table.insert(parts, c)
            end
        end
        error("Unterminated JSON string")
    end
    function parse(depth)
        assert(depth < 32, "Theme JSON is nested too deeply")
        local c = character()
        if c == '"' then
            return string_value()
        elseif c == "{" or c == "[" then
            local array, values, seen = c == "[", {}, {}
            local closing = array and "]" or "}"
            position = position + 1
            if character() == closing then
                position = position + 1
                return values
            end
            while true do
                local key = #values + 1
                if not array then
                    character()
                    key = string_value()
                    assert(not seen[key], "Duplicate JSON key")
                    seen[key] = true
                    assert(character() == ":", "Expected JSON colon")
                    position = position + 1
                end
                values[key] = parse(depth + 1)
                c = character()
                position = position + 1
                if c == closing then
                    return values
                end
                assert(c == ",", "Expected JSON comma")
            end
        end
        for literal, value in pairs({ ["true"] = true, ["false"] = false }) do
            if source:sub(position, position + #literal - 1) == literal then
                position = position + #literal
                return value
            end
        end
        local token = source:sub(position):match("^%-?%d+%.?%d*[eE]?[+-]?%d*")
        local value = token and tonumber(token)
        assert(value and value == value and math.abs(value) < math.huge, "Invalid theme JSON value")
        position = position + #token
        return value
    end
    local result = parse(0)
    whitespace()
    assert(position > #source, "Trailing theme JSON content")
    return result
end

return M
