#!/usr/bin/lua -E
-- Install the development tool manifest and activate mise in the user's shell.

-- Resolve the entry point before loading helpers so symlinks and any cwd work.
local pipe = assert(io.popen("readlink -f -- '" .. arg[0]:gsub("'", "'\\''") .. "'", "r"))
local script_path = pipe:read("*a"):gsub("\n$", "")
assert(pipe:close(), "Cannot resolve setup script: " .. arg[0])
local script_dir = assert(script_path:match("^(.*)/"), "Cannot resolve setup script directory")
local common = dofile(script_dir .. "/../../lib/common.lua")
local json = dofile(script_dir .. "/../../lib/theme/json.lua")
common.setup_logging()

local function install()
    assert(not common.is_root(), "Run mise setup as a normal user, without sudo")
    local manifest = dofile(script_dir .. "/../../packages/packages.mise.lua")

    -- Validate every entry before mise can change installations or configuration.
    common.assert_list(manifest, "Mise manifest")
    local names = {}
    for _, entry in ipairs(manifest) do
        assert(type(entry) == "table", "Invalid mise tool entry")
        assert(type(entry.name) == "string" and entry.name:match("^[a-z][a-z0-9_%-]*$"),
            "Invalid mise tool name")
        assert(not names[entry.name], "Duplicate mise tool name: " .. entry.name)
        assert(entry.source == "mise", "Mise tools must use source = mise")
        assert(type(entry.version) == "string" and entry.version:match("^[%w][%w._+%-]*$"),
            "Invalid mise version request: " .. entry.name)
        names[entry.name] = true
    end

    if #manifest == 0 then
        common.info("No mise development tools configured")
        return
    end
    for _, tool in ipairs({ "mise", "bash", "realpath" }) do
        assert(common.available(tool), "Required command is missing: " .. tool)
    end
    local home = os.getenv("HOME")
    assert(home and home:sub(1, 1) == "/" and not home:find("[%z%c]"),
        "HOME must be an absolute user home directory")
    local resolved_home, resolved = common.capture({ "realpath", "-e", "--", home }, true)
    assert(resolved, "Cannot resolve HOME")
    home = resolved_home:gsub("\n$", "")
    assert(home ~= "/" and common.succeeds({ "test", "-d", home }),
        "HOME must be a user home directory, not the filesystem root")

    -- Global use preserves unrelated mise settings and tools. Running from HOME
    -- avoids the caller's project configuration; fuzzy keeps the chosen requests
    -- even if the user has enabled mise's default version pinning.
    local command = { "mise", "--cd", home, "use", "--global", "--yes", "--fuzzy", "--" }
    for _, entry in ipairs(manifest) do
        command[#command + 1] = entry.name .. "@" .. entry.version
    end
    common.step("Install mise development tools")
    common.run(command)

    -- Do not activate an incomplete installation or report success solely from
    -- an install exit code: each global request must resolve to an installed tool.
    local output, listed = common.capture({ "mise", "--cd", home, "ls", "--global", "--json" })
    assert(listed, "Cannot verify installed mise tools")
    local installed = json.decode(output)
    assert(type(installed) == "table", "Invalid mise tool listing")
    for _, entry in ipairs(manifest) do
        local ready = false
        local versions = installed[entry.name]
        if type(versions) == "table" then
            for _, version in ipairs(versions) do
                if type(version) == "table" and version.requested_version == entry.version
                    and version.installed == true and version.active == true then
                    ready = true
                    break
                end
            end
        end
        assert(ready, "Mise tool is not installed as a global default: " .. entry.name .. "@" .. entry.version)
    end

    common.run({ "bash", script_dir .. "/mise-shell.sh" })
    common.success("Mise development tools are ready")
end

local ok, error_message = pcall(install)
if not ok then
    common.error("Mise setup failed: " .. tostring(error_message))
    os.exit(1)
end
