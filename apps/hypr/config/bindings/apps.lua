return function(bind, launcher)
    -- Super + Enter: open your default terminal in the focused terminal's folder,
    -- or at home for other apps. Capture the process before another window gains focus.
    bind("SUPER + Return", function()
        local window = hl.get_active_window()
        local pid = math.max(0, window and window.pid or 0)
        hl.dispatch(hl.dsp.exec_cmd(launcher .. " terminal --pid=" .. tostring(pid)))
    end, "Open default terminal in current directory")

    -- Super + Shift + Enter: launch the browser currently assigned to HTTPS links.
    -- Resolve its desktop entry on every press so changes to your default apply immediately.
    bind("SUPER + SHIFT + Return", hl.dsp.exec_cmd('gtk-launch -- "$(xdg-mime query default x-scheme-handler/https)"'),
        "Open default browser")
end
