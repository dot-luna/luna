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
