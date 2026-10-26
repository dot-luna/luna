return function(bind, launcher)
    bind("SUPER + L", hl.dsp.exec_cmd(launcher .. " lock"), "Lock screen")
    bind("SUPER + CTRL + B", hl.dsp.exec_cmd(launcher .. " bar focus"), "Focus Luna bar")
    bind("SUPER + CTRL + Space", hl.dsp.exec_cmd(launcher .. " bar controls"), "Open control center")
    bind("SUPER + Space", hl.dsp.exec_cmd(launcher .. " launcher toggle"), "Toggle Luna menu")
    bind("SUPER + N", hl.dsp.exec_cmd(launcher .. " notifications open"), "Toggle notification history")
    bind("SUPER + SHIFT + N", hl.dsp.exec_cmd(launcher .. " notifications dnd"), "Toggle Do Not Disturb")

    -- Menu and keyboard captures share the same saving and clipboard behavior.
    bind("Print", hl.dsp.exec_cmd(launcher .. " screenshot region"), "Screenshot selected region")
    bind("SHIFT + Print", hl.dsp.exec_cmd(launcher .. " screenshot screen"), "Screenshot active screen")
    bind("ALT + Print", hl.dsp.exec_cmd(launcher .. " screenshot window"), "Screenshot active window")
    bind("CTRL + Print", hl.dsp.exec_cmd(launcher .. " screenshot all"), "Screenshot all screens")
    bind("SUPER + Print", hl.dsp.exec_cmd(launcher .. " record toggle"), "Start region recording or stop recording")
    bind("SUPER + SHIFT + Print", hl.dsp.exec_cmd(launcher .. " record stop"), "Stop recording")
end
