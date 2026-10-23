#!/usr/bin/env bash
# Configure Zen's theme, font defaults, and add-ons; extra arguments are ignored.
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

luna_warn 'Back up files you want to keep; Zen setup updates profile configuration without backups.'
/usr/bin/python3 "$setup_dir/zen-profile.py" "$LUNA_CONFIG_DIR/zen" "$zen_available" <<< "$styles"
if ! bash "$setup_dir/zen-extensions.sh"; then
    luna_warn 'Zen extension setup failed; rerun setup to retry.'
fi
luna_success "Installed Zen configuration: $LUNA_CONFIG_DIR/zen"
