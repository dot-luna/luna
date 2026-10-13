#!/usr/bin/env bash
# Read the user's GIPHY credential locally without echoing it or putting it in argv.
set -euo pipefail
read -r -s -p 'GIPHY API key (hidden): ' luna_giphy_key
printf '\n'
if [[ ! $luna_giphy_key =~ ^[A-Za-z0-9_-]+$ ]]; then
    printf 'Invalid key format.\n' >&2
    exit 1
fi
umask 077
luna_insert_dir="${XDG_CONFIG_HOME:-$HOME/.config}/luna"
mkdir -p "$luna_insert_dir"
luna_key_temp=$(mktemp "$luna_insert_dir/.giphy-key.XXXXXX")
trap 'rm -f "$luna_key_temp"' EXIT
printf '%s\n' "$luna_giphy_key" > "$luna_key_temp"
mv -f "$luna_key_temp" "$luna_insert_dir/giphy.key"
printf 'Saved. Reopen GIPHY in Luna Menu.\n'
