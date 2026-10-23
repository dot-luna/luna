-- Default applications by desktop entry ID, resolved after package installation.
-- "terminal" selects xdg-terminal-exec; other keys are MIME types, including
-- x-scheme-handler/... keys for URI schemes.
return {
    terminal = "kitty.desktop",
    ["inode/directory"] = "org.gnome.Nautilus.desktop",
    ["x-scheme-handler/http"] = "zen.desktop",
    ["x-scheme-handler/https"] = "zen.desktop",
    ["text/html"] = "zen.desktop",
    ["application/xhtml+xml"] = "zen.desktop",
}
