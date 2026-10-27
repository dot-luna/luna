-- Public wallpaper API. Own config and rendering here; callers own their UI and output.
-- Load through lib/luna.lua to share the same implementation with the Luna command.
return function(common, root)
    local directory = root .. "/src/wallpaper/src"
    local config = dofile(directory .. "/config.lua")(common, root)
    local runtime = dofile(directory .. "/runtime.lua")(common, root, directory .. "/shell/shell.qml")

    -- Config methods always read/edit the user file, independent of renderer state.
    -- Call reload explicitly to apply edits; source is an ordinary config option.
    return {
        getConfig = config.get,
        updateConfig = config.update,
        getConfigFile = config.file,
        reload = runtime.reload,
        status = runtime.status,
        start = runtime.start,
        stop = runtime.stop,
        restart = runtime.restart,
    }
end
