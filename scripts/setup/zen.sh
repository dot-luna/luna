#!/usr/bin/env bash
# Generate Zen's theme and connect an existing profile; extra arguments are ignored.
set -euo pipefail

script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
source "$(dirname -- "$script_path")/../../lib/common.sh"

setup_dir=$(luna_script_dir "${BASH_SOURCE[0]}")
repo_dir=$(dirname -- "$(dirname -- "$setup_dir")")
luna_resolve_config_dir

# Finish generation before touching installed styles or personal profile files.
styles=$(/usr/bin/lua -E "$repo_dir/apps/zen/scripts/generate-theme.lua")
zen_available=0
if luna_available zen-browser || luna_available zen; then
    zen_available=1
fi

luna_warn 'Back up files you want to keep; Zen setup updates styles and user.js without backups.'
/usr/bin/python3 "$setup_dir/zen-profile.py" "$LUNA_CONFIG_DIR/zen" "$zen_available" <<< "$styles"
luna_success "Installed Zen theme: $LUNA_CONFIG_DIR/zen/generated"
