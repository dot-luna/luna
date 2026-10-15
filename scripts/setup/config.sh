#!/usr/bin/env bash
# Back up conflicting paths and link Luna's Hyprland configuration with GNU Stow.
set -euo pipefail

script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
source "$(dirname -- "$script_path")/../../lib/common.sh"

for option in "$@"; do
    case "$option" in
        --force)
            # Retained for callers; conflicting paths are always backed up.
            ;;
        -h|--help)
            printf 'Usage: %s [--force]\n\nStow Hyprland config into XDG_CONFIG_HOME.\nExisting conflicting paths are moved to adjacent .luna-backup paths before replacement.\n--force is accepted for compatibility; backups are always made.\n' "${0##*/}"
            exit 0
            ;;
        *)
            luna_error "Unknown option: $option"
            exit 2
            ;;
    esac
done

if ! luna_available stow; then
    luna_error 'GNU Stow is missing; install core dependencies first.'
    exit 1
fi

setup_dir=$(luna_script_dir "${BASH_SOURCE[0]}")
repo_dir=$(dirname -- "$(dirname -- "$setup_dir")")
config_dir=${XDG_CONFIG_HOME:-"$HOME/.config"}
package_dir="$repo_dir/config/hypr"
entry_point="$config_dir/hypr/hyprland.lua"
source_file="$package_dir/.config/hypr/hyprland.lua"
hypr_dir="$config_dir/hypr"

mkdir -p -- "$config_dir"

# Do not follow another setup's directory symlink and modify its source files.
# Real Hyprland directories can retain their unrelated personal configuration.
if [[ -L "$hypr_dir" || ( -e "$hypr_dir" && ! -d "$hypr_dir" ) ]]; then
    luna_backup_path "$hypr_dir"
fi

mkdir -p -- "$hypr_dir"

# Replace files, directories, and stale symlinks without discarding their data.
# Never adopt them: Stow adoption would overwrite Luna's repository config.
if [[ -e "$entry_point" || -L "$entry_point" ]]; then
    if [[ ! -L "$entry_point" || ! "$entry_point" -ef "$source_file" ]]; then
        luna_backup_path "$entry_point"
    fi
fi

# Target XDG_CONFIG_HOME directly so custom config locations also work.
# No directory folding: keep other Hyprland files outside Luna's package intact.
stow --dir="$package_dir" --target="$config_dir" --no-folding --restow .config
luna_info "Stowed Luna Hyprland config: $entry_point"
