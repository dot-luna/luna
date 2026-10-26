#!/usr/bin/env bash
# Link this checkout's CLI into the system's local command directory.
set -euo pipefail

script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
setup_dir=${script_path%/*}
repo_dir=${setup_dir%/*/*}
source "$repo_dir/lib/common.sh"

command_source="$repo_dir/bin/luna"
command_target=/usr/local/bin/luna

if [[ ! -f "$command_source" || ! -x "$command_source" ]]; then
    luna_error "Luna launcher is missing or not executable: $command_source"
    exit 1
fi

# Earlier installs may still take precedence through the user's PATH.
local_command="$HOME/.local/bin/luna"
if [[ -f "$local_command" && -x "$local_command" && ! "$local_command" -ef "$command_source" ]]; then
    luna_warn "$local_command may override this installation. Remove it or run $command_target directly."
fi

if [[ -L "$command_target" && "$command_target" -ef "$command_source" ]]; then
    luna_info "Luna command is already installed: $command_target"
    exit 0
fi

# Resolve parent aliases without following the final link we will replace.
resolved_target="$(realpath -m -- "${command_target%/*}")/${command_target##*/}"
if [[ "$resolved_target" == "$repo_dir" || "$resolved_target" == "$repo_dir/"* \
    || "$repo_dir" == "$resolved_target/"* ]]; then
    luna_error "Command link would replace part of the checkout: $command_target. Choose a different install location."
    exit 1
fi

if [[ -d "$command_target" && ! -L "$command_target" ]]; then
    luna_error "Command destination is a directory: $command_target. Move it before running setup again."
    exit 1
fi

# Only system-directory writes need privileges; root can install without sudo.
privilege=()
if (( EUID != 0 )); then
    if ! luna_available sudo; then
        luna_error 'sudo is missing. Run this step as root to install the Luna command.'
        exit 1
    fi
    privilege=(sudo)
fi

"${privilege[@]}" mkdir -p -- "${command_target%/*}"

# Replace files and final symlinks, while refusing to overwrite a directory.
"${privilege[@]}" ln -sfnT -- "$command_source" "$command_target"
luna_success "Installed Luna command: $command_target"
