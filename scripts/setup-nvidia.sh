#!/usr/bin/env bash
# Install NVIDIA's open driver for a supported GPU on Arch's standard linux kernel.
# Run explicitly for NVIDIA hardware; do not add this to every machine's core deps.
set -euo pipefail

script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
source "$(dirname -- "$script_path")/../lib/common.sh"

if [[ $# -gt 0 ]]; then
    printf 'Usage: bash scripts/setup-nvidia.sh\n\nInstall nvidia-open and nvidia-utils for the standard linux kernel, then rebuild initramfs.\nRequires a Turing or newer NVIDIA GPU. Reboot afterward.\n'
    [[ "$1" == -h || "$1" == --help ]]
    exit
fi

if [[ $EUID -ne 0 ]]; then
    # A running polkit authentication agent presents the administrator password dialog.
    exec pkexec /usr/bin/bash "$script_path"
fi

pacman -Q linux >/dev/null || {
    luna_error 'This script requires the standard Arch linux kernel. Other kernels need a matching NVIDIA package.'
    exit 1
}

# Keep the kernel and driver in the same repository transaction. Do not unload the
# active Nouveau module: it may currently drive a display and must change at reboot.
pacman -S --needed --noconfirm linux nvidia-open nvidia-utils

# Persist Wayland modesetting and prevent Nouveau from claiming the GPU next boot.
install -d /etc/modprobe.d
cat > /etc/modprobe.d/luna-nvidia.conf <<'EOF'
blacklist nouveau
options nvidia_drm modeset=1 fbdev=1
EOF

mkinitcpio -P
luna_info 'NVIDIA driver installed. Reboot before testing the external monitor.'
