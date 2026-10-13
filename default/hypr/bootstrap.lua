-- Load reusable defaults relative to the checkout supplied by the entry point.
return function(root)
    dofile(root .. "/default/hypr/monitors.lua")
    dofile(root .. "/default/hypr/workspaces.lua")

    local resolved = dofile(root .. "/lib/theme/resolved.lua")(root)
    local theme = dofile(root .. "/default/hypr/theme.lua")(resolved)
    theme.apply()

    local bind = dofile(root .. "/default/hypr/bindings.lua")
    dofile(root .. "/default/hypr/animations.lua")

    -- Use the checkout launcher so shell shortcuts also work before bin is on PATH.
    local launcher = "'" .. (root .. "/bin/luna"):gsub("'", "'\\''") .. "'"
    bind("SUPER + CTRL + B", hl.dsp.exec_cmd(launcher .. " bar focus"))
    bind("SUPER + CTRL + Space", hl.dsp.exec_cmd(launcher .. " bar controls"))
    bind("SUPER + Space", hl.dsp.exec_cmd(launcher .. " launcher toggle"))
end
