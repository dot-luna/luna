#!/usr/bin/env bash
# Called by 3-install-dev-tools.lua after installing tools to activate them in new terminals.
set -euo pipefail

script_path=$(readlink -f -- "${BASH_SOURCE[0]}")
source "$(dirname -- "$script_path")/../../lib/common.sh"

if ! luna_available mise; then
    luna_warn 'Shell activation skipped: mise is unavailable.'
    exit 0
fi

# SHELL identifies the user's login shell, not the Bash running this helper.
shell_path=${SHELL:-}
shell_name=${shell_path##*/}
case "$shell_name" in
    bash)
        shell_config="$HOME/.bashrc"
        ;;
    zsh)
        # Zsh keeps activation and generated completions in Luna's modular config.
        bash "${script_path%/*}/zsh.sh"
        exit 0
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

# Preserve personal content and permissions when adding the managed block.
luna_append_config_block "$shell_config" "$block_start" "$block_end" <<'EOF'
if [[ $- == *i* ]] && command -v mise >/dev/null 2>&1; then
    eval "$(mise activate bash)"
fi
EOF
luna_success "Configured mise activation: $shell_config"
luna_info 'Open a new terminal to use your mise tools.'
