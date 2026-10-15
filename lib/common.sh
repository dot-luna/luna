# Shared Bash helpers. Source this file after enabling the caller's shell options.

# Print literal messages without treating user-provided text as a format string.
luna_info() {
    printf '%s\n' "$*"
}

luna_error() {
    printf '%s\n' "$*" >&2
}

# Return a status so callers can choose whether absence is an error or a skip.
luna_available() {
    command -v "$1" >/dev/null 2>&1
}

# Resolve checkout resources through symlinks, independently of the working dir.
luna_script_dir() {
    local script_path
    script_path=$(readlink -f -- "$1") || return
    dirname -- "$script_path"
}

# Read an explicit choice; EOF declines so unattended runs cannot approve work.
luna_confirm() {
    local question=$1
    local default=${2:-n}
    local choices='y/N'
    local answer

    if [[ "$default" == y ]]; then
        choices='Y/n'
    fi

    while true; do
        printf '%s [%s] ' "$question" "$choices"
        if ! IFS= read -r answer; then
            printf '\n'
            return 1
        fi

        case "${answer,,}" in
            y|yes)
                return 0
                ;;
            n|no)
                return 1
                ;;
            '')
                if [[ "$default" == y ]]; then
                    return 0
                fi
                return 1
                ;;
            *)
                luna_info 'Please answer yes or no.'
                ;;
        esac
    done
}

# Move conflicts beside their old location so relative symlinks still resolve.
# Numbered backups preserve earlier runs without copying large source trees.
luna_backup_path() {
    local original=$1
    local backup="$original.luna-backup"
    local suffix=1

    if [[ ! -e "$original" && ! -L "$original" ]]; then
        return 0
    fi

    while [[ -e "$backup" || -L "$backup" ]]; do
        backup="$original.luna-backup.$suffix"
        suffix=$((suffix + 1))
    done

    mv --no-clobber --no-target-directory -- "$original" "$backup" || return
    if [[ -e "$original" || -L "$original" ]]; then
        luna_error "Could not back up existing path: $original"
        return 1
    fi
    luna_info "Backed up $original to $backup"
}
