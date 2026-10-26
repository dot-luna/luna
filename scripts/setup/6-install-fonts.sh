#!/usr/bin/env bash
# Install font packages through the shared dependency installer; extra arguments are ignored.
set -euo pipefail

# Resolve the shared installer even when this entry point is a symlink.
script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
exec /usr/bin/lua -E "$(dirname -- "$script_path")/install-deps.lua" fonts
