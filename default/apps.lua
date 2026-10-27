-- Default applications by desktop entry ID, resolved after package installation.
-- "terminal" selects xdg-terminal-exec; other keys are MIME types, including
-- x-scheme-handler/... keys for URI schemes. Image/audio/video wildcards select only
-- types advertised by the installed desktop entry; exact MIME keys override them.
return {
    terminal = "kitty.desktop",
    ["inode/directory"] = "org.gnome.Nautilus.desktop",
    ["x-scheme-handler/http"] = "zen.desktop",
    ["x-scheme-handler/https"] = "zen.desktop",
    ["text/html"] = "zen.desktop",
    ["application/xhtml+xml"] = "zen.desktop",

    ["image/*"] = "imv.desktop",
    ["application/pdf"] = "org.gnome.Evince.desktop",

    -- Keep common source and structured text types explicit: xdg-mime does not
    -- inherit the plain-text default the way GIO file opening does.
    ["text/plain"] = "dev.zed.Zed.desktop",
    ["text/markdown"] = "dev.zed.Zed.desktop",
    ["text/x-log"] = "dev.zed.Zed.desktop",
    ["text/x-python"] = "dev.zed.Zed.desktop",
    ["text/x-python2"] = "dev.zed.Zed.desktop",
    ["text/x-python3"] = "dev.zed.Zed.desktop",
    ["text/x-lua"] = "dev.zed.Zed.desktop",
    ["text/x-shellscript"] = "dev.zed.Zed.desktop",
    ["text/x-makefile"] = "dev.zed.Zed.desktop",
    ["text/x-csrc"] = "dev.zed.Zed.desktop",
    ["text/x-chdr"] = "dev.zed.Zed.desktop",
    ["text/x-c++src"] = "dev.zed.Zed.desktop",
    ["text/x-c++hdr"] = "dev.zed.Zed.desktop",
    ["text/x-java"] = "dev.zed.Zed.desktop",
    ["text/x-go"] = "dev.zed.Zed.desktop",
    ["text/rust"] = "dev.zed.Zed.desktop",
    ["text/javascript"] = "dev.zed.Zed.desktop",
    ["text/css"] = "dev.zed.Zed.desktop",
    ["text/x-qml"] = "dev.zed.Zed.desktop",
    ["application/x-zerosize"] = "dev.zed.Zed.desktop",
    ["application/json"] = "dev.zed.Zed.desktop",
    ["application/toml"] = "dev.zed.Zed.desktop",
    ["application/yaml"] = "dev.zed.Zed.desktop",
    ["application/xml"] = "dev.zed.Zed.desktop",
    ["application/typescript"] = "dev.zed.Zed.desktop",
    ["application/x-ruby"] = "dev.zed.Zed.desktop",

    ["audio/*"] = "mpv.desktop",
    ["video/*"] = "mpv.desktop",
}
