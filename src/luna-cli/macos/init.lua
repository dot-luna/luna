-- Prepare Dockur macOS and manage a foreground VNC console, including recovery.
return function(common, directory)
    local root = directory .. "/../../.."
    local config = dofile(directory .. "/config.lua")(common, root)
    local json = dofile(root .. "/lib/json.lua")
    local M = {}

    function M.register(parser)
        local command = parser:command("macos mac", "Install and control the macOS VM.")
        command:require_command(false)
        local install = command:command("install", "Prepare macOS and wait for its installation console.")
        install:option("--timeout", "Seconds to wait for the installation console"):default("7200")
        install:option("--ram", "Memory in GiB, at least 4G (default 4G)")
        install:option("--cpus", "Virtual CPU cores: 1/2/4/6/8/10/12/14/16/24/32/64 (default 2)")
        install:option("--disk", "Virtual disk capacity in GiB, at least 64G (default 64G)")
        install:option("--version", "macOS version: 11, 12, 13, 14, 15, or 26 (default 15)"):target("macos_version")
        install:flag("--yes -y", "Use defaults for unspecified options without prompting")
        local start = command:command("start", "Start macOS and attach to its installation or desktop console.")
        start:flag("--keep-alive -k", "Leave the VM running after the console closes; useful during installation")
        start:option("--timeout", "Seconds to wait for the console on startup"):default("120")
        command:command("stop", "Gracefully stop the VM, preserving its disk.")
        command:command("status", "Show the VM container status.")
        local delete = command:command("delete remove", "Delete the macOS VM, disk, configuration, and launcher; keep shared files.")
        delete:flag("--yes -y", "Confirm permanent deletion without prompting")
        local logs = command:command("logs", "Follow the VM logs; Ctrl+C ends log viewing only.")
        logs:flag("--no-follow", "Print recent logs and exit")
        logs:option("--tail", "Number of recent lines to show"):default("100")
        return command
    end

    local function compose(...)
        local arguments = { "docker", "compose", "--project-name", "luna-macos", "--file", config.path }
        for _, value in ipairs({ ... }) do table.insert(arguments, value) end
        return arguments
    end

    local function installation_options(options)
        local fields = {
            { "ram", "RAM (GiB, minimum 4G)", "4G" },
            { "cpus", "CPU cores (1/2/4/6/8/10/12/14/16/24/32/64)", "2" },
            { "disk", "Disk capacity (GiB, minimum 64G)", "64G" },
            { "macos_version", "macOS version (11/12/13/14/15/26)", "15" },
        }
        local supplied = {}
        for _, field in ipairs(fields) do
            supplied[field[1]] = options[field[1]] ~= nil
            options[field[1]] = options[field[1]] or field[3]
        end
        config.validate(options)
        if config.exists() or options.yes or not common.succeeds({ "sh", "-c", "test -t 0" }) then return end

        common.info("macOS VM setup — press Enter to accept the defaults.")
        local memory = io.open("/proc/meminfo", "r")
        if memory then
            local kib = tonumber(memory:read("*a"):match("MemTotal:%s+(%d+)"))
            memory:close()
            if kib then common.info(string.format("Host RAM: %.1f GiB", kib / 1024 / 1024)) end
        end
        local cores, detected = common.capture({ "nproc" }, true)
        if detected then common.info("Available CPU cores: " .. cores:gsub("%s+$", "")) end
        common.info("Version 15 is Sequoia; 26 is experimental. On AMD, use at most 8G for initial installation.")
        for _, field in ipairs(fields) do
            local key, label = field[1], field[2]
            if not supplied[key] then
                while true do
                    local previous = options[key]
                    io.write(label .. " [" .. previous .. "]: ")
                    io.flush()
                    local answer = io.read("*l")
                    assert(answer, "Installation cancelled before creating the VM")
                    answer = answer:match("^%s*(.-)%s*$")
                    if answer ~= "" then
                        if key == "ram" or key == "disk" then
                            answer = answer:upper()
                            if answer:match("^%d+$") then answer = answer .. "G" end
                        end
                        options[key] = answer
                    end
                    local valid, message = pcall(config.validate, options)
                    if valid then break end
                    options[key] = previous
                    common.error(tostring(message):gsub("^.-:%d+: ", ""))
                end
            end
        end
        common.info("Resources: " .. options.ram .. " RAM, " .. options.cpus .. " CPU cores, "
            .. options.disk .. " disk; macOS " .. options.macos_version .. ".")
    end

    local function ready()
        assert(common.available("docker"), "Docker is required")
        assert(common.succeeds({ "docker", "compose", "version" }), "Docker Compose is required")
        assert(common.succeeds({ "docker", "info" }),
            "Docker must be running and accessible to your user. Check docker info; enable it with sudo systemctl enable --now docker.")
    end

    local function virtualization()
        local machine, found = common.capture({ "uname", "-m" }, true)
        assert(found and machine:match("^x86_64%s*$"), "Dockur macOS requires an x86_64 host")
        assert(common.succeeds({ "env", "test", "-c", "/dev/kvm" }), "KVM is unavailable; enable CPU virtualization in firmware")
        assert(common.succeeds({ "env", "test", "-c", "/dev/net/tun" }), "The /dev/net/tun device is unavailable")
        assert(common.succeeds({ "grep", "-qw", "avx2", "/proc/cpuinfo" }), "Dockur macOS requires an AVX2-capable processor")
    end

    local function timeout(value, maximum)
        local seconds = tonumber(value)
        assert(seconds and seconds % 1 == 0 and seconds >= 1 and seconds <= maximum,
            "Timeout must be an integer from 1 to " .. maximum .. " seconds")
        return tostring(seconds)
    end

    local function start(options)
        assert(config.prepared(), "macOS VM preparation is not complete. Run luna macos install first.")
        local seconds = timeout(options.timeout, 3600)
        assert(common.available("vncviewer"), "TigerVNC is required (vncviewer); install the tigervnc package")
        assert(os.getenv("DISPLAY") and os.getenv("DISPLAY") ~= "", "Start macOS from a graphical session with X11 or XWayland")
        virtualization()
        common.run({ "bash", directory .. "/session.sh", config.path,
            options.keep_alive and "true" or "false", seconds })
    end

    local function delete(options)
        common.info("Delete the macOS VM and all files inside its virtual disk?")
        common.info("Disk: " .. config.storage)
        common.info("Shared files are kept: " .. config.shared)
        if not options.yes then
            assert(common.succeeds({ "sh", "-c", "test -t 0" }), "Deletion needs an interactive confirmation or --yes")
            io.write("Type delete to confirm: ")
            io.flush()
            if io.read("*l") ~= "delete" then
                common.info("Deletion cancelled.")
                return
            end
        end
        -- Read literal mounts: Compose's rendered output can keep dollar escapes.
        -- Only known literal storage is eligible for automatic deletion; dynamic
        -- environment-based storage needs manual cleanup instead of a guessed path.
        local output, ok = common.capture(compose("config", "--no-interpolate", "--format", "json"), true)
        assert(ok, "Cannot verify macOS storage before deletion")
        local volumes = json.decode(output).services.macos.volumes or {}
        local matched = false
        for _, volume in ipairs(volumes) do
            if volume.target == "/storage" then
                local source = volume.source
                assert(type(source) == "string" and not source:find("[%c]")
                    and not source:gsub("%$%$", ""):find("%$[%w_{]"),
                    "macOS uses dynamic storage; automatic deletion requires a literal storage path")
                source = source:gsub("%$%$", "$")
                assert(volume.type == "bind" and source == config.storage,
                    "macOS uses custom storage. Automatic deletion supports only " .. config.storage)
                matched = true
            end
        end
        assert(matched, "Cannot verify the macOS storage mount; nothing was deleted")
        common.run({ "bash", directory .. "/delete.sh", config.path, config.storage, config.desktop_path, config.shared })
        common.info("macOS VM deleted. Shared files were kept.")
    end

    function M.run(options)
        if options.status and not config.exists() then
            common.info("macOS VM is not installed. Run luna macos install.")
            return
        end
        if options.install then installation_options(options) end
        assert(options.install or config.exists(), "macOS VM is not installed. Run luna macos install.")
        ready()
        if options.delete then
            delete(options)
        elseif options.install then
            local seconds = timeout(options.timeout, 86400)
            virtualization()
            if config.create(options) then
                common.info("Created macOS VM configuration: " .. config.path)
            else
                common.info("Using existing VM configuration and disk; install options do not overwrite them.")
            end
            -- Deletion holds this same lock. Claim it before any container work
            -- and keep it through publishing the marker and desktop entry.
            local ok, _, code = os.execute(common.command({ "flock", "-n", "-E", "75",
                config.directory .. "/install.lock", "/usr/bin/lua", "-E", directory .. "/install.lua", seconds }))
            assert(code ~= 75, "Another macOS install or deletion is active. Wait for it to finish and retry.")
            assert(ok, "macOS preparation failed. Resolve the error above and rerun luna macos install.")
        elseif options.start then
            start(options)
        elseif options.stop then
            common.run({ "bash", root .. "/lib/vm-stop.sh", config.path, "macos" })
        elseif options.status then
            common.run(compose("ps", "--all", "macos"))
        elseif options.logs then
            local tail = tonumber(options.tail)
            assert(tail and tail % 1 == 0 and tail >= 0, "Log tail must be a nonnegative integer")
            local arguments = compose("logs", "--tail", tostring(tail))
            if not options.no_follow then table.insert(arguments, "--follow") end
            table.insert(arguments, "macos")
            common.run(arguments)
        end
    end

    return M
end
