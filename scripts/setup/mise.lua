#!/usr/bin/lua -E
-- Install the development tool manifest and activate mise in the user's shell.
local script_dir = assert(arg[0]:match("^(.*)/"), "Run this script using its path")
local common = dofile(script_dir .. "/../../lib/common.lua")
local json = dofile(script_dir .. "/../../lib/theme/json.lua")
common.setup_logging()

local function install()
    assert(not common.is_root(), "Run mise setup as a normal user, without sudo")
    local manifest = dofile(script_dir .. "/../../packages/packages.mise.lua")
    assert(type(manifest) == "table", "Mise manifest must be a list")

    -- Validate every entry before mise can change installations or configuration.
    local count = 0
    for key in pairs(manifest) do
        assert(type(key) == "number" and key % 1 == 0 and key >= 1 and key <= #manifest,
            "Mise manifest must be a contiguous list")
        count = count + 1
    end
    assert(count == #manifest, "Mise manifest must be a contiguous list")

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
    for _, tool in ipairs({ "mise", "bash" }) do
        assert(common.available(tool), "Required command is missing: " .. tool)
    end
    local home = os.getenv("HOME")
    assert(home and home:sub(1, 1) == "/" and home ~= "/" and not home:find("[%z%c]"),
        "HOME must be an absolute user home directory")

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
