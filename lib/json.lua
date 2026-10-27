-- JSON codec shared by themes and config APIs; never evaluates content as Lua code.
-- A sentinel preserves null object fields and array positions that Lua nil would erase.
local M = { null = setmetatable({}, { __json_kind = "null" }) }

-- Lua's empty tables have no array/object distinction; callers can mark an array.
function M.array(value)
    return setmetatable(value or {}, { __json_kind = "array" })
end

local function quote(value)
    return '"' .. value:gsub('[%z\1-\31\\"]', function(character)
        if character == '"' or character == "\\" then
            return "\\" .. character
        end
        return string.format("\\u%04x", character:byte())
    end) .. '"'
end

function M.encode(value, array)
    local kind = type(value) == "table" and getmetatable(value)
    kind = kind and kind.__json_kind
    if value == M.null or kind == "null" then
        return "null"
    elseif type(value) == "string" then
        return quote(value)
    elseif type(value) == "number" or type(value) == "boolean" then
        return tostring(value)
    end
    assert(type(value) == "table", "Unsupported JSON value")
    local fields = {}
    -- Preserve decoded empty arrays/objects across API transports. Ordinary Lua
    -- sequences are arrays too; the array argument can explicitly encode an empty list.
    if kind == "array" or kind ~= "object" and (array or #value > 0) then
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
        table.insert(fields, quote(key) .. ":" .. M.encode(value[key]))
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
                    if code >= 0xd800 and code <= 0xdbff then
                        assert(source:sub(position, position + 1) == "\\u", "Missing JSON surrogate pair")
                        local low_hex = source:sub(position + 2, position + 5)
                        assert(low_hex:match("^%x%x%x%x$"), "Invalid JSON surrogate escape")
                        local low = tonumber(low_hex, 16)
                        assert(low >= 0xdc00 and low <= 0xdfff, "Invalid JSON surrogate pair")
                        code = 0x10000 + (code - 0xd800) * 0x400 + low - 0xdc00
                        position = position + 6
                    else
                        assert(code < 0xdc00 or code > 0xdfff, "Unexpected JSON low surrogate")
                    end
                    table.insert(parts, utf8.char(code))
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
        assert(depth < 32, "JSON is nested too deeply")
        local c = character()
        if c == '"' then
            return string_value()
        elseif c == "{" or c == "[" then
            local array, seen = c == "[", {}
            local values = setmetatable({}, { __json_kind = array and "array" or "object" })
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
        for literal, value in pairs({ ["true"] = true, ["false"] = false, ["null"] = M.null }) do
            if source:sub(position, position + #literal - 1) == literal then
                position = position + #literal
                return value
            end
        end
        local token = source:sub(position):match("^%-?%d+%.?%d*[eE]?[+-]?%d*")
        local value = token and tonumber(token)
        assert(value and value == value and math.abs(value) < math.huge, "Invalid JSON value")
        position = position + #token
        return value
    end
    local result = parse(0)
    whitespace()
    assert(position > #source, "Trailing JSON content")
    return result
end

return M
