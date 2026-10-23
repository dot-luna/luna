#!/usr/bin/env bash
# Replace and apply the bundled default theme after setup.
set -euo pipefail

script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
source "$(dirname -- "$script_path")/../../lib/common.sh"

setup_dir=$(luna_script_dir "${BASH_SOURCE[0]}")
repo_dir=$(dirname -- "$(dirname -- "$setup_dir")")

# Treat empty XDG settings like unset ones, keeping CLI storage in the user's home.
export XDG_DATA_HOME=${XDG_DATA_HOME:-"$HOME/.local/share"}
export XDG_CONFIG_HOME=${XDG_CONFIG_HOME:-"$HOME/.config"}
if [[ "$XDG_DATA_HOME" != /* || "$XDG_CONFIG_HOME" != /* ]]; then
    luna_warn 'Theme setup skipped: XDG data and config paths must be absolute.'
    exit 0
fi

# Use this checkout's CLI and bundled files even if another Luna is on PATH.
luna=(/usr/bin/lua -E "$repo_dir/src/luna-cli/main.lua")
luna_run "${luna[@]}" theme install "$repo_dir/themes/bundled/tokyo-night" --force
luna_run "${luna[@]}" theme set tokyo-night --force
