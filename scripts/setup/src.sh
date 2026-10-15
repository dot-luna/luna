#!/usr/bin/env bash
# Link each Luna source directory into ~/.local/src, backing up existing paths.
set -euo pipefail

script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
source "$(dirname -- "$script_path")/../../lib/common.sh"

for option in "$@"; do
    case "$option" in
        --force)
            # Setup forwards this flag; source conflicts are always backed up.
            ;;
        -h|--help)
            printf 'Usage: %s [--force]\n\nStow source directories into ~/.local/src.\nExisting conflicting paths are moved to adjacent .luna-backup paths before replacement.\n--force is accepted for compatibility; backups are always made.\n' "${0##*/}"
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
source_target="$HOME/.local/src"

mkdir -p -- "$source_target"

# Keep whole directory links so relative paths still resolve into the checkout.
# Move existing directories aside instead of letting Stow merge their contents.
for source_package in "$repo_dir/src"/*; do
    [[ -d "$source_package" ]] || continue
    target_path="$source_target/${source_package##*/}"

    if [[ -e "$target_path" || -L "$target_path" ]]; then
        if [[ ! -L "$target_path" || ! "$target_path" -ef "$source_package" ]]; then
            luna_backup_path "$target_path"
        fi
    fi
done

stow --dir="$repo_dir" --target="$source_target" --restow src
luna_info "Stowed Luna source directories: $source_target"
