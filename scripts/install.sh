#!/usr/bin/env bash
# Install Luna on Arch Linux from a standalone download or a local checkout.
# This file must work before the repository exists; do not source repo helpers.
#
# Download this script directly (the root install.sh is a Git symlink):
#   curl -fsSL https://raw.githubusercontent.com/dot-luna/luna/master/scripts/install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/dot-luna/luna/master/scripts/install.sh | bash -s -- --ref v1.0.0
#
# The checkout stays in ~/.local/src/luna because deployed configs refer to it.
# Run as your normal user in a terminal; sudo is used for system setup.
# Every run replaces the install checkout with a fresh copy of the requested ref.
set -euo pipefail

# Decide before tee replaces stdout, then share that choice with setup children.
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

usage() {
    cat <<'HELP'
Usage: bash install.sh [--ref <branch-or-tag>]
       curl -fsSL <installer-url> | bash -s -- [--ref <branch-or-tag>]

Options:
    --ref <name>    Install a branch or tag (default: master).
    -h, --help      Show this help without changing anything.

Examples:
    bash install.sh --ref master
    bash install.sh --ref v1.0.0

Checkout: ~/.local/src/luna
Logs:     $XDG_STATE_HOME/luna/ (defaults to ~/.local/state/luna/)

Requires Arch Linux, a normal user with sudo access, and an interactive terminal.
Installs dependencies and Hyprland configuration using scripts/setup.sh.
Package installation may perform a full system upgrade without package-manager confirmations.
Sudo authentication and the optional NVIDIA confirmation remain interactive.
An existing install directory is removed and freshly cloned, without a backup.
HELP
}

log() {
    local level=$1
    shift
    local color=
    local reset=
    if [[ "$level" == WARN || "$level" == ERROR ]]; then
        printf '\n'
    fi
    if [[ "$LUNA_COLOR" == 1 ]]; then
        reset=$'\e[0m'
        case "$level" in
            STEP)
                color=$'\e[1;36m'
                ;;
            OK)
                color=$'\e[32m'
                ;;
            WARN)
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

