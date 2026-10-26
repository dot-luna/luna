-- Appearance toggles preserve values from the first press and reset on config reload.
return function(bind)
    local saved = {}
    local layouts = {}

    local function toggle(name, values)
        if saved[name] then
            hl.config(saved[name])
            saved[name] = nil
            return
        end
        local previous = {}
        for key in pairs(values) do
            previous[key] = hl.get_config(key)
        end
        saved[name] = previous
        hl.config(values)
    end

    bind("SUPER + CTRL + L", function()
        local workspace = hl.get_active_workspace()
        -- Range selectors keep overrides independent of monitor assignment rules.
        -- Named workspaces use negative IDs; leave them and scratchpads untouched.
        if not workspace or workspace.special or workspace.id <= 0 or hl.get_active_special_workspace() then
            return
        end
        local rule = layouts[workspace.id]
        if rule then
            rule:set_enabled(not rule:is_enabled())
        elseif workspace.tiled_layout == "dwindle" or workspace.tiled_layout == "scrolling" then
            layouts[workspace.id] = hl.workspace_rule({
                workspace = string.format("r[%d-%d] s[false]", workspace.id, workspace.id),
                layout = workspace.tiled_layout == "dwindle" and "scrolling" or "dwindle",
            })
        end
    end, "Toggle workspace between dwindle and scrolling")

    bind("SUPER + SHIFT + BackSpace", function()
        toggle("gaps", { ["general.gaps_in"] = 0, ["general.gaps_out"] = 0 })
    end, "Toggle window gaps")

    bind("SUPER + BackSpace", function()
        local active = hl.get_config("decoration.active_opacity")
        local inactive = hl.get_config("decoration.inactive_opacity")
        local fullscreen = hl.get_config("decoration.fullscreen_opacity")
        local opaque = active == 1 and inactive == 1 and fullscreen == 1
        toggle("opacity", {
            ["decoration.active_opacity"] = opaque and 0.9 or 1,
            ["decoration.inactive_opacity"] = opaque and 0.9 or 1,
            ["decoration.fullscreen_opacity"] = 1,
        })
    end, "Toggle window transparency")

    bind("SUPER + CTRL + BackSpace", function()
        local ratio = hl.get_config("layout.single_window_aspect_ratio")
        toggle("aspect", { ["layout.single_window_aspect_ratio"] = ratio[1] == 1 and ratio[2] == 1
            and { 0, 0 } or { 1, 1 } })
    end, "Toggle square aspect for a lone tiled window")
end
