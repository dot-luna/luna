#!/usr/bin/env bash
# Apply the installed desktop config and restart Luna's wallpaper in the active session.
# Session failures warn and skip; a later login still uses the installed configuration.
set -euo pipefail

script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
setup_dir=${script_path%/*}
repo_dir=${setup_dir%/*/*}
source "$repo_dir/lib/common.sh"

if [[ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]]; then
    luna_info 'No active Hyprland session; configuration reload skipped.'
    exit 0
fi

if luna_available hyprctl; then
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
else
    luna_warn 'Hyprland configuration reload skipped: hyprctl is unavailable.'
fi

# Hyprland reload does not rerun autostart. Replace only the wallpaper
# instances through this checkout's CLI so the newly installed TOML is loaded now.
if [[ -z "${WAYLAND_DISPLAY:-}" ]] || ! luna_available qs; then
    luna_info 'Wallpaper restart skipped; it will start at the next desktop login.'
    exit 0
fi
if [[ ! -f "$repo_dir/src/luna-cli/main.lua" ]]; then
    luna_warn 'Wallpaper restart skipped: the Luna command source is missing.'
    exit 0
fi

luna_info 'Starting the installed wallpaper configuration.'
if luna_run /usr/bin/lua -E "$repo_dir/src/luna-cli/main.lua" wallpaper restart; then
    luna_success 'Wallpaper renderer restarted.'
else
    luna_warn 'Wallpaper could not be restarted. Run luna wallpaper restart after fixing the reported error.'
fi
