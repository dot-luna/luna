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

# Both cleanup passes protect packages still declared by Luna's manifest.
manifest_packages() {
    /usr/bin/lua -E - "$repo_dir/packages/packages.lua" 2>/dev/null <<'LUA'
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
}

# Build a bounded removal list. Recursive planning may include Luna requirements
# installed as dependencies, so protect manifest entries and explicit installs.
plan_dolphin_removal() {
    local candidates explicit_packages declared_packages package

    # Wallet replacement has its own readiness gate, even when Dolphin's
    # recursive plan happens to include one of these dependency packages.
    local -A protected=([kwallet]=1 [kwallet-pam]=1 [kwalletmanager]=1) selected=([dolphin]=1)

    candidates=$(pacman -Rs --print --print-format '%n' -- dolphin 2>/dev/null) || return 1
    explicit_packages=$(pacman -Qqe 2>/dev/null) || return 1
    declared_packages=$(manifest_packages) || return 1

    while IFS= read -r package; do
        [[ -n "$package" ]] || continue
        [[ "$package" =~ ^[a-zA-Z0-9@_+][a-zA-Z0-9@._+-]*$ ]] || return 1
        protected[$package]=1
    done <<< "$declared_packages"$'\n'"$explicit_packages"

    while IFS= read -r package; do
        [[ -n "$package" ]] || continue
        [[ "$package" =~ ^[a-zA-Z0-9@_+][a-zA-Z0-9@._+-]*$ ]] || return 1
        if [[ -z "${protected[$package]+set}" && -z "${selected[$package]+set}" ]]; then
            removal+=("$package")
            selected[$package]=1
        fi
    done <<< "$candidates"
}

cleanup_dolphin() {
    # Each replacement is independent: a skipped package step must leave that
    # application's previous provider available without blocking other cleanup.
    if ! pacman -Qq -- nautilus >/dev/null 2>&1; then
        luna_warn 'Nautilus is not installed; keeping Dolphin.'
        return
    fi
    if ! pacman -Qq -- dolphin >/dev/null 2>&1; then
        return
    fi

    luna_warn 'Back up files you want to keep before package removals; Luna does not create backups.'
    local -a removal=(dolphin)
    if ! plan_dolphin_removal; then
        removal=(dolphin)
        luna_warn 'Could not verify unused dependencies; removing Dolphin only.'
    fi

    # Plain -R checks remaining reverse dependencies. Never cascade or remove
    # orphans globally; a protected dependency can make the larger list unsuitable.
    if ! luna_run sudo pacman -R --noconfirm -- "${removal[@]}"; then
        if (( ${#removal[@]} <= 1 )); then
            luna_warn 'Dolphin removal failed; Nautilus is installed. Remove Dolphin manually if desired.'
            return
        fi
        luna_warn 'Dependency cleanup failed; retrying Dolphin removal alone.'
        if ! luna_run sudo pacman -R --noconfirm -- dolphin; then
            luna_warn 'Dolphin removal failed; Nautilus is installed. Remove Dolphin manually if desired.'
            return
        fi
    fi
    luna_success 'Dolphin removed; Nautilus is ready.'
}

cleanup_wallets() {
    if ! pacman -Qq -- gnome-keyring >/dev/null 2>&1; then
        luna_warn 'GNOME Keyring is not installed; keeping KDE Wallet packages.'
        return
    fi

    local package declared_packages
    local -a installed=() removal=()
    local -A protected=()
    for package in kwallet kwallet-pam kwalletmanager; do
        if pacman -Qq -- "$package" >/dev/null 2>&1; then
            installed+=("$package")
        fi
    done
    (( ${#installed[@]} > 0 )) || return 0
    if ! declared_packages=$(manifest_packages); then
        luna_warn 'Could not verify Luna package requirements; keeping KDE Wallet packages.'
        return
    fi
    while IFS= read -r package; do
        [[ -n "$package" ]] || continue
        protected[$package]=1
    done <<< "$declared_packages"
    for package in "${installed[@]}"; do
        if [[ -n "${protected[$package]+set}" ]]; then
            luna_warn "Keeping $package: it is declared in Luna's package manifest."
        else
            removal+=("$package")
        fi
    done
    (( ${#removal[@]} > 0 )) || return 0

    # Remove only the named replacements. Pacman retains shared dependencies and
    # rejects any remaining reverse dependency; personal wallets are never touched.
    luna_warn 'Back up files you want to keep before package removals; Luna does not create backups.'
    if ! luna_run sudo pacman -R --noconfirm -- "${removal[@]}"; then
        luna_warn "KDE Wallet removal failed; keeping the packages. Check pacman's error before retrying."
        return
    fi
    luna_success 'KDE Wallet packages removed; GNOME Keyring is installed.'
}

cleanup_dolphin
cleanup_wallets
