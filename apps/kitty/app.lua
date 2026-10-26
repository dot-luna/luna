return {
    config = "config",
    builder = "build.lua",
    connections = {
        {
            type = "kitty",
            source = "kitty.conf",
            target = "kitty/kitty.conf",
            directory_env = "KITTY_CONFIG_DIRECTORY",
        },
    },
}
