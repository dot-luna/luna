#!/usr/bin/env bash
# Own one VNC console and stop its VM on exit unless --keep-alive was requested.
set -euo pipefail

compose_file=$1
keep_alive=$2
wait_seconds=$3
config_dir=$(dirname -- "$compose_file")
compose=(docker compose --project-name luna-macos --file "$compose_file")
console_ready=false
viewer_pid=

cleanup() {
    local result=$?
    trap - EXIT INT TERM HUP
    if [[ -n $viewer_pid ]] && kill -0 "$viewer_pid" 2>/dev/null; then
        kill "$viewer_pid" 2>/dev/null || true
        wait "$viewer_pid" 2>/dev/null || true
    fi
    if [[ $console_ready == true && $keep_alive == false ]]; then
        printf '\nStopping macOS VM...\n'
        bash "$(dirname -- "$0")/../../../lib/vm-stop.sh" "$compose_file" macos || result=1
    fi
    exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

umask 077
exec 9>"$config_dir/session.lock"
if ! flock -n 9; then
    printf 'A Luna macOS console session is already running.\n' >&2
    exit 1
fi
running=$("${compose[@]}" ps --status running -q macos)
if [[ -z $running ]]; then
    "${compose[@]}" up -d --pull never --no-build macos
fi
printf 'Waiting for the macOS console (up to %ss)...\n' "$wait_seconds"
bash "$(dirname -- "$0")/wait-ready.sh" "$compose_file" "$wait_seconds"
console_ready=true

# This is QEMU's console, available during recovery as well as normal guest use.
# Keep compositor shortcuts available even while the viewer is fullscreen.
vncviewer -FullScreen -Shared -FullscreenSystemKeys=0 -AcceptClipboard=1 -SendClipboard=1 127.0.0.1::5900 &
viewer_pid=$!
result=0
wait "$viewer_pid" || result=$?
viewer_pid=
exit "$result"
