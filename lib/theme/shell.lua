-- Pass the shared resolved output to Quickshell without per-component defaults.
return function(root)
    local resolved = dofile(root .. "/lib/theme/resolved.lua")(root)
    local M = {}

    function M.snapshot()
        return resolved.encode(resolved.active())
    end

    return M
end
