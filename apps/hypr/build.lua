return function(ctx)
    -- These modules are loaded together; never publish an incomplete config.
    local modules = {
        "hyprland", "animations", "bindings", "monitors", "theme", "workspaces",
        "autostart", "rules", "input",
        "bindings/apps", "bindings/windows", "bindings/workspaces", "bindings/desktop", "bindings/media",
        "bindings/display", "bindings/appearance",
    }
    for _, name in ipairs(modules) do
        local content = ctx.read("config/" .. name .. ".lua")
        assert(content ~= "", "Empty Hyprland module: " .. name)
    end

    -- Quote the final checkout path as Lua data, including unusual folder names.
    ctx.render("templates/paths.lua", "generated/paths.lua", {
        install_dir = string.format("%q", ctx.root),
    })
end
