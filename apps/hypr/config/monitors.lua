-- Enable newly connected displays at their preferred mode and extend the desktop.
-- Automatic placement avoids overlapping outputs; personal rules can follow Luna's defaults.
-- An empty output name is the fallback for displays without a more specific rule.
-- "preferred" uses the display's advertised mode; scale = 1 means 100% UI scaling.
-- Override a named output in your personal hyprland.lua for a different mode or scale.
hl.monitor({ output = "", mode = "preferred", position = "auto", scale = 1 })
