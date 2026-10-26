# Terminal

`luna terminal` opens the terminal selected in your `xdg-terminal-exec` preferences.
When a terminal is focused, it starts in that terminal's shell directory; other
apps and unavailable or ambiguous directory lookups fall back to your home folder.
**Super + Enter** uses the same command and captures the focused process at keypress.

Kitty's local per-process socket identifies the focused tab and pane, including the
drop-down terminal. The shell directory is preserved while commands run. Other
supported terminals use a single identifiable child shell when available; multiple
tabs or panes without Kitty IPC fall back to home rather than guessing.

After installing the updated Kitty and Hyprland configs, reload Hyprland and open
a fresh Kitty instance. Existing Kitty processes need restarting to create their
socket; reloading Kitty's config alone cannot enable it.
