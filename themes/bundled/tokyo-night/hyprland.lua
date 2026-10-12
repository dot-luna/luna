-- Appearance values consumed by Luna's adapter when Hyprland loads its Lua config.
return {
    -- Gaps and border thickness are in Hyprland layout pixels.
    general = {
        gaps_in = 5,
        gaps_out = 5,
        border_size = 1,
    },

    decoration = {
        rounding = 0,

        -- Opacity uses 0..1; translucent windows reveal blur, fullscreen stays opaque.
        active_opacity = 0.90,
        inactive_opacity = 0.85,
        fullscreen_opacity = 1,

        -- Strong blur behind transparent content; more passes increase GPU work.
        blur = {
            enabled = true,
            size = 10,
            passes = 3,
        },

        shadow = {
            enabled = true,
            range = 12,
            render_power = 3,
        },
    },
}
