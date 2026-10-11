#!/usr/bin/lua -E
-- Luna CLI entry point. Run with Lua after scripts/setup-lua.sh prepares argparse.

-- Locate shared helpers relative to this file, independently of the caller's cwd.
local source_dir = arg[0]:match("^(.*)/") or "."
local common = dofile(source_dir .. "/../../lib/common.lua")
local argparse = require("argparse")

-- Command implementations live in their own directories; argparse owns usage errors.
local parser = argparse("luna", "Luna personal Arch desktop tools.")
parser:require_command(false)
local fonts = dofile(source_dir .. "/font/init.lua")(common, source_dir .. "/font")
local font_parser = fonts.register(parser)
local options = parser:parse()

-- Bare entry points show help rather than performing any system operation.
if not options.font then
    common.info(parser:get_help())
elseif not (options.search or options.install or options.remove or options.list or options.refresh) then
    common.info(font_parser:get_help())
else
    local ok, message = pcall(fonts.run, options)
    if not ok then
        common.error("Font command failed: " .. tostring(message))
        os.exit(1)
    end
end
