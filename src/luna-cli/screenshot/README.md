# Screenshots

```sh
luna screenshot          # Select a region; Escape cancels.
luna screenshot region
luna screenshot screen   # Focused monitor.
luna screenshot window   # Visible rectangle of the focused window.
luna screenshot all      # Combined desktop across all monitors.
```

Each capture saves a PNG to `~/Pictures/Screenshots` and copies the image to the
Wayland clipboard. Filenames contain the local date and time plus a unique suffix,
so previous captures are never overwritten. The CLI prints the saved path.
Set `LUNA_SCREENSHOT_DIR` to use a different directory.

Luna's menu provides the same actions under Trigger → Screenshot. Shortcuts are
Print for a region, Shift + Print for the active screen, Alt + Print for the active
window, and Ctrl + Print for all screens. Find them under Learn → Hyprland Keybindings.

The launcher closes before capture. Region selection waits for a mouse drag;
Escape cancels without saving or changing the clipboard. Only one capture runs at
a time. A failed capture removes its incomplete file; if clipboard copying fails,
the completed image stays saved and the error includes its path. Menu errors are
shown in the launcher.

Successful captures also show a Luna notification with a preview and Open image
action. Failures show an error notification; cancelling does not send one.
Notification delivery is best effort and never changes whether a capture succeeds.

Captures use `grim`, `slurp`, and `wl-copy` from `wl-clipboard`, with Python handling
file creation and Hyprland geometry. These are included in Luna's core packages.
Screen and window modes require Hyprland. Window mode captures the on-screen
rectangle, including anything that overlaps it; it does not render hidden windows.
