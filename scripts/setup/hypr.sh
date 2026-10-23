#!/usr/bin/env bash
# Install Luna's Hyprland modules and connect a personal Lua entry point.
# Extra arguments are ignored; setup never reloads the running compositor.
set -euo pipefail

script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
source "$(dirname -- "$script_path")/../../lib/common.sh"

setup_dir=$(luna_script_dir "${BASH_SOURCE[0]}")
repo_dir=$(dirname -- "$(dirname -- "$setup_dir")")
luna_resolve_config_dir
active_config=${HYPRLAND_CONFIG:-"$XDG_CONFIG_HOME/hypr/hyprland.lua"}
if [[ "$active_config" != /* ]]; then
    luna_error 'HYPRLAND_CONFIG must be an absolute path.'
    exit 1
fi

# Stage outside the destination so a failed generator or migration leaves both
# the installed modules and the personal entry point unchanged.
staging_dir=$(mktemp -d)
trap 'rm -rf -- "$staging_dir"' EXIT
for name in hyprland animations bindings monitors theme workspaces; do
    cp -- "$repo_dir/apps/hypr/$name.lua" "$staging_dir/$name.lua"
done
if ! /usr/bin/lua -E "$repo_dir/apps/hypr/scripts/generate-config.lua" > "$staging_dir/paths.lua"; then
    luna_error 'Hyprland config generation failed; existing configurations were kept.'
    exit 1
fi

luna_warn 'Back up files you want to keep; Hyprland setup updates Luna configs and its include without backups.'
/usr/bin/python3 "$setup_dir/hypr-config.py" "$staging_dir" "$LUNA_CONFIG_DIR/hypr" "$active_config"
luna_success "Installed Hyprland configuration: $LUNA_CONFIG_DIR/hypr"
