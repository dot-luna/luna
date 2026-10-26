#!/usr/bin/env bash
# Link each Luna source directory into ~/.local/src, replacing conflicting paths.
set -euo pipefail

script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
setup_dir=${script_path%/*}
repo_dir=${setup_dir%/*/*}
source "$repo_dir/lib/common.sh"

if [[ ! -d "$repo_dir/src" ]]; then
    luna_error "Luna source directory is missing: $repo_dir/src"
    exit 1
fi

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

    if [[ -L "$target_path" && "$target_path" -ef "$source_package" ]]; then
        continue
    fi
    rm -rf -- "$target_path"
    ln -srT -- "$source_package" "$target_path"
done

luna_success "Linked Luna source directories: $source_target"
