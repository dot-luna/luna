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

-- Match Zen's video overlay, not ordinary tabs whose title mentions PiP.
hl.window_rule({
    match = { class = "^(zen|zen-browser)$", title = "^Picture-in-Picture$" },
    float = true,
    pin = true,
    keep_aspect_ratio = true,
    size = { 480, 270 },
    move = { "(monitor_w-window_w-24)", "(monitor_h-window_h-24)" },
})

-- The GTK portal's file pickers and permission dialogs stay above tiled apps.
hl.window_rule({
    match = { class = "^xdg-desktop-portal-gtk$" },
    float = true,
    center = true,
})

-- Kitty's dedicated class keeps the drop-down terminal separate from regular ones.
-- Silent placement lets the shortcut decide whether a slow launch should be shown.
hl.window_rule({
    match = { class = "^luna-dropdown$" },
    workspace = "special:luna-terminal silent",
    float = true,
    size = { "(monitor_w*0.9)", "(monitor_h*0.5)" },
    move = { "((monitor_w-window_w)/2)", "24" },
})
