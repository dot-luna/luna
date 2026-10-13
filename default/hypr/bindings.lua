-- Global shortcuts belong to the compositor, including in apps that inhibit binds.
-- Keep normal lock-screen protection; dont_inhibit only bypasses app requests.
local function bind(keys, action)
    return hl.bind(keys, action, { non_consuming = false, dont_inhibit = true })
end

-- Register Luna's basic shortcuts whenever the Hyprland configuration loads.
bind("SUPER + Return", hl.dsp.exec_cmd("kitty"))
bind("SUPER + SHIFT + Return", hl.dsp.exec_cmd("zen-browser"))
bind("SUPER + W", hl.dsp.window.close())
-- Force monitor fullscreen rather than maximized or layout-specific fullscreen.
bind("SUPER + F", hl.dsp.window.fullscreen({ action = "toggle", mode = "fullscreen", layout_aware = false }))

-- Number keys select workspaces 1–9; 0 selects workspace 10. Shift moves and follows the focused window.
for workspace = 1, 10 do
    local key = tostring(workspace % 10)
    bind("SUPER + " .. key, hl.dsp.focus({ workspace = workspace }))
    bind("SUPER + SHIFT + " .. key, hl.dsp.window.move({ workspace = workspace, follow = true }))
end

-- Shell shortcuts use the same consumption policy as window/workspace shortcuts.
return bind
