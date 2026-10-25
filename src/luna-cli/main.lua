#!/usr/bin/lua -E
-- Luna CLI entry point. Run with Lua after scripts/setup/lua.sh prepares argparse.

-- Locate shared helpers relative to this file, independently of the caller's cwd.
local source_dir = arg[0]:match("^(.*)/") or "."

-- Report the checkout version even before argparse or desktop modules are ready.
local function show_version()
    local file, message = io.open(source_dir .. "/../../VERSION", "r")
    if not file then
        io.stderr:write("Cannot read Luna version: " .. tostring(message) .. "\n")
        os.exit(1)
    end

    local version = file:read("*l")
    file:close()
    if not version or not version:match("%S") then
        io.stderr:write("Luna VERSION file is empty.\n")
        os.exit(1)
    end
    print("luna " .. version)
end

if #arg == 1 and (arg[1] == "--version" or arg[1] == "-v") then
    show_version()
    return
end

local common = dofile(source_dir .. "/../../lib/common.lua")
local argparse = require("argparse")

-- Command implementations live in their own directories; argparse owns usage errors.
local parser = argparse("luna", "Luna personal Arch desktop tools.")
parser:require_command(false)
parser:flag("-v --version", "Show Luna version and exit.")
local fonts = dofile(source_dir .. "/font/init.lua")(common, source_dir .. "/font")
local font_parser = fonts.register(parser)
local wallpapers = dofile(source_dir .. "/wallpaper/init.lua")(common, source_dir .. "/wallpaper")
local wallpaper_parser = wallpapers.register(parser)
local themes = dofile(source_dir .. "/theme/init.lua")(common, source_dir .. "/theme")
local theme_parser = themes.register(parser)
local settings = dofile(source_dir .. "/settings/init.lua")(common, source_dir .. "/settings")
settings.register(parser)
local bar = dofile(source_dir .. "/bar/init.lua")(common, source_dir .. "/bar")
bar.register(parser)
local launcher = dofile(source_dir .. "/launcher/init.lua")(common, source_dir .. "/launcher")
launcher.register(parser)
local windows = dofile(source_dir .. "/windows/init.lua")(common, source_dir .. "/windows")
local windows_parser = windows.register(parser)
local macos = dofile(source_dir .. "/macos/init.lua")(common, source_dir .. "/macos")
local macos_parser = macos.register(parser)
local lock = dofile(source_dir .. "/lock/init.lua")(common, source_dir .. "/lock")
lock.register(parser)
local sleep = dofile(source_dir .. "/sleep/init.lua")(common, source_dir .. "/sleep")
sleep.register(parser)
local screensaver = dofile(source_dir .. "/screensaver/init.lua")(common, source_dir .. "/screensaver")
screensaver.register(parser)
local clipboard = dofile(source_dir .. "/clipboard/init.lua")(common, source_dir .. "/clipboard")
clipboard.register(parser)
local insert = dofile(source_dir .. "/insert/init.lua")(common, source_dir .. "/insert")
insert.register(parser)
local screenshot = dofile(source_dir .. "/screenshot/init.lua")(common, source_dir .. "/screenshot")
screenshot.register(parser)
local notifications = dofile(source_dir .. "/notifications/init.lua")(common, source_dir .. "/notifications")
notifications.register(parser)
local auth = dofile(source_dir .. "/auth/init.lua")(common, source_dir .. "/auth")
auth.register(parser)
local control = dofile(source_dir .. "/control/init.lua")(common, source_dir .. "/control")
control.register(parser)
local record = dofile(source_dir .. "/record/init.lua")(common, source_dir .. "/record")
record.register(parser)
local options = parser:parse()

if options.version then
    show_version()
    return
end

-- Bare entry points show help rather than performing any system operation.
if options.auth or options.control or options.record then
    local handler = options.auth and auth or options.control and control or record
    local ok, message = pcall(handler.run, options)
    if not ok then
        common.error(tostring(message))
        os.exit(1)
    end
elseif options.notifications then
    local ok, message = pcall(notifications.run, options)
    if not ok then
        common.error("Notifications command failed: " .. tostring(message))
        os.exit(1)
    end
elseif options.screenshot then
    local ok, message = pcall(screenshot.run, options)
    if not ok then
        common.error("Screenshot command failed: " .. tostring(message))
        os.exit(1)
    end
elseif options.insert then
    local ok, message = pcall(insert.run, options)
    if not ok then
        common.error("Insert command failed: " .. tostring(message))
        os.exit(1)
    end
elseif options.clipboard then
    local ok, message = pcall(clipboard.run, options)
    if not ok then
        common.error("Clipboard command failed: " .. tostring(message))
        os.exit(1)
    end
elseif options.screensaver or options.idle or options.awake then
    local ok, message = pcall(screensaver.run, options)
    if not ok then
        common.error("Screensaver command failed: " .. tostring(message))
        os.exit(1)
    end
elseif options.macos then
    if not (options.install or options.start or options.stop or options.status or options.logs or options.delete) then
        common.info(macos_parser:get_help())
    else
        local ok, message = pcall(macos.run, options)
        if not ok then
            common.error("macOS command failed: " .. tostring(message))
            os.exit(1)
        end
    end
elseif options.windows then
    if not (options.install or options.start or options.stop or options.status or options.logs or options.delete) then
        common.info(windows_parser:get_help())
    else
        local ok, message = pcall(windows.run, options)
        if not ok then
            common.error("Windows command failed: " .. tostring(message))
            os.exit(1)
        end
    end
elseif options.settings or options.bar or options.launcher or options.lock or options.suspend or options.hibernate then
    local handler = options.settings and settings or options.bar and bar or options.lock and lock or (options.suspend or options.hibernate) and sleep or launcher
    local ok, message = pcall(handler.run, options)
    if not ok then
        local label = options.settings and "Settings" or options.bar and "Bar" or options.lock and "Lock" or (options.suspend or options.hibernate) and "Sleep" or "Launcher"
        common.error(label .. " command failed: " .. tostring(message))
        os.exit(1)
    end
elseif not options.font and not options.wallpaper and not options.theme then
    common.info(parser:get_help())
elseif options.font and not (options.search or options.install or options.remove or options.list or options.refresh or options.families or options.set) then
    common.info(font_parser:get_help())
elseif options.wallpaper and not (options.add or options.set or options.remove or options.list
    or options.random or options.current or options.dir or options.open or options.start) then
    common.info(wallpaper_parser:get_help())
elseif options.theme and not (options.install or options.list or options.current or options.path
    or options.set or options.remove or options.mode or options.toggle) then
    common.info(theme_parser:get_help())
else
    local handler = options.font and fonts or options.wallpaper and wallpapers or themes
    local label = options.font and "Font" or options.wallpaper and "Wallpaper" or "Theme"
    local ok, message = pcall(handler.run, options)
    if not ok then
        common.error(label .. " command failed: " .. tostring(message))
        os.exit(1)
    end
end
