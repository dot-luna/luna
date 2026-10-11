-- Shared Lua output and process helpers; load relative to the calling script.
local M = {}

-- Keep ordinary status on stdout and errors on stderr for shell consumers.
function M.info(message)
    io.stdout:write(message, "\n")
end

function M.error(message)
    io.stderr:write(message, "\n")
end

-- Protect each argument from shell expansion, including embedded apostrophes.
function M.quote(value)
    return "'" .. value:gsub("'", "'\\''") .. "'"
end

function M.command(arguments)
    local parts = {}

    for i, value in ipairs(arguments) do
        parts[i] = M.quote(value)
    end

    return table.concat(parts, " ")
end

-- Quiet probes return a boolean; visible operations retain their output/prompts.
function M.succeeds(arguments)
    return os.execute(M.command(arguments) .. " >/dev/null 2>&1") == true
end

function M.run(arguments)
    assert(os.execute(M.command(arguments)) == true, "Command failed: " .. M.command(arguments))
end

function M.available(name)
    return M.succeeds({ "sh", "-c", 'command -v "$1"', "sh", name })
end

function M.is_root()
    return M.succeeds({ "sh", "-c", 'test "$(id -u)" -eq 0' })
end

return M
