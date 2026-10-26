#!/usr/bin/env bash
# Reuse an existing AUR helper, or build yay as the regular setup user.
set -euo pipefail

# Load repository-wide helpers, including when reached via a symlink.
script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
source "$(dirname -- "$script_path")/../../lib/common.sh"

# Reuse a working helper instead of rebuilding it.
for helper in yay paru; do
    if luna_available "$helper"; then
        luna_info "AUR helper already available: $helper"
        exit 0
    fi
done

# makepkg must never run as root. Core setup normally supplies these tools.
if (( EUID == 0 )); then
    luna_warn 'AUR helper setup skipped: run it as a normal user.'
    exit 0
fi

for tool in pacman sudo git makepkg; do
    if ! luna_available "$tool"; then
        luna_warn "AUR helper setup skipped: $tool is unavailable."
        exit 0
    fi
done

# Install build prerequisites only when this script is invoked independently.
if ! pacman -Q git base-devel >/dev/null 2>&1; then
    luna_run sudo pacman -Syu --noconfirm --needed -- git base-devel
fi

# Isolate build files and remove only this script's temporary directory on exit.
build_dir=$(mktemp -d -t luna-aur.XXXXXXXX)
trap 'rm -rf -- "$build_dir"' EXIT

luna_info 'Building the yay AUR helper.'
luna_run git clone -- https://aur.archlinux.org/yay.git "$build_dir/yay"
cd -- "$build_dir/yay"
luna_run makepkg -si --noconfirm

if ! luna_available yay; then
    luna_error "AUR setup failed: yay is unavailable after installation."
    exit 1
fi

luna_success "AUR helper ready: yay"
