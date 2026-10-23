#!/usr/bin/env bash
# Install Luna on Arch Linux from a standalone download or a local checkout.
# This file must work before the repository exists; do not source repo helpers.
#
# Download this script directly from the repository root:
#   curl -fsSL https://raw.githubusercontent.com/dot-luna/luna/master/install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/dot-luna/luna/master/install.sh | bash -s -- --ref v1.0.0
#
# LUNA_INSTALL_DIR selects the checkout; it defaults to ~/.local/src/luna.
# LUNA_CONFIG_DIR selects the generated app configuration destination.
# Keep the checkout in place after setup because deployed configs refer to it.
# Run as your normal user in a terminal; sudo is used for system setup.
# Existing Luna checkouts are updated in place to the requested branch or tag.
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

main() {
    local ref=master
    local repo_url=https://github.com/dot-luna/luna.git
    local install_dir
    local skip_list skip_step normalized_skips=
    local valid_steps='lua core mise aur main fonts git-apps src command postinstall apps keyring defaults session cleanup'
    local -A skipped_steps=()
    local -a setup_arguments=()

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
            --skip=*)
                # Validate before OS checks or checkout changes. Parse each field
                # explicitly so empty fields and embedded newlines are rejected.
                skip_list=${1#--skip=}
                while :; do
                    skip_step=${skip_list%%,*}
                    case "$skip_step" in
                        lua|core|mise|aur|main|fonts|git-apps|src|command|postinstall|apps|keyring|defaults|session|cleanup)
                            ;;
                        *)
                            log ERROR "Invalid skip step '${skip_step:-<empty>}'. Valid steps: $valid_steps." >&2
                            exit 2
                            ;;
                    esac
                    if [[ -z "${skipped_steps[$skip_step]+set}" ]]; then
                        skipped_steps[$skip_step]=1
                        normalized_skips+="${normalized_skips:+,}$skip_step"
                    fi
                    if [[ "$skip_list" != *,* ]]; then
                        break
                    fi
                    skip_list=${skip_list#*,}
                done
                shift
                ;;
            --skip)
                log ERROR "Use --skip=<step[,step...]> (for example --skip=git-apps,fonts). Valid steps: $valid_steps." >&2
                exit 2
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
    if [[ -n "$normalized_skips" ]]; then
        setup_arguments=("--skip=$normalized_skips")
    fi

    log_file=
    log_pid=
    current_step='system checks'
    trap 'finish "$?"' EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM

    check_system
    resolve_install_dir
    install_dir=$LUNA_INSTALL_DIR
    start_log
    welcome
    log INFO "Install folder: $install_dir"
    log WARN 'Packages may be installed or upgraded automatically.'

    step '1/4 — Check system and sudo access'
    sudo -v

    step '2/4 — Prepare Git'
    if ! command -v git >/dev/null 2>&1; then
        log INFO 'Installing Git...'
        run_tool sudo pacman -Syu --needed --noconfirm -- git
    fi
    if ! command -v git >/dev/null 2>&1; then
        fail 'Git is still unavailable after package installation.'
    fi
    if ! git check-ref-format "refs/heads/$ref"; then
        fail "Invalid branch or tag name: $ref"
    fi

    step '3/4 — Prepare Luna'
    prepare_checkout "$install_dir" "$ref" "$repo_url"
    if [[ ! -f "$install_dir/scripts/setup.sh" ]]; then
        fail "The selected version does not contain scripts/setup.sh: $ref"
    fi

    step '4/4 — Install Luna'
    # Setup replaces source-link conflicts without backups.
    # Run from the checkout for a predictable cwd.
    cd -- "$install_dir"
    bash "$install_dir/scripts/setup.sh" "${setup_arguments[@]}"

    printf '\n'
    log OK 'Luna setup completed.'
    if [[ -z "${skipped_steps[command]+set}" ]]; then
        log INFO 'Open a new terminal and run luna --version.'
    fi
    log INFO 'Keep the install folder; Luna uses its files.'
}

