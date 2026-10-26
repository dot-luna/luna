-- Loaded by hyprland.lua: spring motion for geometry, short fades for visibility.
-- Bezier speed is in deciseconds (1 = 100ms). Springs use their physics instead;
-- Hyprland still requires a positive speed, so spring entries use speed = 1.

-- A lightly underdamped spring gives opening windows a gentle, barely visible settle.
-- With mass fixed at 1, higher stiffness moves faster and more dampening reduces bounce.
hl.curve("lunaSoft", { type = "spring", mass = 1, stiffness = 500, dampening = 38 })

-- Near-critical damping keeps tiling, workspace switches and zoom firm and responsive
-- when keyboard shortcuts are repeated, without a noticeable rebound.
hl.curve("lunaMotion", { type = "spring", mass = 1, stiffness = 800, dampening = 56 })

-- Opacity and color changes ease out quickly without spring overshoot.
hl.curve("lunaQuick", {
    type = "bezier",
    points = { { 0.2, 0.8 }, { 0.2, 1 } },
})

-- Allow manual resize steps, including keyboard-driven tiled resizing, to animate.
hl.config({ misc = { animate_manual_resizes = true } })

-- Unspecified branches get a short 180ms ease-out instead of a long transition.
hl.animation({ leaf = "global", enabled = true, speed = 1.8, bezier = "lunaQuick" })

-- Moving, tiling and resizing windows share the firmer spring by default.
hl.animation({ leaf = "windows", enabled = true, speed = 1, spring = "lunaMotion" })

-- Open from 94% of the final size: enough motion to feel the spring without a large zoom.
hl.animation({ leaf = "windowsIn", enabled = true, speed = 1, spring = "lunaSoft", style = "popin 94%" })

-- Closing finishes quickly, shrinking only 4% while the independent fade removes it.
hl.animation({ leaf = "windowsOut", enabled = true, speed = 1.2, bezier = "lunaQuick", style = "popin 96%" })

-- Most fades take 140ms; opening is slightly softer and closing finishes in 100ms.
hl.animation({ leaf = "fade", enabled = true, speed = 1.4, bezier = "lunaQuick" })
hl.animation({ leaf = "fadeIn", enabled = true, speed = 1.6, bezier = "lunaQuick" })
hl.animation({ leaf = "fadeOut", enabled = true, speed = 1, bezier = "lunaQuick" })

-- Focus feedback follows keyboard navigation promptly through borders and opacity.
-- Opacity only changes when the selected theme gives focused/unfocused windows different values.
hl.animation({ leaf = "border", enabled = true, speed = 1.2, bezier = "lunaQuick" })
hl.animation({ leaf = "fadeSwitch", enabled = true, speed = 1, bezier = "lunaQuick" })

-- Dimmed windows ease into their new shade without an abrupt brightness change.
hl.animation({ leaf = "fadeDim", enabled = true, speed = 1.6, bezier = "lunaQuick" })

-- Luna menus use fullscreen transparent layers around smaller cards. Fade those
-- surfaces in place so their click-dismiss areas do not slide or scale across the screen.
hl.animation({ leaf = "layers", enabled = true, speed = 1.6, bezier = "lunaQuick", style = "fade" })
hl.animation({ leaf = "fadeLayers", enabled = true, speed = 1.6, bezier = "lunaQuick" })

-- Dismiss panels and menus in 100ms so returning to the focused app feels immediate.
hl.animation({ leaf = "layersOut", enabled = true, speed = 1, bezier = "lunaQuick", style = "fade" })
hl.animation({ leaf = "fadeLayersOut", enabled = true, speed = 1, bezier = "lunaQuick" })

-- Native Wayland popup fades stay brief for frequent menu and tooltip interactions.
hl.animation({ leaf = "fadePopups", enabled = true, speed = 1, bezier = "lunaQuick" })

-- Follow workspace order with a horizontal slide/fade over 15% of the screen width.
-- The near-critical spring keeps both motion and workspace opacity from bouncing.
hl.animation({ leaf = "workspaces", enabled = true, speed = 1, spring = "lunaMotion", style = "slidefade 15%" })

-- Scratchpads and the drop-down terminal move vertically to distinguish overlays
-- from normal workspaces; travel is limited to 15% of the screen height.
hl.animation({ leaf = "specialWorkspace", enabled = true, speed = 1, spring = "lunaMotion", style = "slidefadevert 15%" })

-- Hide special workspaces in 140ms while keeping the same vertical direction style.
hl.animation({ leaf = "specialWorkspaceOut", enabled = true, speed = 1.4, bezier = "lunaQuick", style = "slidefadevert 15%" })

-- Zoom shortcuts use the same firm spring, including the return to normal scale.
hl.animation({ leaf = "zoomFactor", enabled = true, speed = 1, spring = "lunaMotion" })
