#!/usr/bin/env bash
# Remove replaced applications after setup while retaining shared packages and user data.
# Extra arguments are ignored; optional removals warn and continue on failure.
set -euo pipefail

script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
source "$(dirname -- "$script_path")/../../lib/common.sh"

setup_dir=$(luna_script_dir "${BASH_SOURCE[0]}")
repo_dir=$(dirname -- "$(dirname -- "$setup_dir")")

for dependency in pacman sudo; do
    if ! luna_available "$dependency"; then
        luna_warn "Application cleanup skipped: $dependency is unavailable."
        exit 0
    fi
done

# Package installation belongs to the manifest. Keep a usable file manager when
# an earlier package step was skipped or failed; plan against the current graph.
if ! pacman -Qq -- nautilus >/dev/null 2>&1; then
    luna_warn 'Application cleanup skipped: Nautilus is not installed; keeping Dolphin.'
    exit 0
fi
if ! pacman -Qq -- dolphin >/dev/null 2>&1; then
    luna_success 'No replaced applications need cleanup.'
    exit 0
fi

luna_warn 'Back up files you want to keep before package removals; Luna does not create backups.'

# Build a bounded removal list. Recursive planning may include Luna requirements
# installed as dependencies, so protect manifest entries and explicit installs.
plan_dolphin_removal() {
    local candidates explicit_packages manifest_packages package
    local -A protected=() selected=([dolphin]=1)

    candidates=$(pacman -Rs --print --print-format '%n' -- dolphin 2>/dev/null) || return 1
    explicit_packages=$(pacman -Qqe 2>/dev/null) || return 1
    manifest_packages=$(/usr/bin/lua -E - "$repo_dir/packages/packages.lua" 2>/dev/null <<'LUA'
local manifest = dofile(arg[1])
assert(type(manifest) == "table" and type(manifest.core) == "table")
local count = 0
for _, group in pairs(manifest) do
    assert(type(group) == "table")
    for _, entry in ipairs(group) do
        assert(type(entry) == "table" and type(entry.name) == "string")
        io.write(entry.name, "\n")
        count = count + 1
    end
end
assert(count > 0)
LUA
    ) || return 1

    while IFS= read -r package; do
        [[ -n "$package" ]] || continue
        [[ "$package" =~ ^[a-zA-Z0-9@_+][a-zA-Z0-9@._+-]*$ ]] || return 1
        protected[$package]=1
    done <<< "$manifest_packages"$'\n'"$explicit_packages"

    while IFS= read -r package; do
        [[ -n "$package" ]] || continue
        [[ "$package" =~ ^[a-zA-Z0-9@_+][a-zA-Z0-9@._+-]*$ ]] || return 1
        if [[ -z "${protected[$package]+set}" && -z "${selected[$package]+set}" ]]; then
            removal+=("$package")
            selected[$package]=1
        fi
    done <<< "$candidates"
}

removal=(dolphin)
if ! plan_dolphin_removal; then
    removal=(dolphin)
    luna_warn 'Could not verify unused dependencies; removing Dolphin only.'
fi

# Plain -R checks remaining reverse dependencies. Never cascade or remove orphans
# globally; a protected package's dependency can make the larger list unsuitable.
if ! luna_run sudo pacman -R --noconfirm -- "${removal[@]}"; then
    if (( ${#removal[@]} <= 1 )); then
        luna_warn 'Dolphin removal failed; Nautilus is installed. Remove Dolphin manually if desired.'
        exit 0
    fi
    luna_warn 'Dependency cleanup failed; retrying Dolphin removal alone.'
    if ! luna_run sudo pacman -R --noconfirm -- dolphin; then
        luna_warn 'Dolphin removal failed; Nautilus is installed. Remove Dolphin manually if desired.'
        exit 0
    fi
fi
luna_success 'Dolphin removed; Nautilus is ready.'
