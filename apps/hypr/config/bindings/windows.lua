return function(bind)
    bind("SUPER + W", hl.dsp.window.close(), "Close window")

    -- Force monitor fullscreen rather than maximized or layout-specific fullscreen.
    bind("SUPER + F", hl.dsp.window.fullscreen({ action = "toggle", mode = "fullscreen", layout_aware = false }),
        "Toggle fullscreen")
    bind("SUPER + ALT + F", hl.dsp.window.fullscreen({ action = "toggle", mode = "maximized", layout_aware = false }),
        "Toggle maximized window")
    bind("SUPER + CTRL + F", hl.dsp.window.fullscreen_state({ internal = 0, client = 2, action = "toggle", layout_aware = false }),
        "Toggle fullscreen content inside the window")
    bind("SUPER + T", hl.dsp.window.float({ action = "toggle" }), "Toggle floating window")
    bind("SUPER + J", hl.dsp.layout("togglesplit"), "Toggle tiling split")
    bind("SUPER + P", hl.dsp.window.pseudo(), "Toggle pseudo tiling")

    for _, direction in ipairs({ "left", "right", "up", "down" }) do
        bind("SUPER + " .. direction:upper(), hl.dsp.focus({ direction = direction }), "Focus window " .. direction)
        bind("SUPER + SHIFT + " .. direction:upper(), hl.dsp.window.swap({ direction = direction }),
            "Swap window " .. direction)
        bind("SUPER + ALT + " .. direction:upper(), hl.dsp.window.move({ into_group = direction }),
            "Move window into group " .. direction)
    end

    -- Raise the newly focused window, so cycling also reveals overlapping floats.
    local function cycle(forward)
        return function()
            hl.dispatch(hl.dsp.window.cycle_next({ next = forward }))
            hl.dispatch(hl.dsp.window.bring_to_top())
        end
    end
    bind("ALT + TAB", cycle(true), "Next window")
    bind("ALT + SHIFT + TAB", cycle(false), "Previous window")

    bind("SUPER + mouse:272", hl.dsp.window.drag(), "Drag window", { mouse = true })
    bind("SUPER + mouse:273", hl.dsp.window.resize(), "Resize window with mouse", { mouse = true })

    -- Physical minus/equal keys keep working with Shift; Alt selects 25px steps.
    for _, preset in ipairs({ { modifiers = "", pixels = 100 }, { modifiers = "ALT + ", pixels = 25 } }) do
        local modifiers, pixels = preset.modifiers, preset.pixels
        bind("SUPER + " .. modifiers .. "code:20", hl.dsp.window.resize({ x = -pixels, y = 0, relative = true }),
            "Shrink window width by " .. pixels .. "px", { repeating = true })
        bind("SUPER + " .. modifiers .. "code:21", hl.dsp.window.resize({ x = pixels, y = 0, relative = true }),
            "Grow window width by " .. pixels .. "px", { repeating = true })
        bind("SUPER + SHIFT + " .. modifiers .. "code:20", hl.dsp.window.resize({ x = 0, y = -pixels, relative = true }),
            "Shrink window height by " .. pixels .. "px", { repeating = true })
        bind("SUPER + SHIFT + " .. modifiers .. "code:21", hl.dsp.window.resize({ x = 0, y = pixels, relative = true }),
            "Grow window height by " .. pixels .. "px", { repeating = true })
    end

    bind("SUPER + O", function()
        local window = hl.get_active_window()
        if not window then
            return
        end
        local pinned = window.pinned

        -- Pinning requires a non-fullscreen float. Unpin before returning to tiling.
        hl.dispatch(hl.dsp.window.fullscreen_state({ window = window, internal = 0, client = 0, action = "set", layout_aware = false }))
        if pinned then
            hl.dispatch(hl.dsp.window.pin({ window = window, action = "off" }))
            hl.dispatch(hl.dsp.window.float({ window = window, action = "off" }))
        else
            hl.dispatch(hl.dsp.window.float({ window = window, action = "on" }))
            hl.dispatch(hl.dsp.window.pin({ window = window, action = "on" }))
            hl.dispatch(hl.dsp.window.alter_zorder({ window = window, mode = "top" }))
        end
    end, "Toggle sticky floating window")

    bind("SUPER + G", hl.dsp.group.toggle(), "Toggle window group")
    bind("SUPER + ALT + G", hl.dsp.window.move({ out_of_group = true }), "Remove window from group")
    bind("SUPER + ALT + TAB", hl.dsp.group.next(), "Next window in group")
    bind("SUPER + ALT + SHIFT + TAB", hl.dsp.group.prev(), "Previous window in group")
    bind("SUPER + CTRL + LEFT", hl.dsp.group.prev(), "Previous window in group")
    bind("SUPER + CTRL + RIGHT", hl.dsp.group.next(), "Next window in group")
    for index = 1, 5 do
        bind("SUPER + ALT + " .. index, hl.dsp.group.active({ index = index }), "Focus group window " .. index)
    end
end
