-- Layer-shell menus need an explicit blur rule; window opacity rules do not apply.
-- Ignore the transparent click-dismiss area outside the menu panel.
-- Match only Luna's launcher layer; ignore_alpha = 0 excludes fully transparent pixels.
hl.layer_rule({ match = { namespace = "^luna-launcher$" }, blur = true, ignore_alpha = 0 })

-- Menu installation logs use a compact dialog instead of joining the tiled layout.
hl.window_rule({
    match = { class = "^luna-install$" },

    -- Float the log window outside the tiled layout and center it on its monitor.
    float = true,
    center = true,

    -- Start with a 760 by 460 pixel window for readable progress output.
    size = "760 460",
})

-- Match Zen's video overlay, not ordinary tabs whose title mentions PiP.
hl.window_rule({
    match = { class = "^(zen|zen-browser)$", title = "^Picture-in-Picture$" },

    -- Keep the video floating and visible when switching workspaces on its monitor.
    float = true,
    pin = true,

    -- Preserve the video's proportions when resizing; start at a 16:9 window size.
    keep_aspect_ratio = true,
    size = { 480, 270 },

    -- Place its bottom and right edges 24 pixels inside the monitor edges.
    move = { "(monitor_w-window_w-24)", "(monitor_h-window_h-24)" },
})

-- The GTK portal's file pickers and permission dialogs stay above tiled apps.
hl.window_rule({
    match = { class = "^xdg-desktop-portal-gtk$" },

    -- Float and center portal dialogs so opening a picker does not rearrange tiles.
    float = true,
    center = true,
})

-- Kitty's dedicated class keeps the drop-down terminal separate from regular ones.
-- Silent placement lets the shortcut decide whether a slow launch should be shown.
hl.window_rule({
    match = { class = "^luna-dropdown$" },

    -- Place the terminal in its own special workspace without switching to it.
    -- The Super + backtick shortcut decides when to reveal or hide that workspace.
    workspace = "special:luna-terminal silent",
    float = true,

    -- Use 90% of the monitor width and half its height; keep it horizontally
    -- centered with its top edge 24 pixels below the monitor's top edge.
    size = { "(monitor_w*0.9)", "(monitor_h*0.5)" },
    move = { "((monitor_w-window_w)/2)", "24" },
})
