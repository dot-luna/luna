#!/usr/bin/env bash
# Enable Docker when systemd is available; service setup must not block the desktop.
set -euo pipefail

script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
source "$(dirname -- "$script_path")/../../lib/common.sh"

if [[ $# -gt 0 ]]; then
    if [[ $# -eq 1 && ( "$1" == -h || "$1" == --help ) ]]; then
        printf 'Usage: bash scripts/setup/services.sh\n\nEnable and start Docker with systemd when possible.\nService failures are reported as warnings so desktop setup can continue.\n'
        exit 0
    fi
    luna_error "Unknown option: $1"
    exit 2
fi

# Query the manager instead of assuming systemctl means systemd is running.
# This also permits setup in chroots and containers without a system manager.
if ! luna_available systemctl || ! systemctl show --property=Version >/dev/null 2>&1; then
    luna_warn 'Docker was not enabled: a running systemd manager is unavailable.'
    exit 0
fi

privilege=()
if (( EUID != 0 )); then
    if ! luna_available sudo; then
        luna_warn 'Docker was not enabled: sudo is unavailable.'
        exit 0
    fi
    privilege=(sudo)
fi

luna_info 'Enabling and starting Docker.'
if ! luna_run "${privilege[@]}" systemctl enable --now docker.service; then
    luna_warn 'Docker could not be enabled or started. Setup will continue.'
    exit 0
fi

# A successful enable request does not guarantee the daemon remained healthy.
if systemctl is-enabled --quiet docker.service >/dev/null 2>&1 &&
    systemctl is-active --quiet docker.service >/dev/null 2>&1; then
    luna_success 'Docker is enabled and running. Use sudo docker for daemon commands.'
else
    luna_warn 'Docker is not both enabled and running. Setup will continue.'
fi
