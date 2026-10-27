-- Generate the persistent Dockur macOS project without replacing an existing VM.
return function(common, root)
    local json = dofile(root .. "/lib/json.lua")

    -- Empty XDG variables use the same defaults as unset variables.
    local function absolute(value, name)
        assert(type(value) == "string" and value:sub(1, 1) == "/",
            name .. " must be an absolute path")
        assert(not value:find("[%c]"), name .. " cannot contain control characters")
        return value
    end

    local home = absolute(os.getenv("HOME"), "HOME")
    local function xdg(name, fallback)
        local value = os.getenv(name)
        return absolute(value and value ~= "" and value or fallback, name)
    end

    local config_home = xdg("XDG_CONFIG_HOME", home .. "/.config")
    local data_home = xdg("XDG_DATA_HOME", home .. "/.local/share")
    local M = {
        directory = config_home .. "/luna/macos",
        storage = data_home .. "/luna/macos/storage",
        shared = home .. "/macOS",
    }
    M.path = M.directory .. "/compose.yml"
    M.prepared_path = M.directory .. "/prepared"
    M.desktop_path = data_home .. "/applications/luna-macos.desktop"

    -- The caller records console readiness; this does not mean macOS is installed.
    function M.prepared()
        local file = io.open(M.prepared_path, "r")
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

    -- Return validated defaults without modifying the caller's interactive options.
    function M.validate(options)
        options = options or {}
        local values = {
            ram = options.ram == nil and "4G" or options.ram,
            cpus = options.cpus == nil and "2" or options.cpus,
            disk = options.disk == nil and "64G" or options.disk,
            macos_version = options.macos_version == nil and "15" or tostring(options.macos_version),
        }
        local function size(value, minimum, name)
            local number = type(value) == "string" and value:match("^(%d+)G$")
            assert(number and tonumber(number) >= minimum and tonumber(number) <= 65536,
                name .. " must be a whole number of GiB ending in G (minimum " .. minimum .. "G)")
        end

        size(values.ram, 4, "RAM")
        size(values.disk, 64, "Disk")
        local cpus = tonumber(values.cpus)
        -- Use topologies Dockur can represent exactly; some other counts are
        -- silently rounded or rejected by its macOS-specific CPU configuration.
        local cores = { [1] = true, [2] = true, [4] = true, [6] = true, [8] = true,
            [10] = true, [12] = true, [14] = true, [16] = true, [24] = true, [32] = true, [64] = true }
        assert(cores[cpus], "CPU count must be one of 1, 2, 4, 6, 8, 10, 12, 14, 16, 24, 32, or 64")
        values.cpus = string.format("%.0f", cpus)
        local versions = { ["11"] = true, ["12"] = true, ["13"] = true, ["14"] = true, ["15"] = true, ["26"] = true }
        assert(versions[values.macos_version], "macOS version must be 11, 12, 13, 14, 15, or 26")
        return values
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

        -- Use the bundled monitor icon regardless of the installed icon theme.
        local icon, icon_found = common.capture({ "realpath", "-e", "--", root .. "/src/luna-cli/macos/macos.svg" })
        assert(icon_found, "Cannot locate the macOS icon")
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
        local temporary, created = common.capture({ "mktemp", applications .. "/.luna-macos-XXXXXX" })
        assert(created, "Cannot create macOS desktop entry")
        temporary = temporary:gsub("\n$", "")
        local file = assert(io.open(temporary, "w"))
        assert(file:write(table.concat({
            "[Desktop Entry]", "Type=Application", "Name=macOS", "Comment=macOS virtual machine",
            'Exec="' .. escaped .. '" macos start', "Icon=" .. icon, "Terminal=false",
            "Categories=System;Emulator;", "Keywords=macOS;VM;VNC;Dockur;", "StartupNotify=false", "",
        }, "\n")))
        assert(file:close())
        common.run({ "chmod", "644", "--", temporary })
        assert(os.rename(temporary, M.desktop_path))
    end

    function M.create(options)
        local values = M.validate(options)
        if M.exists() then return false end

        -- A leftover directory from interrupted setup is safe to reuse.
        common.run({ "mkdir", "-p", "-m", "700", "--", M.directory })
        common.run({ "chmod", "700", "--", M.directory })
        common.run({ "mkdir", "-p", "--", M.storage, M.shared })
        local content = table.concat({
            "# Generated by luna macos install. Edit resource values here before starting.",
            "# Create your account in the macOS installer after the console opens.",
            "services:",
            "  macos:",
            "    image: dockurr/macos:latest",
            "    environment:",
            "      VERSION: " .. yaml(values.macos_version),
            "      RAM_SIZE: " .. yaml(values.ram),
            "      CPU_CORES: " .. yaml(values.cpus),
            "      DISK_SIZE: " .. yaml(values.disk),
            "      MANUAL: \"Y\"",
            "      TIMEOUT: \"105\"",
            "    devices:",
            "      - /dev/kvm",
            "      - /dev/net/tun",
            "    cap_add:",
            "      - NET_ADMIN",
            "    ports:",
            "      - \"127.0.0.1:8007:8006\"",
            "      - \"127.0.0.1:5900:5900/tcp\"",
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

        -- Publish a complete private file without replacing a concurrent install.
        -- Hard links make the destination claim atomic; retries preserve the winner.
        local temporary, captured = common.capture({ "mktemp", M.directory .. "/.compose-XXXXXX" })
        assert(captured, "Cannot create macOS configuration")
        temporary = temporary:gsub("\n$", "")
        local ok, created = pcall(function()
            local file = assert(io.open(temporary, "w"))
            local written, write_error = file:write(content)
            local closed, close_error = file:close()
            assert(written, write_error)
            assert(closed, close_error)
            common.run({ "chmod", "600", "--", temporary })
            if common.succeeds({ "ln", "-T", "--", temporary, M.path }) then
                return true
            end
            assert(M.exists(), "Cannot publish macOS configuration: " .. M.path)
            return false
        end)
        assert(os.remove(temporary))
        assert(ok, created)
        return created
    end

    return M
end
