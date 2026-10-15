#!/usr/bin/env bash
# Install NVIDIA's open driver for a supported GPU on Arch's standard linux kernel.
# Offered last by setup.sh or run directly; installation always requires consent.
set -euo pipefail

script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
source "$(dirname -- "$script_path")/../../lib/common.sh"

if [[ $# -gt 0 ]]; then
    printf 'Usage: bash scripts/setup/nvidia.sh\n\nOptionally install nvidia-open, nvidia-utils (including nvidia-smi), and nvidia-settings,\nthen rebuild initramfs. Requires the standard Arch linux kernel and a Turing or newer\nNVIDIA GPU. Prompts before changing the system; reboot after installation.\n'
    if [[ $# -eq 1 && ( "$1" == -h || "$1" == --help ) ]]; then
        exit 0
    fi
    exit 1
fi

luna_info 'Optional NVIDIA setup: nvidia-open, nvidia-smi, and nvidia-settings.'
luna_info 'Supported hardware: Turing or newer NVIDIA GPUs using the standard Arch linux kernel.'
luna_info 'Installation updates system packages and rebuilds initramfs. A reboot is required.'

# Decline before checking or requesting privileges, including when input reaches EOF.
if ! luna_confirm 'Install NVIDIA drivers and tools now?' 'n'; then
    luna_info 'NVIDIA setup skipped.'
    exit 0
fi

pacman -Q linux >/dev/null || {
    luna_error 'This script requires the standard Arch linux kernel. Other kernels need a matching NVIDIA package.'
    exit 1
}

# Terminal sudo works during bootstrap before a graphical polkit agent is running.
privilege=()
if [[ $EUID -ne 0 ]]; then
    if ! luna_available sudo; then
        luna_error 'NVIDIA setup requires sudo. Install it or run this script as root.'
        exit 1
    fi
    privilege=(sudo)
fi

# Keep the kernel and driver in the same repository transaction. Do not unload the
# active Nouveau module: it may currently drive a display and must change at reboot.
"${privilege[@]}" pacman -Syu --needed -- linux nvidia-open nvidia-utils nvidia-settings

# Persist Wayland modesetting and prevent Nouveau from claiming the GPU next boot.
"${privilege[@]}" install -d /etc/modprobe.d
"${privilege[@]}" tee /etc/modprobe.d/luna-nvidia.conf >/dev/null <<'EOF'
blacklist nouveau
options nvidia_drm modeset=1 fbdev=1
EOF

"${privilege[@]}" mkinitcpio -P
luna_info 'NVIDIA drivers and tools installed. Reboot to load the driver, then check nvidia-smi.'
