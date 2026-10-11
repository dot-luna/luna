#!/usr/bin/env bash
# Link Luna's Hyprland Stow package into the user's XDG configuration directory.
set -euo pipefail

script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
source "$(dirname -- "$script_path")/../lib/common.sh"

force=false
for option in "$@"; do
    case "$option" in
        --force)
            force=true
            ;;
        -h|--help)
            printf 'Usage: %s [--force]\n\nStow Luna Hyprland config. --force removes a conflicting Hyprland entry point.\n' "${0##*/}"
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
repo_dir=$(dirname -- "$setup_dir")
config_dir=${XDG_CONFIG_HOME:-"$HOME/.config"}
package_dir="$repo_dir/config/hypr"
entry_point="$config_dir/hypr/hyprland.lua"
source_file="$package_dir/.config/hypr/hyprland.lua"

mkdir -p -- "$config_dir"

# Only replace the conflicting entry point when explicitly requested.
# Never adopt it: Stow adoption would overwrite Luna's repository config.
if [[ -e "$entry_point" || -L "$entry_point" ]]; then
    if [[ ! "$entry_point" -ef "$source_file" && "$force" == true ]]; then
        if [[ -d "$entry_point" && ! -L "$entry_point" ]]; then
            luna_error "Refusing to remove a directory: $entry_point"
            exit 1
        fi
        rm -- "$entry_point"
    fi
fi

# Target XDG_CONFIG_HOME directly so custom config locations also work.
# No directory folding: keep other Hyprland files outside Luna's package intact.
stow --dir="$package_dir" --target="$config_dir" --no-folding --restow .config
luna_info "Stowed Luna Hyprland config: $entry_point"
