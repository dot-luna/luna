#!/usr/bin/env bash
# Select GNOME Keyring and prepare password-login unlocking; extra arguments are ignored.
set -euo pipefail

script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
setup_dir=$(dirname -- "$script_path")
source "$setup_dir/../../lib/common.sh"

if ! luna_available gnome-keyring-daemon; then
    luna_warn 'Keyring setup skipped: install gnome-keyring with the core packages first.'
    exit 0
fi

config_home=${XDG_CONFIG_HOME:-"$HOME/.config"}
data_home=${XDG_DATA_HOME:-"$HOME/.local/share"}

/usr/bin/python3 "$setup_dir/keyring-config.py" configure "$config_home" "$data_home"

# Arch enables this socket globally. Also enable it for this user so a previous
# per-user disable does not prevent activation; existing masks remain respected.
if luna_available systemctl; then
    if ! luna_run systemctl --user enable gnome-keyring-daemon.socket; then
        luna_warn 'Could not enable the keyring socket; Hyprland startup will still initialize GNOME Keyring.'
    fi
else
    luna_warn 'systemctl is unavailable; Hyprland startup will initialize GNOME Keyring.'
fi

luna_success 'GNOME Keyring configured. Log out and sign in with your password to unlock the login keyring.'
