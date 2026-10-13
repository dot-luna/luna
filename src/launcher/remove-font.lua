-- Menu-only removal adapter; the shared CLI resolver validates every target.
local directory = arg[0]:match("^(.*)/") or "."
local root = directory .. "/../.."
local common = dofile(root .. "/lib/common.lua")
local fonts = dofile(root .. "/src/luna-cli/font/init.lua")(common, root .. "/src/luna-cli/font")
local ok, message = pcall(function()
    assert(arg[1] and arg[1] ~= "", "A font package or file is required")
    common.info("Checking selected fonts…")
    io.stdout:flush()
    fonts.run({ remove = true, names = { table.unpack(arg, 1, #arg) }, menu_confirm = true })
end)

if ok then
    common.info("\nRemoval complete.")
else
    common.error("\nRemoval failed: " .. tostring(message))
end
io.stdout:write("\nPress Enter to close…")
io.stdout:flush()
io.read("*l")
os.exit(ok and 0 or 1)
