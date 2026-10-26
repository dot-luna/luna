#!/usr/bin/env bash
# Optional app actions belong here, after config deployment. Extra args are ignored.
set -euo pipefail

script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
source "$(dirname -- "$script_path")/../../lib/common.sh"
setup_dir=$(luna_script_dir "${BASH_SOURCE[0]}")
luna_resolve_config_dir

zen_available=0
if luna_available zen-browser || luna_available zen; then
    zen_available=1
fi
if ! /usr/bin/python3 -B "$setup_dir/zen-extras.py" "$LUNA_CONFIG_DIR/zen" "$zen_available"; then
    luna_warn 'Zen mod setup failed; rerun app extras to retry.'
fi
if ! bash "$setup_dir/zen-extensions.sh"; then
    luna_warn 'Zen extension setup failed; rerun app extras to retry.'
fi
