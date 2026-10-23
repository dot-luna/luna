#!/usr/bin/lua -E
-- Install one manifest group after lua.sh prepares the system Lua runtime.
-- Resolve shared helpers before setup; never rely on the caller's cwd.
local script_dir = assert(arg[0]:match("^(.*)/"), "Run this script using its path")
local common = dofile(script_dir .. "/../../lib/common.lua")
common.setup_logging()

local groups = { core = true, main = true, fonts = true, extra = true }
local selected_group

-- Only the first recognized group matters; extra arguments are ignored.
for _, value in ipairs(arg) do
    if groups[value] then
        selected_group = value
        break
    end
end

if not selected_group then
    common.warn("No package group selected; skipping packages.")
    return
end

local function install()
    -- Resolve the manifest from the script, not the caller's working directory.
    local manifest = dofile(script_dir .. "/../../packages/packages.lua")
    assert(type(manifest) == "table", "Package manifest must contain package groups")
    local packages = { pacman = {}, aur = {} }
    local seen = {}

    -- Validate the entire manifest before any installation. Core is pacman-only.
    for _, group in ipairs({ "core", "main", "fonts", "extra" }) do
        local entries = manifest[group]
        assert(type(entries) == "table", "Package group must be a list: " .. group)
        local count = 0
        for key in pairs(entries) do
            assert(type(key) == "number" and key % 1 == 0 and key >= 1 and key <= #entries,
                "Package group must be a contiguous list: " .. group)
            count = count + 1
        end
        assert(count == #entries, "Package group must be a contiguous list: " .. group)

        for _, entry in ipairs(entries) do
            assert(type(entry) == "table", "Invalid package entry in " .. group)
            assert(type(entry.name) == "string" and entry.name:match("^[%w@._+%-]+$"), "Invalid package name")
            assert(packages[entry.source], "Invalid package source")
            assert(not seen[entry.name], "Duplicate package: " .. entry.name)
            assert(group ~= "core" or entry.source == "pacman", "Never put AUR packages in core")
            seen[entry.name] = true

            if group == selected_group then
                table.insert(packages[entry.source], entry.name)
            end
        end
    end

    if #packages.pacman == 0 and #packages.aur == 0 then
        common.info("No packages configured for " .. selected_group .. ".")
        return
    end

    -- Missing AUR support must not block packages from official repositories.
    local helper
    local skipped_aur = false
    if #packages.aur > 0 then
        if common.is_root() then
            common.warn("AUR packages skipped: they require a regular user.")
        else
            helper = common.available("yay") and "yay" or common.available("paru") and "paru"
            if not helper then
                common.warn("AUR packages skipped: no helper is available.")
            end
        end
        if not helper then
            packages.aur = {}
            skipped_aur = true
        end
    end

    if #packages.pacman == 0 and #packages.aur == 0 then
        return
    end
    assert(common.available("pacman"), "pacman is required")

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

            -- Include installed targets so upgrades are checked on every run;
            -- --needed skips reinstalling packages that are already current.
            table.insert(arguments, "--needed")
            table.insert(arguments, "--")
            for _, name in ipairs(names) do
                table.insert(arguments, name)
            end

            -- Sudo can still authenticate; package confirmations use their defaults.
            -- Verify each target rather than relying only on the command's status.
            local suffix = #names == 1 and "" or "s"
            common.info(string.format("Installing or updating %d package%s for %s.", #names, suffix, selected_group))
            common.run(arguments)
            for _, name in ipairs(names) do
                assert(common.succeeds({ "pacman", "-Q", "--", name }), "Package was not installed: " .. name)
            end
        end
    end

    if not skipped_aur then
        common.success("Dependencies ready: " .. selected_group)
    end
end

local ok, error_message = pcall(install)
if not ok then
    common.error("Dependency setup failed: " .. tostring(error_message))
    os.exit(1)
end