# These small helpers stay self-contained: the checkout does not exist yet.
tool_output() {
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

run_tool() {
    local -a statuses
    printf '\n'
    if "$@" 2>&1 | tool_output; then
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

fail() {
    log ERROR "$*" >&2
    exit 1
}

step() {
    current_step=$1
    printf '\n'
    log STEP "$current_step"
}

welcome() {
    if [[ "$LUNA_COLOR" == 1 ]]; then
        printf '\e[1;36m'
    fi
    cat <<'BANNER'

     __    __  ___   _____
    / /   / / / / | / /   |
   / /   / / / /  |/ / /| |
  / /___/ /_/ / /|  / ___ |
 /_____/\____/_/ |_/_/  |_|

    Welcome to the Luna installer.
    Your desktop, your space.

BANNER
    if [[ "$LUNA_COLOR" == 1 ]]; then
        printf '\e[0m'
    fi
}

# Restore the terminal streams before waiting for tee, so the log is complete
# when the installer exits. Keep the failing command's status for callers.
finish() {
    local status=$1
    trap - EXIT
    set +e

    if (( status != 0 )); then
        log ERROR "Installation stopped during: $current_step" >&2
    fi

    if [[ -n "$log_file" ]]; then
        log INFO "Install log: $log_file"
    fi

    if [[ -n "$log_pid" ]]; then
        exec 1>&3 2>&4
        exec 3>&- 4>&-

        if ! wait "$log_pid"; then
            log ERROR 'Could not write the complete install log.' >&2
            if (( status == 0 )); then
                status=1
            fi
        fi
    fi

    exit "$status"
}

# tee keeps prompts without newlines visible immediately. Wait for the plain-log
# filter as well as tee so finish() never reports success before the log is saved.
copy_log() {
    local plain_fd plain_pid
    local tee_status=0
    local plain_status=0
    exec {plain_fd}> >(LC_ALL=C sed -u $'s/\033\\[[0-?]*[ -/]*[@-~]//g' >> "$log_file")
    plain_pid=$!
    tee "/dev/fd/$plain_fd" || tee_status=$?
    exec {plain_fd}>&-
    wait "$plain_pid" || plain_status=$?
    if (( tee_status != 0 )); then
        return "$tee_status"
    fi
    return "$plain_status"
}

start_log() {
    local state_dir=${XDG_STATE_HOME:-"$HOME/.local/state"}
    if [[ "$state_dir" != /* ]]; then
        fail 'XDG_STATE_HOME must be an absolute path.'
    fi

    mkdir -p -- "$state_dir/luna"
    log_file=$(mktemp "$state_dir/luna/install-$(date +%Y%m%d-%H%M%S)-XXXXXX.log")

    # Terminal colors stay visible; the private log receives only plain text.
    # Save the original streams for finish(), including child command output.
    exec 3>&1 4>&2
    exec > >(copy_log) 2>&1
    log_pid=$!
}

check_system() {
    if (( EUID == 0 )); then
        fail 'Run this installer as your normal user, without sudo.'
    fi

    if [[ "${HOME:-}" != /* || "$HOME" == / ]]; then
        fail 'HOME must point to your user home directory using an absolute path.'
    fi

    local ID=
    if [[ ! -r /etc/os-release ]]; then
        fail 'Cannot identify this system; Luna currently supports Arch Linux.'
    fi

    # Read the distribution identity, rather than assuming that pacman alone
    # means the host supports Luna's Arch package manifest.
    source /etc/os-release
    if [[ "$ID" != arch ]]; then
        fail 'Luna currently supports Arch Linux only.'
    fi

    local tool
    for tool in pacman sudo tee sed mktemp date mkdir rm; do
        if ! command -v "$tool" >/dev/null 2>&1; then
            fail "Required command is missing: $tool"
        fi
    done

    # curl owns stdin while streaming the script. Sudo and the NVIDIA question
    # must read the user's terminal instead of consuming script text or EOF.
    if ! { exec </dev/tty; } 2>/dev/null; then
        fail 'Run this installer in an interactive terminal for sudo and NVIDIA confirmation.'
    fi
}

main() {
    local ref=master
    local repo_url=https://github.com/dot-luna/luna.git
    local install_dir

    while (( $# > 0 )); do
        case "$1" in
            --ref)
                if (( $# < 2 )) || [[ -z "$2" || "$2" == -* ]]; then
                    log ERROR '--ref requires a branch or tag name.' >&2
                    exit 2
                fi
                ref=$2
                shift 2
                ;;
            -h|--help)
                usage
                return
                ;;
            *)
                log ERROR "Unknown option: $1. Use --help for usage." >&2
                exit 2
                ;;
        esac
    done

    # Reject obvious bad input before requesting authentication or installing
    # Git. Git performs the full reference-name validation once available.
    if [[ "$ref" == refs/* || "$ref" == *[[:space:]]* || "$ref" == *..* || "$ref" == *'@{'* ]]; then
        log ERROR "Invalid branch or tag name: $ref" >&2
        exit 2
    fi

    log_file=
    log_pid=
    current_step='system checks'
    trap 'finish "$?"' EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM

    check_system
    install_dir="$HOME/.local/src/luna"
    start_log
    welcome
    log INFO "Repository: $repo_url"
    log INFO "Branch/tag: $ref"
    log INFO "Checkout:   $install_dir"
    log WARN 'Setup installs packages and may upgrade the system without further package confirmations.'

    step '1/4 — Check system and sudo access'
    sudo -v
    log OK 'Arch Linux and sudo access verified.'

    step '2/4 — Prepare Git'
    if ! command -v git >/dev/null 2>&1; then
        log INFO 'Installing Git with pacman.'
        run_tool sudo pacman -Syu --needed --noconfirm -- git
    fi
    if ! command -v git >/dev/null 2>&1; then
        fail 'Git is still unavailable after package installation.'
    fi
    if ! git check-ref-format "refs/heads/$ref"; then
        fail "Invalid branch or tag name: $ref"
    fi
    log OK 'Git is ready.'

    step '3/4 — Prepare the Luna checkout'
    mkdir -p -- "$HOME/.local/src"

    # Running the installer authorizes replacing this fixed install location,
    # including local changes. rm removes a destination symlink, not its target.
    if [[ -e "$install_dir" || -L "$install_dir" ]]; then
        log INFO "Removing existing install checkout: $install_dir"
        rm -rf -- "$install_dir"
    fi

    log INFO "Cloning $ref..."
    run_tool git clone --branch "$ref" --single-branch -- "$repo_url" "$install_dir"
    if [[ ! -f "$install_dir/scripts/setup.sh" ]]; then
        fail "The selected version does not contain scripts/setup.sh: $ref"
    fi
    log OK "Checkout ready at commit $(git -C "$install_dir" rev-parse --short HEAD)."

    step '4/4 — Run Luna setup'
    # Setup backs up and replaces config/source conflicts, then asks separately
    # about NVIDIA drivers. Run from the checkout for a predictable cwd.
    cd -- "$install_dir"
    bash "$install_dir/scripts/setup.sh"

    printf '\n'
    log OK 'Luna setup completed.'
    log INFO 'Dependencies, Hyprland configuration, source links, and the Luna command are installed.'
    log INFO 'Open a new terminal, then run luna --version to check the installed version.'
    log INFO 'Keep the checkout in place; your configuration links depend on it.'
    log INFO 'Log out and select Hyprland in your session chooser, or start it using your usual method.'
    log INFO 'If system packages requested a reboot, reboot before starting the new session.'
}

# Parse the call and exit together before runtime stdin becomes /dev/tty.
# Otherwise piped Bash could read terminal answers as commands after main ends.
{
    main "$@"
    exit 0
}
