-- Package manifest for Luna on an existing Arch Linux installation.
-- Each entry declares its installation source and why Luna uses it.
-- Core contains setup tools and desktop dependencies; main contains everyday
-- applications and AUR packages. Fonts are installed after main.
-- Extra is reserved for optional additions outside the main setup.
-- Package managers resolve transitive dependencies automatically.
--
-- scripts/setup/1-setup-lua.sh bootstraps lua, lua-argparse, and python-tomlkit
-- before this file can be read. Other core tools are installed in the next step.
return {
    -- Never put AUR packages in core: every core entry must use pacman.
    -- Keep the Lua, argparse, and TOMLKit bootstrap entries in sync with step 1.
    core = {
        -- Bootstrap, repository, and package build tools.
        { name = "bash", source = "pacman", purpose = "Run the bootstrap entry script" },
        { name = "coreutils", source = "pacman", purpose = "Basic filesystem and shell utilities" },
        { name = "sudo", source = "pacman", purpose = "Install system packages from a normal user account" },
        { name = "git", source = "pacman", purpose = "Obtain and update the Luna repository" },
        { name = "curl", source = "pacman", purpose = "Download wallpapers from HTTP and HTTPS URLs" },
        { name = "lua", source = "pacman", purpose = "Run Lua setup scripts and read this manifest" },
        { name = "lua-argparse", source = "pacman", purpose = "Parse Luna CLI commands and generate help" },
        { name = "python-tomlkit", source = "pacman", purpose = "Parse TOML and edit configuration while preserving comments" },
        { name = "base-devel", source = "pacman", purpose = "Build AUR packages when needed" },
        { name = "mise", source = "pacman", purpose = "Manage development tools and runtime versions" },
        { name = "ripgrep", source = "pacman", purpose = "Search files from the terminal" },

        -- General dotfile and source-directory symlink management.
        { name = "stow", source = "pacman", purpose = "Manage symlinks for dotfiles and source directories" },

        -- Font discovery, validation, and cache updates for the Luna font CLI.
        { name = "fontconfig", source = "pacman", purpose = "Provide fc-list, fc-scan, and fc-cache" },

        -- Validate wallpaper files and open their library with the desktop default.
        { name = "file", source = "pacman", purpose = "Identify image file types" },
        { name = "xdg-utils", source = "pacman", purpose = "Open folders in the default file explorer" },

        -- Core file management and media playback.
        { name = "yazi", source = "pacman", purpose = "Terminal file manager" },
        { name = "nautilus", source = "pacman", purpose = "Graphical file manager" },
        { name = "mpv", source = "pacman", purpose = "Video and audio player" },

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

        -- TODO: Replace this KDE agent with Luna's own Quickshell polkit UI.
        { name = "polkit-kde-agent", source = "pacman", purpose = "Administrator password dialogs" },

        -- Store application credentials through the desktop Secret Service.
        { name = "gnome-keyring", source = "pacman", purpose = "Store application passwords and provide Secret Service" },
        { name = "libsecret", source = "pacman", purpose = "Access stored secrets from applications and secret-tool" },

        -- Audio service, compatibility layers, and device session management.
        { name = "pipewire", source = "pacman", purpose = "Audio and video service" },
        { name = "pipewire-audio", source = "pacman", purpose = "PipeWire audio support" },
        { name = "pipewire-alsa", source = "pacman", purpose = "ALSA audio compatibility" },
        { name = "pipewire-pulse", source = "pacman", purpose = "PulseAudio compatibility" },
        { name = "wireplumber", source = "pacman", purpose = "Manage PipeWire devices and sessions" },

        -- Network and Bluetooth backends plus battery reporting and power modes.
        { name = "networkmanager", source = "pacman", purpose = "Network connection management" },
        { name = "bluez", source = "pacman", purpose = "Bluetooth service" },
        { name = "bluez-utils", source = "pacman", purpose = "Bluetooth command-line tools" },
        { name = "upower", source = "pacman", purpose = "Battery and power information" },
        { name = "power-profiles-daemon", source = "pacman", purpose = "Provide powerprofilesctl and desktop power mode switching" },

        -- Container runtime and desktop clients for the Windows and macOS VMs.
        { name = "docker", source = "pacman", purpose = "Run containers and the Dockur Windows and macOS VMs" },
        { name = "docker-compose", source = "pacman", purpose = "Manage container stacks with Docker Compose" },
        { name = "freerdp", source = "pacman", purpose = "Connect to the Windows VM over RDP" },
        { name = "tigervnc", source = "pacman", purpose = "Connect to the macOS VM console over VNC" },

        -- Desktop controls for brightness, clipboard access, and locking.
        { name = "brightnessctl", source = "pacman", purpose = "Display brightness controls" },
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
        { name = "xdg-terminal-exec", source = "pacman", purpose = "Run commands in the preferred terminal" },
        { name = "starship", source = "pacman", purpose = "Customizable shell prompt" },
        { name = "zsh", source = "pacman", purpose = "Interactive shell" },
        { name = "seahorse", source = "pacman", purpose = "Manage stored passwords and keyrings graphically" },

        -- Everyday image viewing, document reading, and calculations.
        { name = "imv", source = "pacman", purpose = "Default image viewer" },
        { name = "evince", source = "pacman", purpose = "Default PDF reader" },
        { name = "gnome-calculator", source = "pacman", purpose = "Desktop calculator" },

        -- Archive tools supplement the tar and compression utilities provided by Arch.
        { name = "zip", source = "pacman", purpose = "Create ZIP archives from the terminal" },
        { name = "unzip", source = "pacman", purpose = "Extract ZIP archives from the terminal" },
        { name = "7zip", source = "pacman", purpose = "Create 7z archives and extract additional formats, including RAR" },

        -- Interactive suggestions, completion, navigation, and file previews.
        { name = "zsh-autosuggestions", source = "pacman", purpose = "Suggest commands from shell history" },
        { name = "zsh-syntax-highlighting", source = "pacman", purpose = "Highlight commands while typing" },
        { name = "zsh-completions", source = "pacman", purpose = "Complete additional commands and options" },
        { name = "fzf", source = "pacman", purpose = "Search shell history, files, and directories interactively" },
        { name = "zoxide", source = "pacman", purpose = "Jump to frequently used directories with cd" },
        { name = "bat", source = "pacman", purpose = "Preview files with syntax highlighting" },
        { name = "eza", source = "pacman", purpose = "List files with colors, icons, and Git status" },
        { name = "fd", source = "pacman", purpose = "Find files and directories for fuzzy selection" },

        -- Editor and development workflows.
        { name = "zed", source = "pacman", purpose = "Code editor" },
        { name = "github-cli", source = "pacman", purpose = "GitHub repository workflows" },

        -- AUR packages require a separate build/helper installation step.
        { name = "fzf-tab", source = "aur", purpose = "Select Zsh completions with a fuzzy menu" },
        { name = "zen-browser-bin", source = "aur", purpose = "Zen Browser prebuilt release" },
        { name = "t3code-nightly-bin", source = "aur", purpose = "T3 Code desktop app, prebuilt nightly release" },
    },

    -- Install after main so an AUR helper is ready for the interface font.
    fonts = {
        { name = "ttf-iosevka-nerd", source = "pacman", purpose = "Provide Luna's default monospace font" },
        { name = "noto-fonts-emoji", source = "pacman", purpose = "Color emoji rendering" },
        { name = "ttf-outfit", source = "aur", purpose = "Provide Luna's default interface font" },
    },

    -- Optional additions outside the main setup.
    extra = {},
}
