-- Register Luna's basic shortcuts whenever the Hyprland configuration loads.
hl.bind("SUPER + Return", hl.dsp.exec_cmd("kitty"))
hl.bind("SUPER + SHIFT + Return", hl.dsp.exec_cmd("zen-browser"))
hl.bind("SUPER + W", hl.dsp.window.close())

-- Number keys select workspaces 1–9; 0 selects workspace 10.
for workspace = 1, 10 do
    local key = tostring(workspace % 10)
    hl.bind("SUPER + " .. key, hl.dsp.focus({ workspace = workspace }))
end
