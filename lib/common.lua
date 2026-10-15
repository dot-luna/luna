-- Shared Lua output and process helpers; load relative to the calling script.
local M = {}
local setup_mode = false
local use_color = false

-- Setup opts in explicitly so CLI text and JSON consumers keep their old output.
function M.setup_logging()
    setup_mode = true
    local setting = os.getenv("LUNA_COLOR")
    local no_color = os.getenv("NO_COLOR")
    if no_color and no_color ~= "" then
        use_color = false
    elseif setting == "1" then
        use_color = true
    elseif setting == "0" or os.getenv("TERM") == "dumb" then
        use_color = false
    else
        use_color = os.execute("test -t 1") == true
    end
end

local function log(stream, level, message)
    if not setup_mode then
        stream:write(message, "\n")
        return
    end

    if level == "STEP" or level == "WARN" or level == "ERROR" then
        stream:write("\n")
    end
    local colors = { INFO = "36", OK = "32", WARN = "1;33", ERROR = "1;31", STEP = "1;36" }
    local prefix = use_color and ("\27[" .. colors[level] .. "m") or ""
    local reset = use_color and "\27[0m" or ""
    stream:write(prefix, os.date("[%H:%M:%S]"), " [", level, "]", reset, " ", message, "\n")
    stream:flush()
end

-- Keep ordinary status on stdout and errors on stderr for shell consumers.
function M.info(message)
    log(io.stdout, "INFO", message)
end

function M.error(message)
    log(io.stderr, "ERROR", message)
end

function M.success(message)
    log(io.stdout, "OK", message)
end

function M.warn(message)
    log(io.stderr, "WARN", message)
end

function M.step(message)
    log(io.stdout, "STEP", message)
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
    if not setup_mode then
        assert(os.execute(M.command(arguments)) == true, "Command failed: " .. M.command(arguments))
        return
    end

    -- The child retains stdin, including sudo's terminal access. Read output as
    -- it arrives, and close the pipe before deciding whether installation passed.
    io.stdout:write("\n")
    io.stdout:flush()
    local pipe = assert(io.popen(M.command(arguments) .. " 2>&1", "r"))
    for line in pipe:lines() do
        local clean_line = line:gsub("\27%[[0-?]*[ -/]*[@-~]", "")
        io.stdout:write(use_color and "\27[90m" or "", "  ", clean_line,
            use_color and "\27[0m" or "", "\n")
        io.stdout:flush()
    end
    local ok, kind, code = pipe:close()
    io.stdout:write("\n")
    io.stdout:flush()
    assert(ok, "Command failed (" .. tostring(kind) .. " " .. tostring(code) .. "): " .. M.command(arguments))
end

-- Capture stdout while retaining the exit code; quiet probes suppress stderr.
function M.capture(arguments, quiet)
    local pipe = assert(io.popen(M.command(arguments) .. (quiet and " 2>/dev/null" or ""), "r"))
    local output = pipe:read("*a")
    local ok, _, code = pipe:close()

    return output, ok == true, code
end

function M.available(name)
    return M.succeeds({ "sh", "-c", 'command -v "$1"', "sh", name })
end

function M.is_root()
    return M.succeeds({ "sh", "-c", 'test "$(id -u)" -eq 0' })
end

return M
