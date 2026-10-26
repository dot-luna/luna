#!/usr/bin/lua -E
-- Clone configured Git apps and invoke their own installers after core setup.
-- Build systems and app dependencies belong to the app, not Luna's manifest.

-- Resolve the entry point before loading helpers so symlinks and any cwd work.
local pipe = assert(io.popen("readlink -f -- '" .. arg[0]:gsub("'", "'\\''") .. "'", "r"))
local script_path = pipe:read("*a"):gsub("\n$", "")
assert(pipe:close(), "Cannot resolve setup script: " .. arg[0])
local script_dir = assert(script_path:match("^(.*)/"), "Cannot resolve setup script directory")
local common = dofile(script_dir .. "/../../lib/common.lua")
common.setup_logging()

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

local function install_app(entry, source_dir, prefix)
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

    -- Validate the complete manifest before removing any existing checkout.
    -- Resolving only the parent keeps replacement of a destination symlink safe:
    -- rm removes that link, while parent symlinks cannot hide a Luna collision.
    common.assert_list(manifest, "Git app manifest")
    local names = {}
    local executables = {}
    for _, entry in ipairs(manifest) do
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

    -- Move the whole Lua process out of a checkout before deleting its cwd.
    -- HOME cannot overlap a destination, so the child never needs to restart.
    local working_dir = resolve(".", "-e")
    for _, entry in ipairs(manifest) do
        local destination = source_location .. "/" .. entry.name
        if inside(working_dir, destination) and not common.succeeds({ "test", "-L", destination }) then
            local ok, kind, status = os.execute(common.command({ "bash", "-c",
                'cd -- "$1" && exec /usr/bin/lua -E "$2"', "luna-git-app", home, script_path }))
            os.exit(ok and 0 or (kind == "signal" and 128 + status or status or 1))
        end
    end

    -- Apps are independent: finish the remaining installs before reporting an
    -- incomplete group to setup.sh, which can still deploy the desktop.
    local failures = 0
    for _, entry in ipairs(manifest) do
        local ok, error_message = pcall(install_app, entry, source_dir, prefix)
        if not ok then
            failures = failures + 1
            local detail = tostring(error_message):gsub("^.-:%d+: ", "")
            detail = detail:gsub("^(Command failed %b()):.*$", "%1")
            common.warn("Git app failed: " .. entry.name .. ": " .. detail)
        end
    end
    assert(failures == 0, string.format("%d Git app%s failed", failures, failures == 1 and "" or "s"))
end

local ok, error_message = pcall(install)
if not ok then
    common.error("Git app setup failed: " .. tostring(error_message))
    os.exit(1)
end
