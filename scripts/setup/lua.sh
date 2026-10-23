#!/usr/bin/env bash
# Bootstrap the system Lua runtime before Luna's Lua setup can run.
# Invoke directly; package confirmations are automatic while sudo may authenticate.
set -euo pipefail

# Load repository-wide helpers, including when reached via a symlink.
script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
source "$(dirname -- "$script_path")/../../lib/common.sh"

if ! luna_available pacman; then
    luna_error "This script requires Arch Linux with pacman."
    exit 1
fi

# Check the system interpreter, independently of mise or shell Lua settings.
# -E ignores Lua environment overrides; loading argparse proves it is usable.
lua_ready() {
    [[ -x /usr/bin/lua ]] && /usr/bin/lua -E -e 'require("argparse")' >/dev/null 2>&1
}

if lua_ready; then
    luna_info "Lua and argparse are already available; skipping setup."
    exit 0
fi

# Root can bootstrap without sudo; normal users need it for installation only.
installer=(pacman)

if (( EUID != 0 )); then
    if ! luna_available sudo; then
        luna_error "sudo is missing. Run this script as root to bootstrap Lua."
        exit 1
    fi

    installer=(sudo pacman)
fi

# Refresh packages with a full upgrade, keeping Arch dependencies consistent.
# Keep current versions without reinstalling them.
luna_info "Setting up Lua and argparse (includes a system upgrade)."
luna_run "${installer[@]}" -Syu --noconfirm --needed -- lua lua-argparse

# Verify the runtime rather than assuming a successful transaction is enough.
if ! lua_ready; then
    luna_error "Setup failed: system Lua cannot load argparse."
    exit 1
fi

luna_success "Lua and argparse are ready."
