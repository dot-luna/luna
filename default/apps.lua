-- Default applications by desktop entry ID, resolved after package installation.
-- "terminal" selects xdg-terminal-exec; other keys are MIME types, including
-- x-scheme-handler/... keys for URI schemes.
return {
    terminal = "kitty.desktop",
    ["inode/directory"] = "org.gnome.Nautilus.desktop",
}
