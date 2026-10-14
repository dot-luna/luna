# Notifications

`luna notifications` opens the notification center. `dnd` toggles Do Not Disturb,
`clear` dismisses notifications, and `status` reads the running bar's JSON status
without starting it. A stopped bar reports `{"running":false}`.

`luna notifications setup` and `luna notifications start` both install or refresh
per-user activation and start the provider. Startup preserves an already running
service. Setup validates the current theme and bar preferences before changing
the running desktop.

The provider is Luna Bar under `luna-notifications.service`, with the D-Bus name
`org.freedesktop.Notifications`. The unit lives under
`$XDG_CONFIG_HOME/systemd/user/`; its activation override lives at
`$XDG_DATA_HOME/dbus-1/services/org.freedesktop.Notifications.service`.
The default locations are `~/.config` and `~/.local/share`.

Setup imports the current Wayland session environment, stops a standalone Luna
bar, and masks/stops the user Dunst service before starting Luna. Failed startup
restores the previous activation files and Dunst state. Dunst remains installed.
Hyprland runs `luna notifications start` at login; D-Bus activation can also
restart the provider when an application sends a notification.

To return to Dunst, stop `luna-notifications.service`, remove Luna's two generated
activation files, reload the user service manager, then unmask/start
`dunst.service`. Also remove Luna's notification startup command from personal
Hyprland configuration if changing the default session behavior permanently.
