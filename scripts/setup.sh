#!/usr/bin/env bash
# Run the installer's setup steps from this checkout, regardless of the working directory.
# Extra arguments are ignored; setup always uses its defaults.
set -euo pipefail

# Load repository-wide helpers, including when reached via a symlink.
script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
source "$(dirname -- "$script_path")/../lib/common.sh"

# Keep individual steps together, independently of the caller's directory.
setup_dir=$(luna_script_dir "${BASH_SOURCE[0]}")
steps_dir="$setup_dir/setup"

luna_warn 'Back up files you want to keep; setup replaces conflicts without backups.'

# Step 1: prepare Lua and argparse before running any Lua setup logic.
luna_step '1/9 — Prepare Lua'
bash "$steps_dir/lua.sh"

# Step 2: install official setup tools and desktop dependencies.
luna_step '2/9 — Install core packages'
/usr/bin/lua -E "$steps_dir/install-deps.lua" core

# Step 3: development tools are optional and must not block desktop setup.
luna_step '3/9 — Install development tools with mise'
if ! /usr/bin/lua -E "$steps_dir/mise.lua"; then
    luna_warn 'Development tools setup failed; continuing.'
fi

# Step 4: prepare an AUR helper for main packages and fonts.
luna_step '4/9 — Prepare the AUR helper'
if ! bash "$steps_dir/aur.sh"; then
    luna_warn 'AUR helper setup failed; continuing.'
fi

# Step 5: install everyday apps and AUR packages. Extra remains opt-in.
luna_step '5/9 — Install applications'
if ! /usr/bin/lua -E "$steps_dir/install-deps.lua" main; then
    luna_warn 'Application setup failed; continuing.'
fi

# Step 6: install desktop fonts from official repositories and the AUR.
luna_step '6/9 — Install fonts'
if ! /usr/bin/lua -E "$steps_dir/install-deps.lua" fonts; then
    luna_warn 'Font setup failed; continuing.'
fi

# Step 7: each Git app owns its dependencies, native build, and installation.
luna_step '7/9 — Build and install Git apps'
if ! /usr/bin/lua -E "$steps_dir/git-apps.lua"; then
    luna_warn 'Git app setup failed; continuing.'
fi

# Step 8: expose source packages through whole-directory links.
luna_step '8/9 — Link source directories'
bash "$steps_dir/src.sh"

# Step 9: give shells a stable entry point independent of the checkout location.
luna_step '9/9 — Install the Luna command'
bash "$steps_dir/command.sh"

# Apply the completed configuration to an active session without another prompt.
luna_step 'Apply Hyprland configuration'
if ! bash "$steps_dir/session.sh"; then
    luna_warn 'Session reload failed; log out and back in to apply the configuration.'
fi
