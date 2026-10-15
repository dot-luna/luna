#!/usr/bin/lua -E
-- Install one manifest group after lua.sh prepares Lua and argparse.
-- Resolve shared helpers before parsing commands; never rely on the caller's cwd.
local script_dir = assert(arg[0]:match("^(.*)/"), "Run this script using its path")
local common = dofile(script_dir .. "/../../lib/common.lua")
common.setup_logging()
local argparse = require("argparse")
local parser = argparse("install-deps.lua", "Install a Luna package group.")
parser:argument("group", "Package group"):choices({ "core", "main", "fonts", "extra" })
parser:flag("--force", "Reinstall packages even when already installed")
local options = parser:parse()

local function install()
    -- Resolve the manifest from the script, not the caller's working directory.
    local manifest = dofile(script_dir .. "/../../packages/packages.lua")
    local packages = { pacman = {}, aur = {} }
    local seen = {}
    local installed = 0

    -- Validate the entire manifest before any installation. Core is pacman-only.
    for _, group in ipairs({ "core", "main", "fonts", "extra" }) do
        assert(type(manifest[group]) == "table", "Missing group: " .. group)
        for _, entry in ipairs(manifest[group]) do
            assert(type(entry.name) == "string" and entry.name:match("^[%w@._+%-]+$"), "Invalid package name")
            assert(packages[entry.source], "Invalid package source")
            assert(not seen[entry.name], "Duplicate package: " .. entry.name)
            assert(group ~= "core" or entry.source == "pacman", "Never put AUR packages in core")
            seen[entry.name] = true

            if group == options.group then
                if options.force or not common.succeeds({ "pacman", "-Q", "--", entry.name }) then
                    table.insert(packages[entry.source], entry.name)
                else
                    installed = installed + 1
                end
            end
        end
    end

    if installed > 0 then
        local noun = installed == 1 and "package" or "packages"
        common.info(string.format("%s: %d %s already installed.", options.group, installed, noun))
    end

    -- Preflight both sources so a missing helper cannot cause a partial group install.
    assert(common.available("pacman"), "pacman is required")
    local helper
    if #packages.aur > 0 then
        assert(not common.is_root(), "Run AUR installation as a normal user")
        helper = common.available("yay") and "yay" or common.available("paru") and "paru"
        assert(helper, "Run scripts/setup/aur.sh first")
    end

    for _, source in ipairs({ "pacman", "aur" }) do
        local names = packages[source]
        if #names > 0 then
            local arguments
            if source == "pacman" then
                arguments = { "pacman", "-Syu", "--noconfirm" }
                if not common.is_root() then
                    assert(common.available("sudo"), "sudo is required")
                    table.insert(arguments, 1, "sudo")
                end
            else
                arguments = { helper, "-S", "--noconfirm" }
                -- AUR helpers have review menus in addition to pacman confirmation.
                if helper == "yay" then
                    local review_options = {
                        "--answerclean", "None", "--answerdiff", "None",
                        "--answeredit", "None", "--noremovemake",
                    }
                    for _, value in ipairs(review_options) do
                        table.insert(arguments, value)
                    end
                else
                    table.insert(arguments, "--skipreview")
                    table.insert(arguments, "--noremovemake")
                end
            end

            if not options.force then
                table.insert(arguments, "--needed")
            end
            table.insert(arguments, "--")
            for _, name in ipairs(names) do
                table.insert(arguments, name)
            end

            -- Sudo can still authenticate; package confirmations use their defaults.
            -- Verify each target rather than relying only on the command's status.
            local suffix = #names == 1 and "" or "s"
            common.info(string.format("Installing %d %s package%s for %s.", #names, source, suffix, options.group))
            common.run(arguments)
            for _, name in ipairs(names) do
                assert(common.succeeds({ "pacman", "-Q", "--", name }), "Package was not installed: " .. name)
            end
        end
    end

    common.success("Dependencies ready: " .. options.group)
end

local ok, error_message = pcall(install)
if not ok then
    common.error("Dependency setup failed: " .. tostring(error_message))
    os.exit(1)
end
