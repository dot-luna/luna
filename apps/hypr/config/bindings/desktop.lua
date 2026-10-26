return function(bind, launcher)
    -- Super + L: lock the session with Luna's lock screen; running apps stay open.
    bind("SUPER + L", hl.dsp.exec_cmd(launcher .. " lock"), "Lock screen")

    -- Super + Ctrl + B: give the bar keyboard focus. Navigate with Tab or arrows,
    -- activate a control with Enter, and press Escape to return to your apps.
    bind("SUPER + CTRL + B", hl.dsp.exec_cmd(launcher .. " bar focus"), "Focus Luna bar")

    -- Super + Ctrl + Space: show or hide the control center on the focused monitor.
    bind("SUPER + CTRL + Space", hl.dsp.exec_cmd(launcher .. " bar controls"), "Open control center")

    -- Super + Space: show or hide Luna's menu for launching apps and desktop actions.
    bind("SUPER + Space", hl.dsp.exec_cmd(launcher .. " launcher toggle"), "Toggle Luna menu")

    -- Super + N: show or hide notification history on the focused monitor.
    bind("SUPER + N", hl.dsp.exec_cmd(launcher .. " notifications open"), "Toggle notification history")

    -- Super + Shift + N: toggle Do Not Disturb, silencing notification popups and
    -- sounds while still collecting notifications eligible for history.
    bind("SUPER + SHIFT + N", hl.dsp.exec_cmd(launcher .. " notifications dnd"), "Toggle Do Not Disturb")

    -- Print Screen: select a rectangular region to capture; Escape cancels.
    -- All screenshot shortcuts below save a PNG in ~/Pictures/Screenshots and
    -- copy the image to the clipboard, using the same capture flow as the menu.
    bind("Print", hl.dsp.exec_cmd(launcher .. " screenshot region"), "Screenshot selected region")

    -- Shift + Print Screen: capture the entire focused monitor without selecting a region.
    bind("SHIFT + Print", hl.dsp.exec_cmd(launcher .. " screenshot screen"), "Screenshot active screen")

    -- Alt + Print Screen: capture the focused window's visible on-screen rectangle.
    bind("ALT + Print", hl.dsp.exec_cmd(launcher .. " screenshot window"), "Screenshot active window")

    -- Ctrl + Print Screen: capture all monitors together in one desktop image.
    bind("CTRL + Print", hl.dsp.exec_cmd(launcher .. " screenshot all"), "Screenshot all screens")

    -- Super + Print Screen: select a region and start recording, or stop the
    -- current recording and finish saving its video in ~/Videos/Recordings.
    bind("SUPER + Print", hl.dsp.exec_cmd(launcher .. " record toggle"), "Start region recording or stop recording")

    -- Super + Shift + Print Screen: stop and save an active recording without
    -- starting another one when the recorder is idle.
    bind("SUPER + SHIFT + Print", hl.dsp.exec_cmd(launcher .. " record stop"), "Stop recording")
end