prepare_checkout() {
    local directory=$1 ref=$2 repo_url=$3

    # Git can discover a parent repository, so verify the selected directory is
    # the worktree root before updating it. This also supports Git worktrees.
    if [[ -e "$directory/.git" || -L "$directory/.git" ]] || git -C "$directory" rev-parse --git-dir >/dev/null 2>&1; then
        local checkout_root
        checkout_root=$(git -C "$directory" rev-parse --show-toplevel) || fail "Not a usable Git checkout: $directory"
        if [[ "$(realpath -m -- "$checkout_root")" != "$(realpath -m -- "$directory")" ]]; then
            fail "LUNA_INSTALL_DIR must point to the Git checkout root: $checkout_root"
        fi

        update_checkout "$directory" "$ref" "$repo_url"
        return
    fi

    mkdir -p -- "$(dirname -- "$directory")"

    # Keep the existing replacement behavior for non-Git paths. Removing a
    # destination symlink leaves its external target untouched.
    if [[ -e "$directory" || -L "$directory" ]]; then
        log INFO "Replacing existing path: $directory"
        rm -rf -- "$directory"
    fi

    log INFO "Downloading Luna ($ref)..."
    # Tag installs intentionally detach HEAD; Git's introductory advice is noise here.
    run_tool git -c advice.detachedHead=false clone --quiet --branch "$ref" --single-branch -- "$repo_url" "$directory"
}

update_checkout() {
    local directory=$1 ref=$2 repo_url=$3
    local origin repo_path
    origin=$(git -C "$directory" config --get remote.origin.url) || fail "The existing checkout has no origin remote: $directory"
    repo_path=${repo_url#https://}
    repo_path=${repo_path%.git}
    case "${origin%/}" in
        "https://$repo_path"|"https://$repo_path.git"|"git@${repo_path/\//:}"|"git@${repo_path/\//:}.git"|"ssh://git@$repo_path"|"ssh://git@$repo_path.git")
            ;;
        *)
            fail "The existing checkout's origin is not $repo_url: $origin"
            ;;
    esac

    log INFO "Updating Luna ($ref)..."

    # Resolve the requested name on the remote, not against potentially stale
    # local refs. Match clone's branch-first behavior when a tag has the same name.
    local remote_refs object_id remote_ref
    local has_branch=0 has_tag=0
    remote_refs=$(git -C "$directory" ls-remote --refs origin "refs/heads/$ref" "refs/tags/$ref") || fail 'Could not read branches and tags from origin.'
    while read -r object_id remote_ref; do
        case "$remote_ref" in
            "refs/heads/$ref")
                has_branch=1
                ;;
            "refs/tags/$ref")
                has_tag=1
                ;;
        esac
    done <<< "$remote_refs"

    if (( has_branch )); then
        # Fetch explicitly so checkouts cloned with --single-branch can switch
        # to another branch. Only the remote-tracking ref may move backwards.
        run_tool git -C "$directory" fetch --quiet --no-tags origin "+refs/heads/$ref:refs/remotes/origin/$ref"

        # Git otherwise overwrites ignored local files when a new ref tracks them.
        if git -C "$directory" show-ref --verify --quiet "refs/heads/$ref"; then
            run_tool git -C "$directory" switch --quiet --no-overwrite-ignore --no-guess "$ref" || fail 'Could not switch branches. Commit or stash conflicting changes and retry.'
        else
            run_tool git -C "$directory" switch --quiet --no-overwrite-ignore --no-track -c "$ref" "refs/remotes/origin/$ref" || fail 'Could not switch branches. Commit or stash conflicting changes and retry.'
        fi

        # Explicit flags override branch merge options as well as global config,
        # preserving ignored files and leaving conflicting edits in place.
        run_tool git -C "$directory" merge --quiet --ff-only --no-autostash --no-overwrite-ignore "refs/remotes/origin/$ref" || fail 'Could not update the branch. Resolve conflicting edits or diverged commits and retry.'
    elif (( has_tag )); then
        # Refresh this tag even if its remote target changed; tags are checked
        # out detached and do not merge into or reset any local branch.
        run_tool git -C "$directory" fetch --quiet --no-tags origin "+refs/tags/$ref:refs/tags/$ref"
        run_tool git -C "$directory" switch --quiet --no-overwrite-ignore --detach "refs/tags/$ref" || fail 'Could not switch to the tag. Commit or stash conflicting changes and retry.'
    else
        fail "Branch or tag does not exist on origin: $ref"
    fi
}

