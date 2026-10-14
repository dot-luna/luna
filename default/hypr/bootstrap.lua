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
        hl.dispatch(hl.dsp.exec_cmd(launcher .. " auth start"))
        hl.dispatch(hl.dsp.exec_cmd(launcher .. " screensaver start"))
        hl.dispatch(hl.dsp.exec_cmd(launcher .. " clipboard start"))
        hl.dispatch(hl.dsp.exec_cmd(launcher .. " notifications start"))
    end)
    bind("SUPER + L", hl.dsp.exec_cmd(launcher .. " lock"), "Lock screen")
    bind("SUPER + CTRL + B", hl.dsp.exec_cmd(launcher .. " bar focus"), "Focus Luna bar")
    bind("SUPER + CTRL + Space", hl.dsp.exec_cmd(launcher .. " bar controls"), "Open control center")
    bind("SUPER + Space", hl.dsp.exec_cmd(launcher .. " launcher toggle"), "Toggle Luna menu")
    bind("SUPER + N", hl.dsp.exec_cmd(launcher .. " notifications open"), "Toggle notification history")
    bind("SUPER + SHIFT + N", hl.dsp.exec_cmd(launcher .. " notifications dnd"), "Toggle Do Not Disturb")

    -- Menu and keyboard captures share the same saving and clipboard behavior.
    bind("Print", hl.dsp.exec_cmd(launcher .. " screenshot region"), "Screenshot selected region")
    bind("SHIFT + Print", hl.dsp.exec_cmd(launcher .. " screenshot screen"), "Screenshot active screen")
    bind("ALT + Print", hl.dsp.exec_cmd(launcher .. " screenshot window"), "Screenshot active window")
    bind("CTRL + Print", hl.dsp.exec_cmd(launcher .. " screenshot all"), "Screenshot all screens")
    bind("SUPER + Print", hl.dsp.exec_cmd(launcher .. " record toggle"), "Start region recording or stop recording")
    bind("SUPER + SHIFT + Print", hl.dsp.exec_cmd(launcher .. " record stop"), "Stop recording")

    -- Continuous controls repeat; mute and transport controls act once per keypress.
    for _, shortcut in ipairs({
        { "XF86AudioRaiseVolume", "volume-up", "Raise volume", true },
        { "XF86AudioLowerVolume", "volume-down", "Lower volume", true },
        { "XF86AudioMute", "volume-mute", "Toggle sound mute" },
        { "XF86AudioMicMute", "mic-mute", "Toggle microphone mute" },
        { "XF86MonBrightnessUp", "brightness-up", "Raise brightness", true },
        { "XF86MonBrightnessDown", "brightness-down", "Lower brightness", true },
        { "XF86AudioPlay", "play-pause", "Play or pause media" },
        { "XF86AudioNext", "next", "Next track" },
        { "XF86AudioPrev", "previous", "Previous track" },
    }) do
        bind(shortcut[1], hl.dsp.exec_cmd(launcher .. " control " .. shortcut[2]), shortcut[3], shortcut[4])
    end
end
