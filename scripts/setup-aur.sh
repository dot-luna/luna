#!/usr/bin/env bash
# Reuse an existing AUR helper, or build yay as the regular setup user.
set -euo pipefail

# Load repository-wide helpers, including when reached via a symlink.
script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
source "$(dirname -- "$script_path")/../lib/common.sh"

for option in "$@"; do
    case "$option" in
        -h|--help)
            printf 'Usage: %s\n\nReuse yay/paru or build yay from the AUR.\n' "${0##*/}"
            exit 0
            ;;
        *)
            luna_error "Unknown option: $option"
            exit 2
            ;;
    esac
done

# Existing helpers need no rebuild; package --force does not replace the helper.
for helper in yay paru; do
    if luna_available "$helper"; then
        luna_info "AUR helper already available: $helper"
        exit 0
    fi
done

# makepkg must never run as root. Core setup normally supplies these tools.
if (( EUID == 0 )); then
    luna_error "Run AUR setup as a normal user with sudo access."
    exit 1
fi

for tool in pacman sudo git makepkg; do
    if ! luna_available "$tool"; then
        luna_error "Missing $tool; install core dependencies first."
        exit 1
    fi
done

# Install build prerequisites only when this script is invoked independently.
if ! pacman -Q git base-devel >/dev/null 2>&1; then
    sudo pacman -Syu --needed -- git base-devel
fi

# Isolate build files and remove only this script's temporary directory on exit.
build_dir=$(mktemp -d -t luna-aur.XXXXXXXX)
trap 'rm -rf -- "$build_dir"' EXIT

git clone -- https://aur.archlinux.org/yay.git "$build_dir/yay"
cd -- "$build_dir/yay"
makepkg -si

if ! luna_available yay; then
    luna_error "AUR setup failed: yay is unavailable after installation."
    exit 1
fi

luna_info "AUR helper ready: yay"
