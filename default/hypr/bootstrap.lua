-- Load reusable defaults relative to the checkout supplied by the entry point.
return function(root)
    local validate = dofile(root .. "/lib/theme/validate.lua")()
    local theme = dofile(root .. "/default/hypr/theme.lua")(validate)
    theme.apply()

    dofile(root .. "/default/hypr/bindings.lua")
    dofile(root .. "/default/hypr/animations.lua")

    -- Use the checkout launcher so shell shortcuts also work before bin is on PATH.
    local launcher = "'" .. (root .. "/bin/luna"):gsub("'", "'\\''") .. "'"
    hl.bind("SUPER + CTRL + B", hl.dsp.exec_cmd(launcher .. " bar focus"))
    hl.bind("SUPER + CTRL + Space", hl.dsp.exec_cmd(launcher .. " bar controls"))
    hl.bind("SUPER + Space", hl.dsp.exec_cmd(launcher .. " launcher toggle"))
end
