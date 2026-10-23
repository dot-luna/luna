#!/usr/bin/env bash
# Install Luna's static Starship configuration; extra arguments are ignored.
set -euo pipefail

script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
source "$(dirname -- "$script_path")/../../lib/common.sh"

setup_dir=$(luna_script_dir "${BASH_SOURCE[0]}")
repo_dir=$(dirname -- "$(dirname -- "$setup_dir")")
luna_resolve_config_dir
starship_dir="$LUNA_CONFIG_DIR/starship"

# Never follow a directory alias into another configuration or the checkout.
if [[ -L "$starship_dir" ]]; then
    luna_error "Starship configuration destination must not be a symlink: $starship_dir"
    exit 1
fi
resolved_starship=$(realpath -m -- "$starship_dir")
if [[ "$resolved_starship" == "$repo_dir" || "$resolved_starship" == "$repo_dir/"* \
    || "$repo_dir" == "$resolved_starship/"* ]]; then
    luna_error 'Starship source and installed configuration must be separate paths.'
    exit 1
fi
if [[ -d "$starship_dir/starship.toml" && ! -L "$starship_dir/starship.toml" ]]; then
    luna_error "Expected a configuration file, found a directory: $starship_dir/starship.toml"
    exit 1
fi

luna_warn 'Back up files you want to keep; Starship setup replaces its config without backups.'
mkdir -p -- "$LUNA_CONFIG_DIR"
staging_dir=$(mktemp -d "$LUNA_CONFIG_DIR/.starship-XXXXXX")
trap 'rm -rf -- "$staging_dir"' EXIT

# Stage a complete copy before replacement; replace file symlinks themselves.
cp -- "$repo_dir/apps/starship/starship.toml" "$staging_dir/starship.toml"
mkdir -p -- "$starship_dir"
mv -fT -- "$staging_dir/starship.toml" "$starship_dir/starship.toml"
luna_success "Installed Starship configuration: $starship_dir"
