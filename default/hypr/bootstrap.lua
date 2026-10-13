-- Load reusable defaults relative to the checkout supplied by the entry point.
return function(root)
    dofile(root .. "/default/hypr/monitors.lua")
    dofile(root .. "/default/hypr/workspaces.lua")

    local resolved = dofile(root .. "/lib/theme/resolved.lua")(root)
    local theme = dofile(root .. "/default/hypr/theme.lua")(resolved)
    theme.apply()

    -- Layer-shell menus need an explicit blur rule; window opacity rules do not apply.
    -- Ignore the transparent click-dismiss area outside the menu panel.
    hl.layer_rule({ match = { namespace = "^luna-launcher$" }, blur = true, ignore_alpha = 0 })

    -- Menu installation logs use a compact dialog instead of joining the tiled layout.
    hl.window_rule({
        match = { class = "^luna-install$" },
        float = true,
        center = true,
        size = "760 460",
    })

    local bind = dofile(root .. "/default/hypr/bindings.lua")
    dofile(root .. "/default/hypr/animations.lua")

    -- Use the checkout launcher so shell shortcuts also work before bin is on PATH.
    local launcher = "'" .. (root .. "/bin/luna"):gsub("'", "'\\''") .. "'"
    hl.on("hyprland.start", function()
        hl.dispatch(hl.dsp.exec_cmd(launcher .. " screensaver start"))
    end)
    bind("SUPER + L", hl.dsp.exec_cmd(launcher .. " lock"))
    bind("SUPER + CTRL + B", hl.dsp.exec_cmd(launcher .. " bar focus"))
    bind("SUPER + CTRL + Space", hl.dsp.exec_cmd(launcher .. " bar controls"))
    bind("SUPER + Space", hl.dsp.exec_cmd(launcher .. " launcher toggle"))
end
