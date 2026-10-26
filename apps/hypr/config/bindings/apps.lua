return function(bind)
    -- Super + Enter: open the terminal selected in your xdg-terminal-exec preferences.
    bind("SUPER + Return", hl.dsp.exec_cmd("xdg-terminal-exec"), "Open default terminal")

    -- Super + Shift + Enter: launch the browser currently assigned to HTTPS links.
    -- Resolve its desktop entry on every press so changes to your default apply immediately.
    bind("SUPER + SHIFT + Return", hl.dsp.exec_cmd('gtk-launch -- "$(xdg-mime query default x-scheme-handler/https)"'),
        "Open default browser")
end
