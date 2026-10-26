-- Register services for session startup only; reloads do not restart them.
return function(launcher)
    hl.on("hyprland.start", function()
        -- Finish initializing the daemon unlocked by PAM. Publish the graphical
        -- environment first so D-Bus can display later keyring unlock prompts.
        hl.dispatch(hl.dsp.exec_cmd([[
            if command -v gnome-keyring-daemon >/dev/null 2>&1; then
                if command -v dbus-update-activation-environment >/dev/null 2>&1; then
                    dbus-update-activation-environment --systemd DISPLAY WAYLAND_DISPLAY XDG_CURRENT_DESKTOP
                fi
                gnome-keyring-daemon --start --components=secrets,pkcs11
            fi
        ]]))
        hl.dispatch(hl.dsp.exec_cmd(launcher .. " auth start"))
        hl.dispatch(hl.dsp.exec_cmd(launcher .. " screensaver start"))
        hl.dispatch(hl.dsp.exec_cmd(launcher .. " clipboard start"))
        hl.dispatch(hl.dsp.exec_cmd(launcher .. " notifications start"))
    end)
end
