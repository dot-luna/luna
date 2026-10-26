-- Global shortcuts belong to the compositor, including in apps that inhibit binds.
-- Keep normal lock-screen protection; dont_inhibit only bypasses app requests.
-- Descriptions expose Lua actions to the launcher's live keybinding guide.
local function bind(keys, action, description, options)
    -- Existing media bindings pass a repeat flag; mouse bindings need an option table.
    if type(options) ~= "table" then
        options = { repeating = options == true }
    end
    options.non_consuming = false
    options.dont_inhibit = true
    options.description = description
    return hl.bind(keys, action, options)
end

-- Every group uses the same helper; keep the load order explicit.
return function(config_dir, launcher)
    for _, name in ipairs({ "apps", "windows", "workspaces", "display", "appearance", "desktop", "media" }) do
        dofile(config_dir .. "/bindings/" .. name .. ".lua")(bind, launcher)
    end
end
