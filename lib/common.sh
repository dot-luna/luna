# Shared Bash helpers. Source this file after enabling the caller's shell options.

# Preserve terminal detection when the installer sends output through its log tee.
# NO_COLOR also applies when a parent explicitly enabled terminal colors.
if [[ -n "${NO_COLOR:-}" ]]; then
    LUNA_COLOR=0
elif [[ "${LUNA_COLOR:-auto}" == auto ]]; then
    if [[ -t 1 && "${TERM:-}" != dumb ]]; then
        LUNA_COLOR=1
    else
        LUNA_COLOR=0
    fi
fi
export LUNA_COLOR

# Label Luna output consistently; attention messages start a fresh visual block.
luna_log() {
    local level=$1
    shift
    local color=
    local reset=

    case "$level" in
        STEP|WARN|ERROR)
            printf '\n'
            ;;
    esac
    if [[ "$LUNA_COLOR" == 1 ]]; then
        reset=$'\e[0m'
        case "$level" in
            STEP)
                color=$'\e[1;36m'
                ;;
            OK)
                color=$'\e[32m'
                ;;
            WARN|INPUT)
                color=$'\e[1;33m'
                ;;
            ERROR)
                color=$'\e[1;31m'
                ;;
            *)
                color=$'\e[36m'
                ;;
        esac
    fi
    printf '%s[%(%H:%M:%S)T] [%s]%s %s\n' "$color" -1 "$level" "$reset" "$*"
}

luna_info() {
    luna_log INFO "$*"
}

luna_success() {
    luna_log OK "$*"
}

luna_warn() {
    luna_log WARN "$*" >&2
}

luna_error() {
    luna_log ERROR "$*" >&2
}

luna_step() {
    luna_log STEP "$*"
}

# Keep external tools visually separate from Luna. Strip their ANSI sequences so
# a package manager's reset cannot cancel the muted color halfway through a line.
luna_tool_output() {
    local line
    local ansi=$'\e''\[[0-?]*[ -/]*[@-~]'
    while IFS= read -r line || [[ -n "$line" ]]; do
        while [[ "$line" =~ $ansi ]]; do
            line=${line/"${BASH_REMATCH[0]}"/}
        done
        if [[ "$LUNA_COLOR" == 1 ]]; then
            printf '\e[90m  %s\e[0m\n' "$line"
        else
            printf '  %s\n' "$line"
        fi
    done
}

# Stream stdout/stderr without consuming stdin. Capture both pipeline statuses
# inside a conditional so errexit cannot hide a command failure during cleanup.
luna_run() {
    local -a statuses
    printf '\n'
    if "$@" 2>&1 | luna_tool_output; then
        statuses=("${PIPESTATUS[@]}")
    else
        statuses=("${PIPESTATUS[@]}")
    fi
    printf '\n'
    if (( statuses[0] != 0 )); then
        return "${statuses[0]}"
    fi
    return "${statuses[1]}"
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

    printf '\n'
    while true; do
        if [[ "$LUNA_COLOR" == 1 ]]; then
            printf '\e[1;33m[INPUT] %s [%s]\e[0m ' "$question" "$choices"
        else
            printf '[INPUT] %s [%s] ' "$question" "$choices"
        fi
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