resolve_install_dir() {
    local directory=${LUNA_INSTALL_DIR:-"$HOME/.local/src/luna"}
    if [[ "$directory" != /* ]]; then
        fail 'LUNA_INSTALL_DIR must be an absolute path to the Luna checkout.'
    fi

    # A trailing slash must not turn removal of a symlink into traversal of its target.
    while [[ "$directory" != / && "$directory" == */ ]]; do
        directory=${directory%/}
    done

    # Non-Git install paths are replaced; reject home and its ancestors,
    # including equivalent paths containing symlinks or dot components.
    local resolved_dir resolved_home
    resolved_dir=$(realpath -m -- "$directory")
    resolved_home=$(realpath -m -- "$HOME")
    if [[ "$resolved_dir" == / || "$resolved_dir" == "$resolved_home" || "$resolved_home" == "$resolved_dir/"* ]]; then
        fail 'LUNA_INSTALL_DIR must not be /, your home directory, or a parent of your home directory.'
    fi

    # Child setup processes inherit the same convention, including the default.
    export LUNA_INSTALL_DIR="$directory"
}

usage() {
    cat <<'HELP'
Usage: bash install.sh [--ref <branch-or-tag>] [--skip=<step[,step...]>]
       curl -fsSL <installer-url> | bash -s -- [options]

Options:
    --ref <name>           Install a branch or tag (default: master).
    --skip=<step,...>      Skip selected setup steps.
    -h, --help             Show this help without changing anything.

Setup steps:
    lua core mise aur main fonts git-apps src command postinstall apps keyring defaults session cleanup
    Skips do not skip dependencies automatically; provide what remaining steps need.
    System checks, Git bootstrap, and checkout preparation always run.

Environment:
    LUNA_INSTALL_DIR    Absolute checkout path (default: ~/.local/src/luna).
    LUNA_CONFIG_DIR     App config directory (default: $XDG_CONFIG_HOME/luna,
                        or ~/.config/luna when XDG_CONFIG_HOME is unset or empty).

Examples:
    bash install.sh --ref master
    bash install.sh --ref v1.0.0
    bash install.sh --skip=git-apps,fonts,mise
    LUNA_INSTALL_DIR="$HOME/coding/luna" bash install.sh --ref dev

Logs:     $XDG_STATE_HOME/luna/ (defaults to ~/.local/state/luna/)

Requires Arch Linux, a normal user with sudo access, and an interactive terminal.
Packages may be installed or upgraded automatically.
Updates existing Luna checkouts; stops if local edits or history conflict.
Replaces existing non-Git install paths without a backup.
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
    # ANSI byte ranges need C collation; keep this local to the output filter.
    local LC_ALL=C
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
    if "$@" 2>&1 | tool_output; then
        statuses=("${PIPESTATUS[@]}")
    else
        statuses=("${PIPESTATUS[@]}")
    fi
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
    for tool in pacman sudo tee sed mktemp date mkdir rm dirname realpath; do
        if ! command -v "$tool" >/dev/null 2>&1; then
            fail "Required command is missing: $tool"
        fi
    done

    # curl owns stdin while streaming the script. Sudo must read the user's
    # terminal instead of consuming script text or EOF.
    if ! { exec </dev/tty; } 2>/dev/null; then
        fail 'Run this installer in an interactive terminal for sudo authentication.'
    fi
}

# Parse the call and exit together before runtime stdin becomes /dev/tty.
# Otherwise piped Bash could read terminal answers as commands after main ends.
{
    main "$@"
    exit 0
}
