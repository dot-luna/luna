#!/usr/bin/env bash
# Expose this checkout's CLI and persist command lookup for the user's shell.
set -euo pipefail

script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
source "$(dirname -- "$script_path")/../../lib/common.sh"

for option in "$@"; do
    case "$option" in
        --force)
            # Setup forwards this flag; command conflicts are always backed up.
            ;;
        -h|--help)
            printf 'Usage: %s [--force]\n\nLink Luna into ~/.local/bin and configure PATH for Bash, Zsh, or fish.\nExisting conflicts and changed shell startup files receive adjacent .luna-backup backups.\n--force is accepted for compatibility; backups are always made.\n' "${0##*/}"
            exit 0
            ;;
        *)
            luna_error "Unknown option: $option"
            exit 2
            ;;
    esac
done

setup_dir=$(luna_script_dir "${BASH_SOURCE[0]}")
repo_dir=$(dirname -- "$(dirname -- "$setup_dir")")
command_source="$repo_dir/bin/luna"
command_target="$HOME/.local/bin/luna"

if [[ ! -x "$command_source" ]]; then
    luna_error "Luna launcher is missing or not executable: $command_source"
    exit 1
fi

mkdir -p -- "${command_target%/*}"
if [[ ! -L "$command_target" || ! "$command_target" -ef "$command_source" ]]; then
    luna_backup_path "$command_target"
    ln -s -- "$command_source" "$command_target"
fi
luna_success "Linked Luna command: $command_target"

# Configure the login shell rather than the Bash interpreter running this step.
# ZDOTDIR and XDG_CONFIG_HOME may place personal shell files outside HOME.
shell_path=${SHELL:-}
shell_name=${shell_path##*/}
case "$shell_name" in
    bash)
        shell_config="$HOME/.bashrc"
        ;;
    zsh)
        shell_config="${ZDOTDIR:-$HOME}/.zshrc"
        ;;
    fish)
        shell_config="${XDG_CONFIG_HOME:-$HOME/.config}/fish/config.fish"
        ;;
    *)
        luna_warn "Shell '${shell_name:-unknown}' is not supported for automatic PATH setup. Add ~/.local/bin to the start of PATH to use Luna."
        exit 0
        ;;
esac

if [[ -e "$shell_config" && ! -f "$shell_config" ]]; then
    luna_warn "Cannot configure PATH in a non-file startup path: $shell_config. Add ~/.local/bin to the start of PATH manually."
    exit 0
fi

block_start='# >>> Luna command PATH >>>'
block_end='# <<< Luna command PATH <<<'
if [[ -f "$shell_config" ]] && grep -Fxq -- "$block_start" "$shell_config"; then
    luna_info "Luna PATH is already configured: $shell_config"
    exit 0
fi

# Stage the complete replacement before moving the original to its backup. When
# the startup file is a symlink, preserve that link without editing its target.
mkdir -p -- "${shell_config%/*}"
temporary_config=$(mktemp "${shell_config}.luna.XXXXXX")
trap 'if [[ -n "${temporary_config:-}" ]]; then rm -f -- "$temporary_config"; fi' EXIT
if [[ -f "$shell_config" ]]; then
    cat -- "$shell_config" > "$temporary_config"
    chmod --reference="$shell_config" -- "$temporary_config"
fi

{
    printf '\n%s\n' "$block_start"
    if [[ "$shell_name" == fish ]]; then
        # fish_add_path moves an existing entry and avoids duplicate PATH entries.
        printf 'fish_add_path --move --prepend --path "$HOME/.local/bin"\n'
    else
        cat <<'PATH_BLOCK'
if [ "${PATH%%:*}" != "$HOME/.local/bin" ]; then
    export PATH="$HOME/.local/bin:$PATH"
fi
PATH_BLOCK
    fi
    printf '%s\n' "$block_end"
} >> "$temporary_config"

luna_backup_path "$shell_config"
mv -- "$temporary_config" "$shell_config"
temporary_config=
luna_success "Configured Luna PATH: $shell_config"
luna_info 'Open a new terminal to use Luna, or run ~/.local/bin/luna now.'
