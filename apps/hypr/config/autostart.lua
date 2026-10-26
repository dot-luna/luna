-- Register services for session startup only; reloads do not restart them.
-- The entry point supplies a quoted Luna command so every helper uses the same checkout.
return function(launcher)
    hl.on("hyprland.start", function()
        -- Finish initializing the daemon unlocked by PAM. Publish the graphical
        -- environment first so D-Bus can display later keyring unlock prompts.
        -- Enable the password store and the PKCS#11 interface for keys and certificates.
        hl.dispatch(hl.dsp.exec_cmd([[
            if command -v gnome-keyring-daemon >/dev/null 2>&1; then
                if command -v dbus-update-activation-environment >/dev/null 2>&1; then
                    dbus-update-activation-environment --systemd DISPLAY WAYLAND_DISPLAY XDG_CURRENT_DESKTOP
                fi
                gnome-keyring-daemon --start --components=secrets,pkcs11
            fi
        ]]))

        -- Start the desktop authentication agent for administrator password dialogs.
        hl.dispatch(hl.dsp.exec_cmd(launcher .. " auth start"))

        -- Start the idle monitor hidden; it shows the screensaver and locks later
        -- according to your idle settings rather than covering the desktop at login.
        hl.dispatch(hl.dsp.exec_cmd(launcher .. " screensaver start"))

        -- Start clipboard watchers so copied text and images enter clipboard history.
        hl.dispatch(hl.dsp.exec_cmd(launcher .. " clipboard start"))

        -- Restore the saved wallpaper and keep its renderer running for this session.
        hl.dispatch(hl.dsp.exec_cmd(launcher .. " wallpaper start"))

        -- Start the notification service, which also owns Luna's resident bar.
        hl.dispatch(hl.dsp.exec_cmd(launcher .. " notifications start"))

        -- Preload the menu without showing it; Super + Space opens it when needed.
        hl.dispatch(hl.dsp.exec_cmd(launcher .. " launcher start"))
    end)
end
