-- Hyprland speeds are durations in deciseconds: 2 means 200 milliseconds.
hl.curve("lunaQuick", {
    type = "bezier",
    points = { { 0.2, 0.8 }, { 0.2, 1 } },
})

hl.animation({ leaf = "global", enabled = true, speed = 2.5, bezier = "lunaQuick" })
hl.animation({ leaf = "windows", enabled = true, speed = 2, bezier = "lunaQuick" })
hl.animation({ leaf = "fade", enabled = true, speed = 1.5, bezier = "lunaQuick" })
hl.animation({ leaf = "layers", enabled = true, speed = 1.8, bezier = "lunaQuick" })

-- Horizontal slide direction follows the source and destination workspace order.
hl.animation({ leaf = "workspaces", enabled = true, speed = 2.2, bezier = "lunaQuick", style = "slide" })
