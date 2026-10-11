-- Update one INI setting while preserving unrelated sections, keys, and comments.
local M = {}

function M.set(content, section, key, value)
    local newline = content:find("\r\n", 1, true) and "\r\n" or "\n"
    local lines, inside, found_section, found_key = {}, false, false, false
    local function finish_section()
        if inside and not found_key then
            table.insert(lines, key .. "=" .. value)
        end
    end

    for original in (content:gsub("\r\n", "\n") .. (content:sub(-1) == "\n" and "" or "\n")):gmatch("([^\n]*)\n") do
        local line = original
        local heading = line:match("^%s*%[([^%]]+)%]%s*$")
        if heading then
            finish_section()
            inside = heading == section
            found_section = found_section or inside
            found_key = false
        end
        if inside and line:match("^%s*([^=;%s#]+)%s*=") == key then
            line = key .. "=" .. value
            found_key = true
        end
        table.insert(lines, line)
    end
    finish_section()

    if not found_section then
        if #lines > 0 and lines[#lines] ~= "" then
            table.insert(lines, "")
        end
        table.insert(lines, "[" .. section .. "]")
        table.insert(lines, key .. "=" .. value)
    end
    return table.concat(lines, newline) .. newline
end

return M
