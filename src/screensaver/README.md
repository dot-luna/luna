# Luna screensaver and idle options

A themed clock and date drift gently across each monitor. Keyboard input, pointer
movement, clicking, or scrolling dismisses the screensaver. It does not authenticate;
Hyprlock supplies the separate password lock.

- System → Screensaver opens it immediately.
- Setup → Idle → Auto Screensaver / Auto Lock sets either timer independently.
- Defaults: screensaver after 300 seconds, lock after 600 seconds of inactivity.
- Disabled (0) turns a timer off.
- Wayland idle inhibitors are respected, including those requested by video players.

Preferences live in `~/.config/luna/idle.json`:

```json
{"screensaver_seconds":300,"lock_seconds":600}
```

`luna idle set screensaver 300` and `luna idle set lock 600` save and apply choices.
`luna idle status` shows the current settings. Direct file edits require
`luna screensaver reload`.

`luna screensaver` shows the screensaver; `hide` dismisses it; `start` starts the
hidden idle monitor; `stop` stops both the screensaver and automatic timers.
Hyprland starts the monitor on login. Quickshell's native IdleMonitor uses compositor
notifications, so Hypridle is not required. Automatic locking uses `luna lock`.
