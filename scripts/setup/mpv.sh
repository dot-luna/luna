#!/usr/bin/env bash
# Install mpv defaults and connect its personal configuration. Extra arguments are ignored.
set -euo pipefail

script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
source "$(dirname -- "$script_path")/../../lib/common.sh"

setup_dir=$(luna_script_dir "${BASH_SOURCE[0]}")
repo_dir=$(dirname -- "$(dirname -- "$setup_dir")")
luna_resolve_config_dir

luna_warn 'Back up files you want to keep; mpv setup updates Luna configs and personal entry points without backups.'
/usr/bin/python3 "$setup_dir/mpv-config.py" "$repo_dir/apps/mpv" "$LUNA_CONFIG_DIR/mpv"
luna_success "Installed mpv configuration: $LUNA_CONFIG_DIR/mpv"
