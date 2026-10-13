#!/usr/bin/env bash
# Own one foreground RDP session and stop its VM on exit unless --keep-alive was requested.
set -euo pipefail

compose_file=$1
rdp_arguments=$2
keep_alive=$3
wait_seconds=$4
config_dir=$(dirname -- "$compose_file")
compose=(docker compose --project-name luna-windows --file "$compose_file")
vm_started=false
rdp_ready=false
rdp_pid=

cleanup() {
    local result=$?
    trap - EXIT INT TERM HUP
    if [[ -n $rdp_pid ]] && kill -0 "$rdp_pid" 2>/dev/null; then
        kill "$rdp_pid" 2>/dev/null || true
        wait "$rdp_pid" 2>/dev/null || true
    fi
    rm -f -- "$rdp_arguments"
    if [[ $vm_started == true && $rdp_ready == true && $keep_alive == false ]]; then
        printf '\nStopping Windows VM...\n'
        "${compose[@]}" stop --timeout 120 windows || result=1
    fi
    exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

# A second start must not attach another session whose exit could stop the first.
umask 077
exec 9>"$config_dir/session.lock"
if ! flock -n 9; then
    printf 'A Luna Windows desktop session is already running.\n' >&2
    exit 1
fi
running=$("${compose[@]}" ps --status running -q windows)
if [[ -z $running ]]; then
    # Start may use the installed image, but must never download or build one.
    "${compose[@]}" up -d --pull never --no-build windows
fi
vm_started=true
printf 'Waiting for Windows to boot (up to %ss)...\n' "$wait_seconds"
bash "$(dirname -- "$0")/wait-ready.sh" "$compose_file" "$wait_seconds"
rdp_ready=true

# FreeRDP receives credentials over stdin, never through process arguments.
# A realm-less configuration avoids irrelevant Kerberos discovery for the local account.
export KRB5_CONFIG="$config_dir/krb5.conf"
xfreerdp3 /args-from:stdin <"$rdp_arguments" &
rdp_pid=$!
result=0
wait "$rdp_pid" || result=$?
rdp_pid=
exit "$result"
