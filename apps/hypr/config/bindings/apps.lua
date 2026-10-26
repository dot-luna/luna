return function(bind)
    bind("SUPER + Return", hl.dsp.exec_cmd("kitty"), "Open Kitty terminal")
    bind("SUPER + SHIFT + Return", hl.dsp.exec_cmd("zen-browser"), "Open Zen Browser")
end
