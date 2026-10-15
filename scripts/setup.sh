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
            printf 'Usage: %s [--force]\n\nSet up Lua, core packages, an AUR helper, main packages, fonts, and config/source links.\nConfig and source conflicts are backed up and replaced automatically.\nThe final step asks whether to install NVIDIA drivers and tools.\n--force reinstalls packages. Extra packages are excluded.\n' "${0##*/}"
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
bash "$steps_dir/lua.sh" "$@"

# Step 2: install official setup tools and desktop dependencies.
/usr/bin/lua -E "$steps_dir/install-deps.lua" core "$@"

# Step 3: prepare an AUR helper for main packages and fonts.
bash "$steps_dir/aur.sh"

# Step 4: install everyday apps and AUR packages. Extra remains opt-in.
/usr/bin/lua -E "$steps_dir/install-deps.lua" main "$@"

# Step 5: install desktop fonts from official repositories and the AUR.
/usr/bin/lua -E "$steps_dir/install-deps.lua" fonts "$@"

# Step 6: deploy configuration, backing up existing conflicting paths.
bash "$steps_dir/config.sh" "$@"

# Step 7: expose source packages through whole-directory links.
bash "$steps_dir/src.sh" "$@"

# Step 8: optional hardware-specific setup must remain last and ask for consent.
bash "$steps_dir/nvidia.sh"
