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
# The standalone installer forwards skip values unchanged to this runner.
declare -A skipped_steps=()
valid_steps='lua,core,mise,aur,main,fonts,git-apps,command,postinstall,apps,keyring,src,defaults,app-extras,session'
for argument in "$@"; do
    case "$argument" in
        --skip=*)
            remaining=${argument#--skip=}
            while true; do
                name=${remaining%%,*}
                case "$name" in
                    # Each --skip name omits the corresponding work below:
                    # lua: prepare Lua, argparse, and TOMLKit.
                    # core: install setup tools and desktop dependencies.
                    # mise: install development tools and configure mise in shells.
                    # aur: prepare the AUR helper.
                    # main: install application packages.
                    # fonts: install desktop fonts.
                    # git-apps: build and install applications from Git repositories.
                    # command: install the Luna CLI entry point in /usr/local/bin.
                    # postinstall: install and select the bundled Tokyo Night theme.
                    # apps: install and generate application configurations.
                    # keyring: configure GNOME Keyring for credential storage.
                    # src: link Luna source directories into ~/.local/src.
                    # defaults: set default applications.
                    # app-extras: install optional browser extensions and mods.
                    # session: reload the active Hyprland session's configuration.
                    # Skips do not automatically skip dependent steps.
                    lua|core|mise|aur|main|fonts|git-apps|command|postinstall|apps|keyring|src|defaults|app-extras|session)
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

# Step 1: prepare Lua and configuration dependencies before the remaining setup.
run_setup_step lua '1/15 — Prepare Lua and TOMLKit' '' bash "$steps_dir/1-setup-lua.sh"

# Step 2: install official setup tools and desktop dependencies.
run_setup_step core '2/15 — Install core packages' '' bash "$steps_dir/2-install-core-deps.sh"

# Step 3: development tools are optional and must not block desktop setup.
run_setup_step mise '3/15 — Install development tools with mise' \
    'Development tools setup failed; continuing.' /usr/bin/lua -E "$steps_dir/3-install-dev-tools.lua"

# Step 4: prepare an AUR helper for main packages and fonts.
run_setup_step aur '4/15 — Prepare the AUR helper' \
    'AUR helper setup failed; continuing.' bash "$steps_dir/4-setup-aur-helper.sh"

# Step 5: install everyday apps and AUR packages. Extra remains opt-in.
run_setup_step main '5/15 — Install applications' \
    'Application setup failed; continuing.' bash "$steps_dir/5-install-app-packages.sh"

# Step 6: install desktop fonts from official repositories and the AUR.
run_setup_step fonts '6/15 — Install fonts' \
    'Font setup failed; continuing.' bash "$steps_dir/6-install-fonts.sh"

# Step 7: each Git app owns its dependencies, native build, and installation.
run_setup_step git-apps '7/15 — Build and install Git apps' \
    'Git app setup failed; continuing.' /usr/bin/lua -E "$steps_dir/7-install-git-apps.lua"

# Step 8: install a global launcher independent of the shell and checkout location.
run_setup_step command '8/15 — Install the Luna command' '' bash "$steps_dir/8-install-luna-command.sh"

# Step 9: finish user defaults after installation and before the session reads them.
run_setup_step postinstall '9/15 — Set up Tokyo Night' \
    'Bundled theme setup failed; continuing.' bash "$steps_dir/9-setup-default-theme.sh"

# Step 10: generate app colors and fonts after the selected theme is available.
run_setup_step apps '10/15 — Install application configurations' '' /usr/bin/lua -E "$steps_dir/10-setup-app-configs.lua"

# Step 11: configure credential storage before defaults and the session reload.
run_setup_step keyring '11/15 — Configure GNOME Keyring' '' bash "$steps_dir/11-setup-gnome-keyring.sh"

# Step 12: expose source packages through whole-directory links before session reload.
run_setup_step src '12/15 — Link source directories' '' bash "$steps_dir/12-link-sources.sh"

# Step 13: set default applications after their packages and configuration are installed.
run_setup_step defaults '13/15 — Configure default applications' '' bash "$steps_dir/13-set-default-apps.sh"

# Step 14: optional app actions run separately from copying configuration files.
run_setup_step app-extras '14/15 — Set up optional app extras' \
    'Optional app extras failed; continuing.' bash "$steps_dir/14-setup-app-extras.sh"

# Step 15: apply the completed configuration to an active session without another prompt.
run_setup_step session '15/15 — Apply Hyprland configuration' \
    'Session reload failed; log out and back in to apply the configuration.' bash "$steps_dir/15-reload-hyprland.sh"
