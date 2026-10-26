return function(bind, launcher)
    -- Continuous controls repeat; mute and transport controls act once per keypress.
    -- Each row holds the hardware key, Luna control action, guide text and repeat flag.
    for _, shortcut in ipairs({
        -- Volume Up: raise output volume by 5 percentage points and unmute; hold to repeat.
        { "XF86AudioRaiseVolume", "volume-up", "Raise volume", true },

        -- Volume Down: lower output volume by 5 percentage points and unmute; hold to repeat.
        { "XF86AudioLowerVolume", "volume-down", "Lower volume", true },

        -- Speaker Mute: mute or unmute the current audio output without changing its volume.
        { "XF86AudioMute", "volume-mute", "Toggle sound mute" },

        -- Microphone Mute: mute or unmute the current microphone, independently of speakers.
        { "XF86AudioMicMute", "mic-mute", "Toggle microphone mute" },

        -- Brightness Up: raise the available display backlight by 5 percentage points; hold to repeat.
        { "XF86MonBrightnessUp", "brightness-up", "Raise brightness", true },

        -- Brightness Down: lower the available display backlight by 5 percentage points; hold to repeat.
        { "XF86MonBrightnessDown", "brightness-down", "Lower brightness", true },

        -- Media Play/Pause: toggle playback in the media player currently selected by Luna.
        { "XF86AudioPlay", "play-pause", "Play or pause media" },

        -- Media Next: request the next track from that player, even when its window is unfocused.
        { "XF86AudioNext", "next", "Next track" },

        -- Media Previous: request the previous track from the same player.
        { "XF86AudioPrev", "previous", "Previous track" },
    }) do
        -- Register this row's hardware key through Luna's shared controls so it
        -- uses the same devices, player selection and feedback as the control center.
        bind(shortcut[1], hl.dsp.exec_cmd(launcher .. " control " .. shortcut[2]), shortcut[3], shortcut[4])
    end
end
