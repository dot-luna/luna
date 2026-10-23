#!/usr/bin/env bash
# Run the installer's setup steps from this checkout, regardless of the working directory.
# --skip accepts comma-separated step names; unrelated extra arguments are ignored.
set -euo pipefail

# Load repository-wide helpers, including when reached via a symlink.
script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
source "$(dirname -- "$script_path")/../lib/common.sh"

# Keep individual steps together, independently of the caller's directory.
setup_dir=$(luna_script_dir "${BASH_SOURCE[0]}")
steps_dir="$setup_dir/setup"

# Validate skip requests before any step can install packages or change files.
# Keep these names in sync with the standalone installer's --skip option.
declare -A skipped_steps=()
valid_steps='lua,core,mise,aur,main,fonts,git-apps,src,command,postinstall,apps,defaults,session'
for argument in "$@"; do
    case "$argument" in
        --skip=*)
            remaining=${argument#--skip=}
            while true; do
                name=${remaining%%,*}
                case "$name" in
                    lua|core|mise|aur|main|fonts|git-apps|src|command|postinstall|apps|defaults|session)
                        skipped_steps[$name]=1
                        ;;
                    *)
                        luna_error "Invalid step in --skip: '$name'. Use --skip=$valid_steps"
                        exit 2
                        ;;
                esac
                [[ "$remaining" == *,* ]] || break
                remaining=${remaining#*,}
            done
            ;;
        --skip)
            luna_error 'Use --skip=step1,step2 to select setup steps to skip.'
            exit 2
            ;;
    esac
done

# Skips affect only named steps. Required steps still stop on failure; optional
# ones retain their warning and continue behavior when they are actually run.
run_setup_step() {
    local name=$1 label=$2 warning=$3
    shift 3

    if [[ -n "${skipped_steps[$name]:-}" ]]; then
        luna_info "Skipping $name."
        return 0
    fi

    luna_step "$label"
    if [[ -n "$warning" ]]; then
        if ! "$@"; then
            luna_warn "$warning"
        fi
    else
        "$@"
    fi
}

# Resolve the app destination before package installation begins.
luna_resolve_config_dir

luna_warn 'Back up files you want to keep; setup replaces conflicts without backups.'

# Step 1: prepare Lua and argparse before running any Lua setup logic.
run_setup_step lua '1/9 — Prepare Lua' '' bash "$steps_dir/lua.sh"

# Step 2: install official setup tools and desktop dependencies.
run_setup_step core '2/9 — Install core packages' '' /usr/bin/lua -E "$steps_dir/install-deps.lua" core

# Step 3: development tools are optional and must not block desktop setup.
run_setup_step mise '3/9 — Install development tools with mise' \
    'Development tools setup failed; continuing.' /usr/bin/lua -E "$steps_dir/mise.lua"

# Step 4: prepare an AUR helper for main packages and fonts.
run_setup_step aur '4/9 — Prepare the AUR helper' \
    'AUR helper setup failed; continuing.' bash "$steps_dir/aur.sh"

# Step 5: install everyday apps and AUR packages. Extra remains opt-in.
run_setup_step main '5/9 — Install applications' \
    'Application setup failed; continuing.' /usr/bin/lua -E "$steps_dir/install-deps.lua" main

# Step 6: install desktop fonts from official repositories and the AUR.
run_setup_step fonts '6/9 — Install fonts' \
    'Font setup failed; continuing.' /usr/bin/lua -E "$steps_dir/install-deps.lua" fonts

# Step 7: each Git app owns its dependencies, native build, and installation.
run_setup_step git-apps '7/9 — Build and install Git apps' \
    'Git app setup failed; continuing.' /usr/bin/lua -E "$steps_dir/git-apps.lua"

# Step 8: expose source packages through whole-directory links.
run_setup_step src '8/9 — Link source directories' '' bash "$steps_dir/src.sh"

# Step 9: give shells a stable entry point independent of the checkout location.
run_setup_step command '9/9 — Install the Luna command' '' bash "$steps_dir/command.sh"

# Finish user defaults after installation and before the session reads them.
run_setup_step postinstall 'Post-install — Set up Tokyo Night' \
    'Bundled theme setup failed; continuing.' bash "$steps_dir/postinstall.sh"

# Generate app colors and fonts only after the selected theme is available.
run_setup_step apps 'Install application configurations' '' bash "$steps_dir/apps.sh"

# Set default applications after their packages and configuration are installed.
run_setup_step defaults 'Configure default applications' '' bash "$steps_dir/defaults.sh"

# Apply the completed configuration to an active session without another prompt.
run_setup_step session 'Apply Hyprland configuration' \
    'Session reload failed; log out and back in to apply the configuration.' bash "$steps_dir/session.sh"
