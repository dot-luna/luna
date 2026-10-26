-- Keyboard layouts, remaps and pointer sensitivity remain personal preferences.
hl.config({
    input = {
        repeat_rate = 40,
        repeat_delay = 250,
        touchpad = {
            tap_to_click = true,
            disable_while_typing = true,
            clickfinger_behavior = true,
        },
    },
    -- Keep manually selected dwindle splits when adding or removing windows.
    dwindle = { preserve_split = true },
    -- Swipes use existing workspaces on this monitor instead of creating new IDs.
    gestures = { workspace_swipe_create_new = false, workspace_swipe_use_r = false },
})

hl.gesture({ fingers = 3, direction = "horizontal", action = "workspace" })
