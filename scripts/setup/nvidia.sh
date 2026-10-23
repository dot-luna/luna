#!/usr/bin/env bash
# Install NVIDIA's open driver for a supported GPU on Arch's standard linux kernel.
# Run directly when needed; installation always requires consent.
set -euo pipefail

script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
source "$(dirname -- "$script_path")/../../lib/common.sh"

luna_info 'Optional NVIDIA setup: nvidia-open, nvidia-smi, and nvidia-settings.'
luna_info 'Supported hardware: Turing or newer NVIDIA GPUs using the standard Arch linux kernel.'
luna_warn 'Installation updates system packages and rebuilds initramfs. A reboot is required.'

# Decline before checking or requesting privileges, including when input reaches EOF.
if ! luna_confirm 'Install NVIDIA drivers and tools now?' 'n'; then
    luna_info 'NVIDIA setup skipped.'
    exit 0
fi

pacman -Q linux >/dev/null 2>&1 || {
    luna_warn 'NVIDIA setup skipped: the standard Arch linux kernel is required.'
    exit 0
}

# Terminal sudo works during bootstrap before a graphical polkit agent is running.
privilege=()
if [[ $EUID -ne 0 ]]; then
    if ! luna_available sudo; then
        luna_warn 'NVIDIA setup skipped: sudo is unavailable.'
        exit 0
    fi
    privilege=(sudo)
fi

# Keep the kernel and driver in the same repository transaction. Do not unload the
# active Nouveau module: it may currently drive a display and must change at reboot.
luna_run "${privilege[@]}" pacman -Syu --noconfirm --needed -- linux nvidia-open nvidia-utils nvidia-settings

# Persist Wayland modesetting and prevent Nouveau from claiming the GPU next boot.
luna_run "${privilege[@]}" install -d /etc/modprobe.d
"${privilege[@]}" tee /etc/modprobe.d/luna-nvidia.conf >/dev/null <<'EOF'
blacklist nouveau
options nvidia_drm modeset=1 fbdev=1
EOF

luna_run "${privilege[@]}" mkinitcpio -P
luna_success 'NVIDIA drivers and tools installed. Reboot to load the driver, then check nvidia-smi.'
