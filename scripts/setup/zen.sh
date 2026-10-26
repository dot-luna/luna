#!/usr/bin/env bash
# Compatibility entry point; shared app setup owns copying, building and connecting.
set -euo pipefail

script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
export LUNA_SETUP_APP=zen
exec /usr/bin/lua -E "$(dirname -- "$script_path")/10-setup-app-configs.lua"
