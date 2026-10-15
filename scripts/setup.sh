#!/usr/bin/env bash
# Run Luna setup from this checkout, regardless of the working directory.
set -euo pipefail

# Load repository-wide helpers, including when reached via a symlink.
script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
source "$(dirname -- "$script_path")/../lib/common.sh"

# Validate entry options before starting any system changes.
for option in "$@"; do
    case "$option" in
        --force)
            ;;
        -h|--help)
            printf 'Usage: %s [--force]\n\nSet up packages, fonts, Docker, config/source links, and the Luna command.\nPackages install without confirmation; sudo may ask for authentication.\nConfig and source conflicts are backed up and replaced automatically.\nThe final step asks whether to install NVIDIA drivers and tools.\n--force reinstalls packages. Extra packages are excluded.\n' "${0##*/}"
            exit 0
            ;;
        *)
            luna_error "Unknown option: $option"
            exit 2
            ;;
    esac
done

# Keep individual steps together, independently of the caller's directory.
setup_dir=$(luna_script_dir "${BASH_SOURCE[0]}")
steps_dir="$setup_dir/setup"

# Step 1: prepare Lua and argparse before running any Lua setup logic.
# Forward --force consistently to bootstrap and package installation.
luna_step '1/10 — Prepare Lua'
bash "$steps_dir/lua.sh" "$@"

# Step 2: install official setup tools and desktop dependencies.
luna_step '2/10 — Install core packages'
/usr/bin/lua -E "$steps_dir/install-deps.lua" core "$@"

# Step 3: prepare an AUR helper for main packages and fonts.
luna_step '3/10 — Prepare the AUR helper'
bash "$steps_dir/aur.sh"

# Step 4: install everyday apps and AUR packages. Extra remains opt-in.
luna_step '4/10 — Install applications'
/usr/bin/lua -E "$steps_dir/install-deps.lua" main "$@"

# Step 5: install desktop fonts from official repositories and the AUR.
luna_step '5/10 — Install fonts'
/usr/bin/lua -E "$steps_dir/install-deps.lua" fonts "$@"

# Step 6: service setup is best effort on systems where systemd is unavailable.
luna_step '6/10 — Enable Docker'
bash "$steps_dir/services.sh"

# Step 7: deploy configuration, backing up existing conflicting paths.
luna_step '7/10 — Link Hyprland configuration'
bash "$steps_dir/config.sh" "$@"

# Step 8: expose source packages through whole-directory links.
luna_step '8/10 — Link source directories'
bash "$steps_dir/src.sh" "$@"

# Step 9: give shells a stable entry point independent of the checkout location.
luna_step '9/10 — Install the Luna command'
bash "$steps_dir/command.sh" "$@"

# Step 10: optional hardware-specific setup must remain last and ask for consent.
luna_step '10/10 — Optional NVIDIA setup'
bash "$steps_dir/nvidia.sh"
