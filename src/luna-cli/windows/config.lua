-- Generate one persistent Compose project; installation never overwrites an existing VM.
return function(common, root)
    local json = dofile(root .. "/lib/json.lua")
    local home = assert(os.getenv("HOME"))
    local config_home = os.getenv("XDG_CONFIG_HOME") or home .. "/.config"
    local data_home = os.getenv("XDG_DATA_HOME") or home .. "/.local/share"
    local M = {
        directory = config_home .. "/luna/windows",
        storage = data_home .. "/luna/windows/storage",
        shared = home .. "/Windows",
    }
    M.path = M.directory .. "/compose.yml"
    M.installed_path = M.directory .. "/installed"
    M.desktop_path = data_home .. "/applications/luna-windows.desktop"

    function M.installed()
        local file = io.open(M.installed_path, "r")
        if not file then return false end
        file:close()
        return true
    end

    function M.exists()
        local file = io.open(M.path, "r")
        if not file then return false end
        file:close()
        return true
    end

    function M.validate(options)
        local function size(value, minimum, name)
            local number = type(value) == "string" and value:match("^(%d+)G$")
            assert(number and tonumber(number) >= minimum and tonumber(number) <= 65536,
                name .. " must be a whole number of GiB ending in G (minimum " .. minimum .. "G)")
        end
        size(options.ram, 2, "RAM")
        size(options.disk, 64, "Disk")
        local cpus = tonumber(options.cpus)
        assert(cpus and cpus % 1 == 0 and cpus >= 1 and cpus <= 256, "CPU count must be an integer from 1 to 256")
        assert(options.username:match("^[a-zA-Z][a-zA-Z0-9_-]*$") and #options.username <= 20,
            "Username must start with a letter and contain at most 20 letters, numbers, underscores, or hyphens")
    end

    -- JSON quoted strings are valid YAML scalars. Compose additionally interprets $.
    local function yaml(value)
        assert(not value:find("[%c]"), "Configuration paths cannot contain control characters")
        return json.encode(value:gsub("%$", "$$"))
    end

    function M.install_desktop_entry()
        local applications = data_home .. "/applications"
        common.run({ "mkdir", "-p", "--", applications })
        local launcher, found = common.capture({ "realpath", "-e", "--", root .. "/bin/luna" })
        assert(found, "Cannot locate the Luna launcher")
        launcher = launcher:gsub("\n$", "")
        assert(not launcher:find("[%c]"), "Launcher path cannot contain control characters")

        -- Use the bundled logo regardless of the installed icon theme.
        local icon, icon_found = common.capture({ "realpath", "-e", "--", root .. "/src/luna-cli/windows/windows.svg" })
        assert(icon_found, "Cannot locate the Windows icon")
        icon = icon:gsub("\n$", "")
        assert(not icon:find("[%c]"), "Icon path cannot contain control characters")
        icon = icon:gsub("\\", "\\\\")

        -- Desktop Exec has its own quoting and percent field codes, not shell quoting.
        local escaped = launcher:gsub(".", function(character)
            if character == "\\" then return string.rep("\\", 4) end
            if character == '"' or character == "$" or character == "`" then
                return string.rep("\\", 2) .. character
            end
            return character == "%" and "%%" or character
        end)
        local temporary, created = common.capture({ "mktemp", applications .. "/.luna-windows-XXXXXX" })
        assert(created, "Cannot create Windows desktop entry")
        temporary = temporary:gsub("\n$", "")
        local file = assert(io.open(temporary, "w"))
        assert(file:write(table.concat({
            "[Desktop Entry]", "Type=Application", "Name=Windows", "Comment=Windows virtual machine",
            'Exec="' .. escaped .. '" windows start', "Icon=" .. icon, "Terminal=false",
            "Categories=System;Emulator;", "Keywords=Windows;VM;RDP;Dockur;", "StartupNotify=false", "",
        }, "\n")))
        assert(file:close())
        common.run({ "chmod", "644", "--", temporary })
        assert(os.rename(temporary, applications .. "/luna-windows.desktop"))
    end

    function M.create(options)
        M.validate(options)
        if M.exists() then return false end
        common.run({ "mkdir", "-p", "--", config_home .. "/luna" })
        -- mkdir without -p is an exclusive claim: concurrent installs cannot replace credentials.
        assert(common.succeeds({ "mkdir", "-m", "700", "--", M.directory }),
            "Windows config directory already exists without compose.yml; inspect " .. M.directory)
        local random = assert(io.open("/dev/urandom", "rb"))
        local bytes = assert(random:read(16))
        random:close()
        assert(#bytes == 16, "Cannot generate Windows credentials")
        local password = bytes:gsub(".", function(byte) return string.format("%02x", byte:byte()) end)
        local content = table.concat({
            "# Generated by luna windows install. Edit resource values here before starting.",
            "services:",
            "  windows:",
            "    image: dockurr/windows:latest",
            "    environment:",
            "      VERSION: \"11\"",
            "      RAM_SIZE: " .. yaml(options.ram),
            "      CPU_CORES: " .. yaml(tostring(tonumber(options.cpus))),
            "      DISK_SIZE: " .. yaml(options.disk),
            "      USERNAME: " .. yaml(options.username),
            "      PASSWORD: " .. yaml(password),
            "    devices:",
            "      - /dev/kvm",
            "      - /dev/net/tun",
            "    cap_add:",
            "      - NET_ADMIN",
            "    ports:",
            "      - \"127.0.0.1:8006:8006\"",
            "      - \"127.0.0.1:3389:3389/tcp\"",
            "      - \"127.0.0.1:3389:3389/udp\"",
            "    volumes:",
            "      - type: bind",
            "        source: " .. yaml(M.storage),
            "        target: /storage",
            "      - type: bind",
            "        source: " .. yaml(M.shared),
            "        target: /shared",
            "    restart: \"no\"",
            "    stop_grace_period: 2m",
            "",
        }, "\n")
        local file = assert(io.open(M.path, "w"))
        assert(file:write(content))
        assert(file:close())
        common.run({ "chmod", "600", "--", M.path })
        common.run({ "mkdir", "-p", "--", M.storage, M.shared })
        return true
    end

    return M
end
