#!/usr/bin/env bash
# Install Luna on Arch Linux from a standalone download or a local checkout.
# This file must work before the repository exists; do not source repo helpers.
#
# Download this script directly (the root install.sh is a Git symlink):
#   curl -fsSL https://raw.githubusercontent.com/dot-luna/luna/master/scripts/install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/dot-luna/luna/master/scripts/install.sh | bash -s -- --ref v1.0.0
#
# The checkout stays in ~/.local/src/luna because deployed configs refer to it.
# Run as your normal user in a terminal; sudo is used only for package setup.
# Existing clean checkouts can be reused, but are never switched or updated here.
set -euo pipefail

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
Package installation may perform a full system upgrade and retains its prompts.
An existing checkout must be clean and match the requested branch or tag.
HELP
}

log() {
    local level=$1
    shift
    printf '[%(%H:%M:%S)T] [%s] %s\n' -1 "$level" "$*"
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
    cat <<'BANNER'

     __    __  ___   _____
    / /   / / / / | / /   |
   / /   / / / /  |/ / /| |
  / /___/ /_/ / /|  / ___ |
 /_____/\____/_/ |_/_/  |_|

    Welcome to the Luna installer.
    Your desktop, your space.

BANNER
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

start_log() {
    local state_dir=${XDG_STATE_HOME:-"$HOME/.local/state"}
    if [[ "$state_dir" != /* ]]; then
        fail 'XDG_STATE_HOME must be an absolute path.'
    fi

    mkdir -p -- "$state_dir/luna"
    log_file=$(mktemp "$state_dir/luna/install-$(date +%Y%m%d-%H%M%S)-XXXXXX.log")

    # Plain text goes to both the terminal and a private log, including output
    # from Git and package managers. Save the original streams for finish().
    exec 3>&1 4>&2
    exec > >(tee -a "$log_file") 2>&1
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
    for tool in pacman sudo tee mktemp date mkdir realpath; do
        if ! command -v "$tool" >/dev/null 2>&1; then
            fail "Required command is missing: $tool"
        fi
    done

    # curl owns stdin while streaming the script. Package manager confirmations
    # must read the user's terminal instead of consuming script text or EOF.
    if ! { exec </dev/tty; } 2>/dev/null; then
        fail 'Run this installer in an interactive terminal to answer package prompts.'
    fi
}

verify_checkout() {
    local install_dir=$1
    local ref=$2
    local root origin branch tag_commit

    if [[ -L "$install_dir" || ! -d "$install_dir/.git" ]]; then
        fail "Install location is occupied by something other than a Luna checkout: $install_dir"
    fi

    root=$(git -C "$install_dir" rev-parse --show-toplevel)
    if [[ "$root" != "$(realpath -- "$install_dir")" ]]; then
        fail "Install location is not the root of its Git checkout: $install_dir"
    fi

    # Read the stored URL so user-configured Git mirrors (insteadOf) also work.
    origin=$(git -C "$install_dir" config --get remote.origin.url)
    case "$origin" in
        https://github.com/dot-luna/luna.git|git@github.com:dot-luna/luna.git)
            ;;
        *)
            fail "Existing checkout has a different origin: $origin"
            ;;
    esac

    if [[ -n "$(git -C "$install_dir" status --porcelain --untracked-files=normal)" ]]; then
        fail 'Existing checkout has local changes. Save them before rerunning the installer.'
    fi

    # Branch installs must remain on that exact branch. A detached checkout is
    # accepted only for the requested tag; peel annotated tags to their commit.
    if branch=$(git -C "$install_dir" symbolic-ref --quiet HEAD); then
        if [[ "$branch" != "refs/heads/$ref" ]]; then
            fail "Existing checkout is on ${branch#refs/heads/}; requested $ref. Switch it explicitly before rerunning."
        fi
    else
        if ! tag_commit=$(git -C "$install_dir" rev-parse --verify "refs/tags/$ref^{commit}" 2>/dev/null); then
            fail "Existing checkout is detached and does not match the requested tag: $ref"
        fi
        if [[ "$(git -C "$install_dir" rev-parse HEAD)" != "$tag_commit" ]]; then
            fail "Existing checkout does not match tag $ref. Switch it explicitly before rerunning."
        fi
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
    log INFO 'Setup installs packages and may upgrade the system. Review package-manager prompts.'

    step '1/4 — Check system and sudo access'
    sudo -v
    log OK 'Arch Linux and sudo access verified.'

    step '2/4 — Prepare Git'
    if ! command -v git >/dev/null 2>&1; then
        log INFO 'Installing Git with pacman.'
        sudo pacman -Syu --needed -- git
    fi
    if ! command -v git >/dev/null 2>&1; then
        fail 'Git is still unavailable after package installation.'
    fi
    if ! git check-ref-format "refs/heads/$ref"; then
        fail "Invalid branch or tag name: $ref"
    fi
    log OK 'Git is ready.'

    step '3/4 — Prepare the Luna checkout'
    if [[ -e "$install_dir" || -L "$install_dir" ]]; then
        verify_checkout "$install_dir" "$ref"
        log INFO 'Reusing the matching local checkout without updating it.'
    else
        mkdir -p -- "$HOME/.local/src"
        log INFO "Cloning $ref..."
        git clone --branch "$ref" --single-branch -- "$repo_url" "$install_dir"
    fi
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
    log INFO 'Dependencies, Hyprland configuration, and source links are installed.'
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
