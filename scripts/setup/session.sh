#!/usr/bin/env bash
# Apply Hyprland configuration after setup without blocking installation on IPC.
set -euo pipefail

script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
source "$(dirname -- "$script_path")/../../lib/common.sh"

if [[ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]]; then
    luna_info 'No active Hyprland session; configuration reload skipped.'
    exit 0
fi

if ! luna_available hyprctl; then
    luna_warn 'Hyprland configuration reload skipped: hyprctl is unavailable.'
    exit 0
fi

# Coreutils normally provides timeout; bound a stalled compositor IPC request.
reload=(hyprctl reload)
if luna_available timeout; then
    reload=(timeout --kill-after=2s 10s "${reload[@]}")
fi

luna_info 'Reloading the active Hyprland configuration.'
if luna_run "${reload[@]}"; then
    luna_success 'Hyprland configuration reloaded.'
else
    luna_warn 'Hyprland configuration could not be reloaded. Log out and back in to apply it.'
fi
