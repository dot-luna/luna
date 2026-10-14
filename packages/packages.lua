-- Package manifest for Luna on an existing Arch Linux installation.
-- Each entry declares its installation source and why Luna uses it.
-- Core contains setup tools and desktop dependencies; main contains everyday
-- applications and AUR packages.
-- Extra is reserved for optional additions outside the main setup.
-- Package managers resolve transitive dependencies automatically.
--
-- scripts/setup-lua.sh bootstraps lua and lua-argparse before this file
-- can be read. Other core tools will be handled by the main setup later.
return {
    -- Never put AUR packages in core: every core entry must use pacman.
    -- Only Lua and argparse are installed by setup-lua.sh; keep those two
    -- entries in sync with that script.
    core = {
        -- Bootstrap, repository, and package build tools.
        { name = "bash", source = "pacman", purpose = "Run the bootstrap entry script" },
        { name = "coreutils", source = "pacman", purpose = "Basic filesystem and shell utilities" },
        { name = "sudo", source = "pacman", purpose = "Install system packages from a normal user account" },
        { name = "git", source = "pacman", purpose = "Obtain and update the Luna repository" },
        { name = "curl", source = "pacman", purpose = "Download wallpapers from HTTP and HTTPS URLs" },
        { name = "lua", source = "pacman", purpose = "Run Lua setup scripts and read this manifest" },
        { name = "lua-argparse", source = "pacman", purpose = "Parse Luna CLI commands and generate help" },
        { name = "base-devel", source = "pacman", purpose = "Build AUR packages when needed" },

        -- Deploy configuration from this checkout into the user's home.
        { name = "stow", source = "pacman", purpose = "Link repository configs into the home directory" },

        -- Font discovery, validation, and cache updates for the Luna font CLI.
        { name = "fontconfig", source = "pacman", purpose = "Provide fc-list, fc-scan, and fc-cache" },

        -- Validate wallpaper files and open their library with the desktop default.
        { name = "file", source = "pacman", purpose = "Identify image file types" },
        { name = "xdg-utils", source = "pacman", purpose = "Open folders in the default file explorer" },

        -- Desktop compositor, app portals, and custom Quickshell UI.
        { name = "hyprland", source = "pacman", purpose = "Wayland desktop compositor" },
        { name = "xdg-desktop-portal-hyprland", source = "pacman", purpose = "Hyprland screen sharing and portal integration" },
        { name = "xdg-desktop-portal-gtk", source = "pacman", purpose = "GTK file chooser and fallback portals" },
        { name = "glib2", source = "pacman", purpose = "Provide gsettings for system appearance preferences" },
        { name = "gsettings-desktop-schemas", source = "pacman", purpose = "Define the desktop light/dark preference" },
        { name = "dconf", source = "pacman", purpose = "Persist desktop settings and publish changes to applications" },
        { name = "quickshell", source = "pacman", purpose = "Runtime for a custom bar, launcher, and desktop UI" },
        { name = "qt6-svg", source = "pacman", purpose = "Render SVG icons in the custom desktop UI" },
        { name = "qt6-imageformats", source = "pacman", purpose = "Decode additional wallpaper formats, including WebP" },
        { name = "polkit", source = "pacman", purpose = "Desktop authorization backend; also needs an authentication agent" },
        { name = "polkit-kde-agent", source = "pacman", purpose = "Administrator password dialogs" },

        -- Audio service, compatibility layers, and device session management.
        { name = "pipewire", source = "pacman", purpose = "Audio and video service" },
        { name = "pipewire-audio", source = "pacman", purpose = "PipeWire audio support" },
        { name = "pipewire-alsa", source = "pacman", purpose = "ALSA audio compatibility" },
        { name = "pipewire-pulse", source = "pacman", purpose = "PulseAudio compatibility" },
        { name = "wireplumber", source = "pacman", purpose = "Manage PipeWire devices and sessions" },

        -- Network and Bluetooth backends plus battery reporting.
        { name = "networkmanager", source = "pacman", purpose = "Network connection management" },
        { name = "bluez", source = "pacman", purpose = "Bluetooth service" },
        { name = "bluez-utils", source = "pacman", purpose = "Bluetooth command-line tools" },
        { name = "upower", source = "pacman", purpose = "Battery and power information" },

        -- Container runtime and Windows VM client; Docker is enabled separately.
        { name = "docker", source = "pacman", purpose = "Run containers and the Dockur Windows VM" },
        { name = "docker-compose", source = "pacman", purpose = "Manage container stacks with Docker Compose" },
        { name = "freerdp", source = "pacman", purpose = "Connect to the Windows VM over RDP" },

        -- Desktop controls for brightness, clipboard access, and locking.
        { name = "brightnessctl", source = "pacman", purpose = "Display brightness controls" },
        { name = "noto-fonts-emoji", source = "pacman", purpose = "Color emoji rendering" },
        { name = "cliphist", source = "pacman", purpose = "Text and image clipboard history" },
        { name = "wtype", source = "pacman", purpose = "Paste clipboard selections into Wayland applications" },
        { name = "wl-clipboard", source = "pacman", purpose = "Wayland clipboard tools" },
        { name = "grim", source = "pacman", purpose = "Capture Wayland screenshots" },
        { name = "slurp", source = "pacman", purpose = "Select a screenshot region" },
        { name = "python", source = "pacman", purpose = "Run screenshot, clipboard, and insert helpers" },
        { name = "python-dbus", source = "pacman", purpose = "Bluetooth pairing agent communication" },
        { name = "python-gobject", source = "pacman", purpose = "Bluetooth pairing event loop" },
        { name = "wf-recorder", source = "pacman", purpose = "Record a Wayland screen or selected region" },
        { name = "libnotify", source = "pacman", purpose = "Send desktop notifications from Luna tools" },
        { name = "libcanberra", source = "pacman", purpose = "Play desktop notification event sounds" },
        { name = "sound-theme-freedesktop", source = "pacman", purpose = "Standard sounds for notification priorities" },
        { name = "hyprlock", source = "pacman", purpose = "Screen locking" },
    },

    -- Everyday applications and AUR packages.
    main = {
        -- Everyday applications and development tools.
        { name = "kitty", source = "pacman", purpose = "Terminal emulator" },
        { name = "zed", source = "pacman", purpose = "Code editor" },
        { name = "ripgrep", source = "pacman", purpose = "Search files from the terminal" },
        { name = "github-cli", source = "pacman", purpose = "GitHub repository workflows" },

        -- AUR packages require a separate build/helper installation step.
        { name = "zen-browser-bin", source = "aur", purpose = "Zen Browser prebuilt release" },
    },

    -- Optional additions outside the main setup.
    extra = {},
}
