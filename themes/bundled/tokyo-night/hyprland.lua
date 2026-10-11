-- Theme appearance values for a future Hyprland adapter; loading does not apply them.
return {
    -- Gaps and border thickness are in Hyprland layout pixels.
    general = {
        gaps_in = 8,
        gaps_out = 12,
        border_size = 2,
    },

    decoration = {
        rounding = 8,

        -- Opacity and dimming use 0..1; keep focused and fullscreen content opaque.
        active_opacity = 1,
        inactive_opacity = 0.95,
        fullscreen_opacity = 1,
        dim_inactive = true,
        dim_strength = 0.1,

        -- A modest blur behind transparent content; more passes increase GPU work.
        blur = {
            enabled = true,
            size = 4,
            passes = 2,
        },

        shadow = {
            enabled = true,
            range = 12,
            render_power = 3,
        },
    },
}
