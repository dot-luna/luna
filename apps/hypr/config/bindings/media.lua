return function(bind, launcher)
    -- Continuous controls repeat; mute and transport controls act once per keypress.
    for _, shortcut in ipairs({
        { "XF86AudioRaiseVolume", "volume-up", "Raise volume", true },
        { "XF86AudioLowerVolume", "volume-down", "Lower volume", true },
        { "XF86AudioMute", "volume-mute", "Toggle sound mute" },
        { "XF86AudioMicMute", "mic-mute", "Toggle microphone mute" },
        { "XF86MonBrightnessUp", "brightness-up", "Raise brightness", true },
        { "XF86MonBrightnessDown", "brightness-down", "Lower brightness", true },
        { "XF86AudioPlay", "play-pause", "Play or pause media" },
        { "XF86AudioNext", "next", "Next track" },
        { "XF86AudioPrev", "previous", "Previous track" },
    }) do
        bind(shortcut[1], hl.dsp.exec_cmd(launcher .. " control " .. shortcut[2]), shortcut[3], shortcut[4])
    end
end
