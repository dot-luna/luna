#!/usr/bin/env bash
# Link each Luna source directory into ~/.local/src, replacing conflicting paths.
set -euo pipefail

script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
source "$(dirname -- "$script_path")/../../lib/common.sh"

if ! luna_available stow; then
    luna_error 'GNU Stow is missing; install core dependencies first.'
    exit 1
fi

setup_dir=$(luna_script_dir "${BASH_SOURCE[0]}")
repo_dir=$(dirname -- "$(dirname -- "$setup_dir")")
source_target="$HOME/.local/src"

mkdir -p -- "$source_target"

# A custom install location or parent symlink can overlap these destinations.
# Validate every target first so a later conflict cannot delete the checkout.
resolved_target=$(readlink -f -- "$source_target")
if [[ "$resolved_target" == "$repo_dir" || "$resolved_target" == "$repo_dir/"* ]]; then
    luna_error "Source links would modify the checkout: $source_target. Choose a different install location."
    exit 1
fi

for source_package in "$repo_dir/src"/*; do
    [[ -d "$source_package" ]] || continue
    target_path="$source_target/${source_package##*/}"
    [[ -d "$target_path" && ! -L "$target_path" ]] || continue
    target_directory="$resolved_target/${source_package##*/}"

    if [[ "$repo_dir" == "$target_directory" || "$repo_dir" == "$target_directory/"* ]]; then
        luna_error "Source link would replace the checkout: $target_path. Choose a different install location."
        exit 1
    fi
done

# Keep whole directory links so relative paths still resolve into the checkout.
# Remove conflicts without following their final symlink or merging directories.
for source_package in "$repo_dir/src"/*; do
    [[ -d "$source_package" ]] || continue
    target_path="$source_target/${source_package##*/}"

    if [[ -e "$target_path" || -L "$target_path" ]]; then
        if [[ ! -L "$target_path" || ! "$target_path" -ef "$source_package" ]]; then
            rm -rf -- "$target_path"
        fi
    fi
done

luna_run stow --dir="$repo_dir" --target="$source_target" --restow src
luna_success "Stowed Luna source directories: $source_target"
