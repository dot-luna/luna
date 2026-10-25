-- Invoked under install.lock by the CLI; deletion cannot race container startup.
local directory = assert(arg[0]:match("^(.*)/"))
local root = directory .. "/../../.."
local common = dofile(root .. "/lib/common.lua")
local config = dofile(directory .. "/config.lua")(common, root)

local function install()
    assert(config.exists(), "macOS configuration disappeared; rerun luna macos install")
    local seconds = tonumber(arg[1])
    assert(seconds and seconds % 1 == 0 and seconds >= 1 and seconds <= 86400,
        "Console timeout must be an integer from 1 to 86400 seconds")

    local function compose(...)
        local arguments = { "docker", "compose", "--project-name", "luna-macos", "--file", config.path }
        for _, value in ipairs({ ... }) do table.insert(arguments, value) end
        common.run(arguments)
    end

    compose("pull", "macos")
    compose("up", "-d", "macos")
    common.info("Waiting for the macOS console. View progress at http://127.0.0.1:8007 or with luna macos logs.")
    common.run({ "bash", directory .. "/wait-ready.sh", config.path, tostring(seconds) })

    -- Publish readiness only after a VNC greeting, while deletion is still locked.
    local file = assert(io.open(config.prepared_path, "w"))
    assert(file:write("macOS VM console prepared; this does not confirm guest installation.\n"))
    assert(file:close())
    common.run({ "chmod", "600", "--", config.prepared_path })
    config.install_desktop_entry()
    common.info("macOS VM console is ready. Finish any recovery/installation screens in the console.")
    common.info("Open http://127.0.0.1:8007 or run luna macos start --keep-alive. The VM stays running.")
end

local ok, message = pcall(install)
if not ok then
    common.error(tostring(message):gsub("^.-:%d+: ", ""))
    os.exit(1)
end
