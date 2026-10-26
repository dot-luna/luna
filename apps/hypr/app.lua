return {
    config = "config",
    builder = "build.lua",
    connections = {
        {
            type = "lua",
            source = "hyprland.lua",
            target = "hypr/hyprland.lua",
            file_env = "HYPRLAND_CONFIG",
        },
    },
}
