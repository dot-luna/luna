#!/usr/bin/env bash
# Remove only Luna's verified VM storage, after Compose has removed its containers.
set -euo pipefail
compose_file=$1
storage=$2
desktop_entry=$3
shared=$4
config_dir=$(dirname -- "$compose_file")
compose=(docker compose --project-name luna-macos --file "$compose_file")

# A live desktop session owns cleanup; refuse to race it while deleting its disk.
exec 9>"$config_dir/session.lock"
flock -n 9 || { printf 'Close the macOS desktop before deleting the VM.\n' >&2; exit 1; }
exec 8>"$config_dir/install.lock"
flock -n 8 || { printf 'Finish or cancel macOS installation setup before deleting the VM.\n' >&2; exit 1; }

# Refuse redirected or overlapping directories, including symlinks in their parents.
for path in "$storage" "$config_dir"; do
    [[ $(realpath -ms -- "$path") == "$(realpath -m -- "$path")" ]] || {
        printf 'Refusing to delete a VM directory redirected through symlinks: %s\n' "$path" >&2
        exit 1
    }
done
storage=$(realpath -m -- "$storage")
config_dir=$(realpath -m -- "$config_dir")
shared=$(realpath -m -- "$shared")
for path in "$storage" "$config_dir"; do
    [[ $path != / && $path != "$HOME" && $shared != "$path" && $shared != "$path/"* ]] || exit 1
done
[[ $storage != "$config_dir" && $storage != "$config_dir/"* && $config_dir != "$storage/"* ]] || exit 1

"${compose[@]}" down --timeout 120
remaining=$("${compose[@]}" ps --all -q)
[[ -z $remaining ]] || { printf 'VM containers still exist; storage was not deleted.\n' >&2; exit 1; }

# Stay on the storage filesystem. If cleanup fails, retain configuration for recovery.
if [[ -d $storage ]]; then
    find "$storage" -xdev -mindepth 1 -delete
    rmdir -- "$storage"
fi
rm -f -- "$desktop_entry"
rm -rf --one-file-system -- "$config_dir"
