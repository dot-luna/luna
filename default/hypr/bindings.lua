-- Global shortcuts belong to the compositor, including in apps that inhibit binds.
-- Keep normal lock-screen protection; dont_inhibit only bypasses app requests.
-- Descriptions expose Lua actions to the launcher's live keybinding guide.
local function bind(keys, action, description)
    return hl.bind(keys, action, { non_consuming = false, dont_inhibit = true, description = description })
end

-- Register Luna's basic shortcuts whenever the Hyprland configuration loads.
bind("SUPER + Return", hl.dsp.exec_cmd("kitty"), "Open Kitty terminal")
bind("SUPER + SHIFT + Return", hl.dsp.exec_cmd("zen-browser"), "Open Zen Browser")
bind("SUPER + W", hl.dsp.window.close(), "Close window")

-- Force monitor fullscreen rather than maximized or layout-specific fullscreen.
bind("SUPER + F", hl.dsp.window.fullscreen({ action = "toggle", mode = "fullscreen", layout_aware = false }),
    "Toggle fullscreen")

-- Number keys select workspaces 1–9; 0 selects workspace 10. Shift moves and follows the focused window.
for workspace = 1, 10 do
    local key = tostring(workspace % 10)
    bind("SUPER + " .. key, hl.dsp.focus({ workspace = workspace }), "Switch to workspace " .. workspace)
    bind("SUPER + SHIFT + " .. key, hl.dsp.window.move({ workspace = workspace, follow = true }),
        "Move window to workspace " .. workspace .. " and follow")
end

-- Shell shortcuts use the same consumption policy as window/workspace shortcuts.
return bind
