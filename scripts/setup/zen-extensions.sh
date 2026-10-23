#!/usr/bin/env bash
# Install removable add-ons for all native Zen profiles; extra arguments are ignored.
set -euo pipefail

script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
setup_dir=$(dirname -- "$script_path")
source "$setup_dir/../../lib/common.sh"

repo_dir=$(dirname -- "$(dirname -- "$setup_dir")")
/usr/bin/python3 "$setup_dir/zen-extensions.py" configure \
    "${ZEN_INSTALL_DIR:-/opt/zen-browser-bin}" "$repo_dir/apps/zen/extensions.json"
