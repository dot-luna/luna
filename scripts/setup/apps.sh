#!/usr/bin/env bash
# Install Luna's application configs and connect their personal entry points.
# Extra arguments are ignored.
set -euo pipefail

script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
source "$(dirname -- "$script_path")/../../lib/common.sh"

setup_dir=$(luna_script_dir "${BASH_SOURCE[0]}")
repo_dir=$(dirname -- "$(dirname -- "$setup_dir")")
luna_resolve_config_dir
kitty_dir="$LUNA_CONFIG_DIR/kitty"
active_kitty_dir=${KITTY_CONFIG_DIRECTORY:-"$XDG_CONFIG_HOME/kitty"}
if [[ "$active_kitty_dir" != /* ]]; then
    luna_error 'KITTY_CONFIG_DIRECTORY must be an absolute path.'
    exit 1
fi

# Never follow an app-directory link into a user's active configuration.
if [[ -L "$kitty_dir" ]]; then
    luna_error "Kitty configuration destination must not be a symlink: $kitty_dir"
    exit 1
fi

resolved_kitty=$(realpath -m -- "$kitty_dir")
active_kitty=$(realpath -m -- "$active_kitty_dir")
for protected_dir in "$repo_dir" "$active_kitty"; do
    if [[ "$resolved_kitty" == "$protected_dir" || "$resolved_kitty" == "$protected_dir/"* || "$protected_dir" == "$resolved_kitty/"* ]]; then
        luna_error "Kitty configuration destination overlaps the checkout or active Kitty config: $kitty_dir"
        exit 1
    fi
done

# A conflicting directory cannot be replaced by a configuration file.
for name in kitty.conf theme.conf; do
    if [[ -d "$kitty_dir/$name" && ! -L "$kitty_dir/$name" ]]; then
        luna_error "Expected a configuration file, found a directory: $kitty_dir/$name"
        exit 1
    fi
done

luna_warn 'Back up files you want to keep; app setup replaces Luna configs and updates the Kitty include without backups.'
mkdir -p -- "$LUNA_CONFIG_DIR"
staging_dir=$(mktemp -d "$LUNA_CONFIG_DIR/.kitty-XXXXXX")
trap 'rm -rf -- "$staging_dir"' EXIT

# Complete generation before replacing either installed file. Keep generated
# output separate from progress logs and replace file symlinks without following.
cp -- "$repo_dir/apps/kitty/kitty.conf" "$staging_dir/kitty.conf"
if ! /usr/bin/lua -E "$repo_dir/apps/kitty/scripts/generate-theme.lua" > "$staging_dir/theme.conf"; then
    luna_error 'Kitty theme generation failed; existing configuration files were kept.'
    exit 1
fi

mkdir -p -- "$kitty_dir"
mv -fT -- "$staging_dir/kitty.conf" "$kitty_dir/kitty.conf"
mv -fT -- "$staging_dir/theme.conf" "$kitty_dir/theme.conf"
luna_success "Installed Kitty configuration: $kitty_dir"

# Include only a fully installed configuration. Personal settings follow it and
# keep their existing order and precedence; repeated setup adds no duplicates.
/usr/bin/python3 "$setup_dir/kitty-include.py" "$active_kitty_dir/kitty.conf" "$kitty_dir/kitty.conf"
luna_success "Configured Kitty include: $active_kitty_dir/kitty.conf"

bash "$setup_dir/starship.sh"
bash "$setup_dir/zsh.sh"
bash "$setup_dir/zen.sh"
bash "$setup_dir/hypr.sh"
