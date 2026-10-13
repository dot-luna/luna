-- Menu-only adapter: reuse font installation while retaining logs until Enter.
local directory = arg[0]:match("^(.*)/") or "."
local root = directory .. "/../.."
local common = dofile(root .. "/lib/common.lua")
local fonts = dofile(root .. "/src/luna-cli/font/init.lua")(common, root .. "/src/luna-cli/font")
local ok, message = pcall(function()
    assert(#arg > 0 and #arg % 2 == 0, "Font package/source pairs are required")
    local repository, aur, seen = {}, {}, {}
    -- Validate the complete selection before starting either package transaction.
    for index = 1, #arg, 2 do
        local name, source = arg[index], arg[index + 1]
        assert(name:match("^[%w@._+%-]+$"), "Invalid font package")
        assert(source:match("^[%w@._+%-]+$"), "Invalid package source")
        if not seen[name] then
            seen[name] = true
            table.insert(source == "aur" and aur or repository, name)
        end
    end
    if #aur > 0 then
        local packages = dofile(root .. "/src/luna-cli/font/packages.lua")(common)
        packages.helper()
        assert(not common.is_root(), "AUR installation must run as a normal user")
    end
    for _, batch in ipairs({ { targets = repository, aur = false }, { targets = aur, aur = true } }) do
        if #batch.targets > 0 then
            common.info("Installing " .. table.concat(batch.targets, ", ") .. "…")
            batch.install, batch.menu_confirm = true, true
            fonts.run(batch)
        end
    end
end)

if ok then
    common.info("\nInstallation complete.")
else
    common.error("\nInstallation failed: " .. tostring(message))
end
io.stdout:write("\nPress Enter to close…")
io.stdout:flush()
io.read("*l")
os.exit(ok and 0 or 1)
