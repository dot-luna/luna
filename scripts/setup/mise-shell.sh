#!/usr/bin/env bash
# Called by mise.lua after installing tools to activate them in new terminals.
set -euo pipefail

script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
source "$(dirname -- "$script_path")/../../lib/common.sh"

for option in "$@"; do
    case "$option" in
        --force)
            # Setup forwards this flag; personal shell files are always backed up.
            ;;
        -h|--help)
            printf 'Usage: %s [--force]\n\nActivate mise in new Bash, Zsh, or fish terminals.\nChanged shell startup files receive adjacent .luna-backup backups.\n--force is accepted for compatibility; backups are always made.\n' "${0##*/}"
            exit 0
            ;;
        *)
            luna_error "Unknown option: $option"
            exit 2
            ;;
    esac
done

if ! luna_available mise; then
    luna_error 'mise is required before configuring shell activation. Run the packages setup step first.'
    exit 1
fi

# SHELL identifies the user's login shell, not the Bash running this helper.
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
        luna_warn "Shell '${shell_name:-unknown}' is not supported for automatic mise activation. Configure mise for your shell manually: https://mise.jdx.dev/shell-setup.html"
        exit 0
        ;;
esac

if [[ -e "$shell_config" && ! -f "$shell_config" ]]; then
    luna_warn "Cannot activate mise in a non-file startup path: $shell_config. Configure mise for your shell manually."
    exit 0
fi

block_start='# >>> Luna mise activation >>>'
block_end='# <<< Luna mise activation <<<'
if [[ -f "$shell_config" ]] && grep -Fxq -- "$block_start" "$shell_config"; then
    luna_info "Luna mise activation is already configured: $shell_config"
    exit 0
fi

# Stage the complete file before backing up the original. Symlinks are moved
# intact into the backup, leaving the user's original target untouched.
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
        # fish also reads config.fish in scripts; hooks belong in terminals only.
        cat <<'FISH_BLOCK'
if status is-interactive; and command -q mise
    mise activate fish | source
end
FISH_BLOCK
    else
        printf 'if [[ $- == *i* ]] && command -v mise >/dev/null 2>&1; then\n'
        printf '    eval "$(mise activate %s)"\n' "$shell_name"
        printf 'fi\n'
    fi
    printf '%s\n' "$block_end"
} >> "$temporary_config"

luna_backup_path "$shell_config"
mv -- "$temporary_config" "$shell_config"
temporary_config=
luna_success "Configured mise activation: $shell_config"
luna_info 'Open a new terminal to use your mise tools.'
