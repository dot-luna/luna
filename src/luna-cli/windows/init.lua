-- Manage Dockur's persistent Windows VM and an attached FreeRDP desktop session.
return function(common, directory)
    local root = directory .. "/../../.."
    local config = dofile(directory .. "/config.lua")(common, root)
    local json = dofile(root .. "/lib/theme/json.lua")
    local M = {}

    function M.register(parser)
        local command = parser:command("windows win", "Install and control the Windows VM.")
        command:require_command(false)
        local install = command:command("install", "Download and install Windows, waiting until its desktop is ready.")
        install:option("--timeout", "Seconds to wait for Windows installation"):default("7200")
        install:option("--ram", "Memory in GiB (default 4G)")
        install:option("--cpus", "Number of virtual CPU cores (default 2)")
        install:option("--disk", "Virtual disk capacity in GiB, at least 64G (default 64G)")
        install:option("--username", "Initial Windows account name (default luna)")
        install:flag("--yes -y", "Use defaults for unspecified options without prompting")
        local start = command:command("start", "Start Windows and attach to its desktop until the RDP window closes.")
        start:flag("--keep-alive -k", "Leave the VM running after the desktop session ends")
        start:option("--timeout", "Seconds to wait for RDP on startup"):default("120")
        command:command("stop", "Gracefully stop the VM, preserving its disk.")
        command:command("status", "Show the VM container status.")
        local delete = command:command("delete remove", "Delete the Windows VM, disk, configuration, and launcher; keep shared files.")
        delete:flag("--yes -y", "Confirm permanent deletion without prompting")
        local logs = command:command("logs", "Follow the VM logs; Ctrl+C ends log viewing only.")
        logs:flag("--no-follow", "Print recent logs and exit")
        logs:option("--tail", "Number of recent lines to show"):default("100")
        return command
    end

    local function compose(...)
        local arguments = { "docker", "compose", "--project-name", "luna-windows", "--file", config.path }
        for _, value in ipairs({ ... }) do table.insert(arguments, value) end
        return arguments
    end

    -- Ask only for new-VM settings that were not explicitly supplied as flags.
    -- Existing disks and credentials must survive retries of an interrupted install.
    local function installation_options(options)
        local fields = {
            { "ram", "RAM (GiB, e.g. 8G)", "4G" },
            { "cpus", "CPU cores", "2" },
            { "disk", "Disk capacity (GiB, minimum 64G)", "64G" },
            { "username", "Windows username", "luna" },
        }
        local supplied = {}
        for _, field in ipairs(fields) do
            supplied[field[1]] = options[field[1]] ~= nil
            options[field[1]] = options[field[1]] or field[3]
        end
        config.validate(options)
        local interactive = not config.exists() and not options.yes
            and common.succeeds({ "sh", "-c", "test -t 0" })
        if not interactive then return end

        common.info("Windows VM setup — press Enter to accept the defaults.")
        local memory = io.open("/proc/meminfo", "r")
        if memory then
            local kib = tonumber(memory:read("*a"):match("MemTotal:%s+(%d+)"))
            memory:close()
            if kib then common.info(string.format("Host RAM: %.1f GiB", kib / 1024 / 1024)) end
        end
        local cores, detected = common.capture({ "nproc" }, true)
        if detected then common.info("Available CPU cores: " .. cores:gsub("%s+$", "")) end
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
        common.info("Resources: " .. options.ram .. " RAM, " .. options.cpus .. " CPU cores, " .. options.disk .. " disk.")
    end

    local function ready()
        assert(common.available("docker"), "Docker is required")
        assert(common.succeeds({ "docker", "compose", "version" }), "Docker Compose is required")
        assert(common.succeeds({ "docker", "info" }),
            "Docker must be running and accessible to your user. Check docker info; enable it with sudo systemctl enable --now docker.")
    end

    local function virtualization()
        assert(common.succeeds({ "env", "test", "-c", "/dev/kvm" }), "KVM is unavailable; enable CPU virtualization in firmware")
        assert(common.succeeds({ "env", "test", "-c", "/dev/net/tun" }), "The /dev/net/tun device is unavailable")
    end

    local function write(path, content)
        local file = assert(io.open(path, "w"))
        assert(file:write(content))
        assert(file:close())
        common.run({ "chmod", "600", "--", path })
    end

    local function start(options)
        assert(config.installed(), "Windows installation is not complete. Run luna windows install to finish setup.")
        local timeout = tonumber(options.timeout)
        assert(timeout and timeout % 1 == 0 and timeout >= 1 and timeout <= 3600,
            "Timeout must be an integer from 1 to 3600 seconds")
        assert(common.available("xfreerdp3"), "FreeRDP 3 is required (xfreerdp3)")
        assert(os.getenv("WAYLAND_DISPLAY") or os.getenv("DISPLAY"), "Start Windows from a graphical session")
        virtualization()
        -- Resolve credentials through Compose so edits and its escaping rules stay consistent.
        local output, ok = common.capture(compose("config", "--format", "json"), true)
        assert(ok, "Cannot read Windows Compose configuration")
        local environment = json.decode(output).services.windows.environment
        local username, password = environment.USERNAME, environment.PASSWORD
        assert(type(username) == "string" and username ~= "" and not username:find("[%c]"), "Invalid Windows username")
        assert(type(password) == "string" and password ~= "" and not password:find("[%c]"), "Invalid Windows password")
        local arguments = {
            "/u:" .. username, "/p:" .. password, "/v:127.0.0.1:3389", "-grab-keyboard",
            "/sound", "/microphone", "/clipboard", "/cert:ignore", "/title:Windows - Luna",
            "/dynamic-resolution", "/gfx:AVC444", "/f", "/floatbar:sticky:off,default:visible,show:fullscreen",
        }
        if common.available("hyprctl") then
            local monitors, read = common.capture({ "hyprctl", "monitors", "-j" }, true)
            local valid, values = pcall(json.decode, monitors)
            if read and valid and type(values) == "table" then
                for _, monitor in ipairs(values) do
                    if monitor.focused and type(monitor.scale) == "number" then
                        if monitor.scale >= 1.7 then table.insert(arguments, "/scale:180")
                        elseif monitor.scale >= 1.3 then table.insert(arguments, "/scale:140") end
                    end
                end
            end
        end
        write(config.directory .. "/krb5.conf", "[libdefaults]\n  dns_lookup_kdc = false\n  dns_lookup_realm = false\n")
        local temporary, created = common.capture({ "mktemp", config.directory .. "/.rdp-XXXXXX" })
        assert(created, "Cannot create private RDP arguments file")
        temporary = temporary:gsub("\n$", "")
        local success, failure = pcall(function()
            write(temporary, table.concat(arguments, "\n") .. "\n")
            common.run({ "bash", directory .. "/session.sh", config.path, temporary,
                options.keep_alive and "true" or "false", tostring(timeout) })
        end)
        os.remove(temporary)
        assert(success, failure)
    end

    local function delete(options)
        common.info("Delete the Windows VM and all files inside its virtual disk?")
        common.info("Disk: " .. config.storage)
        common.info("Shared files are kept: " .. config.shared)
        if not options.yes then
            assert(common.succeeds({ "sh", "-c", "test -t 0" }),
                "Deletion needs an interactive confirmation or --yes")
            io.write("Type delete to confirm: ")
            io.flush()
            if io.read("*l") ~= "delete" then
                common.info("Deletion cancelled.")
                return
            end
        end
        -- Never infer deletion targets from arbitrary user-edited Compose mounts.
        local output, ok = common.capture(compose("config", "--format", "json"), true)
        assert(ok, "Cannot verify Windows storage before deletion")
        local volumes = json.decode(output).services.windows.volumes or {}
        local matched = false
        for _, volume in ipairs(volumes) do
            if volume.target == "/storage" then
                assert(volume.type == "bind" and volume.source == config.storage,
                    "Windows uses custom storage. Automatic deletion supports only " .. config.storage)
                matched = true
            end
        end
        assert(matched, "Cannot verify the Windows storage mount; nothing was deleted")
        common.run({ "bash", directory .. "/delete.sh", config.path, config.storage,
            config.desktop_path, config.shared })
        common.info("Windows VM deleted. Shared files were kept.")
    end

    function M.run(options)
        if options.status and not config.exists() then
            common.info("Windows VM is not installed. Run luna windows install.")
            return
        end
        if options.install then installation_options(options) end
        assert(options.install or config.exists(), "Windows VM is not installed. Run luna windows install.")
        ready()
        if options.delete then
            delete(options)
        elseif options.install then
            local timeout = tonumber(options.timeout)
            assert(timeout and timeout % 1 == 0 and timeout >= 1 and timeout <= 86400,
                "Installation timeout must be an integer from 1 to 86400 seconds")
            virtualization()
            if config.create(options) then
                common.info("Created Windows 11 VM configuration: " .. config.path)
            else
                common.info("Using existing VM configuration and disk; install options do not overwrite them.")
            end
            common.run(compose("pull", "windows"))
            common.run(compose("up", "-d", "windows"))
            common.info("Waiting for Windows download and installation to finish. This may take a while.")
            common.info("Watch progress at http://127.0.0.1:8006 or in another terminal with luna windows logs.")
            common.run({ "flock", "-n", config.directory .. "/install.lock",
                "bash", directory .. "/wait-ready.sh", config.path, tostring(timeout) })
            write(config.installed_path, "Windows setup completed and RDP is ready.\n")
            config.install_desktop_entry()
            common.info("Windows installed successfully. Open Windows from the application launcher or run luna windows start.")
        elseif options.start then
            start(options)
        elseif options.stop then
            common.run(compose("stop", "--timeout", "120", "windows"))
        elseif options.status then
            common.run(compose("ps", "--all", "windows"))
        elseif options.logs then
            local tail = tonumber(options.tail)
            assert(tail and tail % 1 == 0 and tail >= 0, "Log tail must be a nonnegative integer")
            local arguments = compose("logs", "--tail", tostring(tail))
            if not options.no_follow then table.insert(arguments, "--follow") end
            table.insert(arguments, "windows")
            common.run(arguments)
        end
    end

    return M
end
