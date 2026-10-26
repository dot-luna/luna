return function(bind)
    -- Number keys select workspaces 1–9; 0 selects 10. Shift moves and follows.
    for workspace = 1, 10 do
        local key = tostring(workspace % 10)
        bind("SUPER + " .. key, hl.dsp.focus({ workspace = workspace }), "Switch to workspace " .. workspace)
        bind("SUPER + SHIFT + " .. key, hl.dsp.window.move({ workspace = workspace, follow = true }),
            "Move window to workspace " .. workspace .. " and follow")
        bind("SUPER + SHIFT + ALT + " .. key, hl.dsp.window.move({ workspace = workspace, follow = false }),
            "Move window silently to workspace " .. workspace)
    end

    -- Cycle existing workspaces on this monitor without changing their assignments.
    bind("SUPER + Tab", hl.dsp.focus({ workspace = "m+1" }), "Next workspace on this monitor")
    bind("SUPER + SHIFT + Tab", hl.dsp.focus({ workspace = "m-1" }), "Previous workspace on this monitor")
    bind("SUPER + mouse_down", hl.dsp.focus({ workspace = "m+1" }), "Next workspace on this monitor")
    bind("SUPER + mouse_up", hl.dsp.focus({ workspace = "m-1" }), "Previous workspace on this monitor")
    bind("SUPER + CTRL + Tab", hl.dsp.focus({ workspace = "previous_per_monitor" }), "Return to former workspace")
    bind("CTRL + ALT + Tab", hl.dsp.focus({ monitor = "+1" }), "Focus next monitor")
    bind("CTRL + ALT + SHIFT + Tab", hl.dsp.focus({ monitor = "-1" }), "Focus previous monitor")

    -- Move only the window; moving whole numbered workspaces would conflict with
    -- workspaces.lua, which distributes Luna's shared 1–10 set across monitors.
    for _, direction in ipairs({ "left", "right", "up", "down" }) do
        bind("SUPER + CTRL + SHIFT + " .. direction, hl.dsp.window.move({ monitor = direction:sub(1, 1), follow = true }),
            "Move window to monitor " .. direction .. " and follow")
    end

    bind("SUPER + S", hl.dsp.workspace.toggle_special("luna-scratchpad"), "Toggle scratchpad")
    bind("SUPER + ALT + S", hl.dsp.window.move({ workspace = "special:luna-scratchpad", follow = false }),
        "Move window to scratchpad")

    local dropdown = "luna-terminal"
    local launching, show_when_ready, launch_timer = false, false, nil

    hl.on("window.open", function(window)
        if window.class ~= "luna-dropdown" then
            return
        end
        launching = false
        if launch_timer then
            launch_timer:set_enabled(false)
            launch_timer = nil
        end

        if show_when_ready then
            show_when_ready = false
            local monitor = hl.get_active_monitor()
            local special = monitor and monitor.active_special_workspace
            if not special or (special.name ~= dropdown and special.name ~= "special:" .. dropdown) then
                hl.dispatch(hl.dsp.workspace.toggle_special(dropdown))
            end
            hl.dispatch(hl.dsp.focus({ window = window }))
        end
    end)

    bind("SUPER + grave", function()
        for _, window in ipairs(hl.get_windows()) do
            if window.mapped and window.class == "luna-dropdown" then
                -- Recover the terminal if ordinary workspace shortcuts moved it.
                local workspace = window.workspace
                if not workspace or (workspace.name ~= dropdown and workspace.name ~= "special:" .. dropdown) then
                    hl.dispatch(hl.dsp.window.move({ window = window, workspace = "special:" .. dropdown, follow = false }))
                end
                hl.dispatch(hl.dsp.workspace.toggle_special(dropdown))
                return
            end
        end

        -- Rapid presses change the desired visibility while Kitty is starting.
        if launching then
            show_when_ready = not show_when_ready
            return
        end

        launching, show_when_ready = true, true
        -- A failed launch must allow retry. The process lock also prevents duplicate
        -- terminals after a config reload or a startup slower than this timeout.
        launch_timer = hl.timer(function()
            launching, launch_timer = false, nil
        end, { timeout = 5000, type = "oneshot" })
        hl.dispatch(hl.dsp.exec_cmd(
            'flock -n "${XDG_RUNTIME_DIR:?}/luna-dropdown-${HYPRLAND_INSTANCE_SIGNATURE:?}.lock" kitty --class luna-dropdown'))
    end, "Toggle drop-down terminal")
end
