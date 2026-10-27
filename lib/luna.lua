-- Shared Lua entry point for Luna callers: load this file, then pass the checkout root.
-- Creating the API reads no config, installs nothing, and starts no desktop processes.
return function(root, common)
    common = common or dofile(root .. "/lib/common.lua")
    local download = dofile(root .. "/lib/wallpapers/download.lua")(common)
    return {
        wallpaper = dofile(root .. "/src/wallpaper/src/api.lua")(common, root),
        wallpapers = dofile(root .. "/lib/wallpapers/files.lua")(common, download),
    }
end
