return function(ctx)
    -- These modules are loaded together; never publish an incomplete config.
    for _, name in ipairs({ "hyprland", "animations", "bindings", "monitors", "theme", "workspaces" }) do
        assert(ctx.read("config/" .. name .. ".lua") ~= "", "Empty Hyprland module: " .. name)
    end

    -- Quote the final checkout path as Lua data, including unusual folder names.
    ctx.render("templates/paths.lua", "generated/paths.lua", {
        install_dir = string.format("%q", ctx.root),
    })
end
