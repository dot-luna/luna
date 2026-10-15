#!/usr/bin/lua -E
-- Clone configured Git apps and invoke their own installers after core setup.
-- Build systems and app dependencies belong to the app, not Luna's manifest.
local script_dir = assert(arg[0]:match("^(.*)/"), "Run this script using its path")
local common = dofile(script_dir .. "/../../lib/common.lua")
common.setup_logging()
local argparse = require("argparse")
local parser = argparse("git-apps.lua", "Clone and install Luna's Git applications.")
parser:flag("--force", "Accepted for setup compatibility; Git apps are always reinstalled")
parser:parse()

local function resolve(path, mode)
    local output, ok = common.capture({ "realpath", mode, "--", path }, true)
    assert(ok, "Cannot resolve path: " .. path)
    return (output:gsub("\n$", ""))
end

local function inside(path, directory)
    return path == directory or path:sub(1, #directory + 1) == directory .. "/"
end

local function basename(value)
    return type(value) == "string" and value:match("^[%w][%w._%-]*$") ~= nil
end

local function relative_script(value)
    if type(value) ~= "string" or value == "" or value:sub(1, 1) == "/"
        or value:sub(-1) == "/" or value:find("//", 1, true) then
        return false
    end
    for component in value:gmatch("[^/]+") do
        if component == "." or component == ".." or not component:match("^[%w._%-]+$") then
            return false
        end
    end
    return true
end

local function install()
    assert(not common.is_root(), "Run Git app setup as a normal user, without sudo")
    for _, tool in ipairs({ "git", "bash", "realpath", "mkdir", "rm" }) do
        assert(common.available(tool), "Required command is missing: " .. tool)
    end

    local home = os.getenv("HOME")
    assert(home and home:sub(1, 1) == "/" and not home:find("[%z%c]"),
        "HOME must be an absolute user home directory")
    home = resolve(home, "-e")
    assert(home ~= "/" and common.succeeds({ "test", "-d", home }),
        "HOME must be a user home directory, not the filesystem root")

    local repo_dir = resolve(script_dir .. "/../..", "-e")
    local source_dir = home .. "/.local/src"
    local source_location = resolve(source_dir, "-m")
    local prefix = home .. "/.local"
    local manifest = dofile(repo_dir .. "/packages/packages.git.lua")
    assert(type(manifest) == "table", "Git app manifest must be a list")

    -- Validate the complete manifest before removing any existing checkout.
    -- Resolving only the parent keeps replacement of a destination symlink safe:
    -- rm removes that link, while parent symlinks cannot hide a Luna collision.
    local count = 0
    for key in pairs(manifest) do
        assert(type(key) == "number" and key % 1 == 0 and key >= 1 and key <= #manifest,
            "Git app manifest must be a contiguous list")
        count = count + 1
    end
    assert(count == #manifest, "Git app manifest must be a contiguous list")

    local names = {}
    local executables = {}
    for index = 1, #manifest do
        local entry = manifest[index]
        assert(type(entry) == "table", "Invalid Git app entry")
        assert(basename(entry.name), "Invalid Git app name")
        assert(entry.name ~= "luna" and not names[entry.name], "Reserved or duplicate Git app name: " .. entry.name)
        assert(entry.source == "git", "Git apps must use source = git")
        assert(type(entry.url) == "string" and entry.url:match("^https://[^%s%z]+$"),
            "Git app URL must use HTTPS: " .. entry.name)
        assert(type(entry.ref) == "string" and entry.ref ~= "" and entry.ref:sub(1, 1) ~= "-"
            and not entry.ref:match("^refs/") and not entry.ref:find("[%z%c]"),
            "Invalid branch or tag for Git app: " .. entry.name)
        assert(common.succeeds({ "git", "check-ref-format", "refs/heads/" .. entry.ref }),
            "Invalid branch or tag for Git app: " .. entry.name)
        assert(relative_script(entry.script), "Invalid installer path for Git app: " .. entry.name)
        assert(basename(entry.executable) and entry.executable ~= "luna", "Invalid Git app executable: " .. entry.name)
        assert(not executables[entry.executable], "Duplicate Git app executable: " .. entry.executable)

        local bundled = repo_dir .. "/src/" .. entry.name
        assert(not common.succeeds({ "test", "-e", bundled }) and not common.succeeds({ "test", "-L", bundled }),
            "Git app name collides with a Luna source package: " .. entry.name)
        local destination = source_location .. "/" .. entry.name
        assert(not inside(destination, repo_dir) and not inside(repo_dir, destination)
            and not inside(home, destination), "Git app checkout overlaps Luna or HOME: " .. entry.name)
        names[entry.name] = true
        executables[entry.executable] = true
    end

    for _, entry in ipairs(manifest) do
        local destination = source_dir .. "/" .. entry.name
        common.step("Install Git app: " .. entry.name .. " (" .. entry.ref .. ")")
        common.run({ "mkdir", "-p", "--", source_dir })
        common.info("Replacing checkout: " .. destination)
        common.run({ "rm", "-rf", "--", destination })
        common.run({ "git", "clone", "--recurse-submodules", "--branch", entry.ref,
            "--single-branch", "--", entry.url, destination })

        local installer = resolve(destination .. "/" .. entry.script, "-e")
        assert(inside(installer, resolve(destination, "-e")) and common.succeeds({ "test", "-f", installer }),
            "App installer must be a file inside its checkout: " .. entry.name)

        -- Positional arguments preserve spaces and shell metacharacters. Only
        -- the app's installer decides which dependencies and build tools to use.
        common.run({ "bash", "-c", 'cd -- "$1" && exec bash "$2" --prefix "$3" --non-interactive',
            "luna-git-app", destination, installer, prefix })
        local executable = prefix .. "/bin/" .. entry.executable
        assert(common.succeeds({ "test", "-f", executable }) and common.succeeds({ "test", "-x", executable }),
            "Git app did not install its executable: " .. executable)
        common.success("Git app ready: " .. entry.name)
    end
end

local ok, error_message = pcall(install)
if not ok then
    common.error("Git app setup failed: " .. tostring(error_message))
    os.exit(1)
end
