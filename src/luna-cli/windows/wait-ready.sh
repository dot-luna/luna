#!/usr/bin/env bash
# Match Omarchy's current-boot guest readiness check, then verify RDP responds.
set -euo pipefail
compose_file=$1
wait_seconds=$2
compose=(docker compose --project-name luna-windows --file "$compose_file")
deadline=$((SECONDS + wait_seconds))

while true; do
    container=$("${compose[@]}" ps --status running -q windows)
    if [[ -z $container ]]; then
        printf 'Windows container stopped. Check luna windows logs.\n' >&2
        exit 1
    fi
    started_at=$(docker inspect --format '{{.State.StartedAt}}' "$container")
    if [[ -n $started_at ]]; then
        # Capture before matching so pipefail cannot mistake grep's early exit for failure.
        logs=$("${compose[@]}" logs --no-color --since "$started_at" windows)
        if [[ ${logs,,} == *'windows started successfully'* ]] &&
            timeout 2 bash "$(dirname -- "$0")/rdp-ready.sh" 2>/dev/null; then
            exit 0
        fi
    fi
    if ((SECONDS >= deadline)); then
        printf 'Windows is not ready yet. Setup/boot remains running. Watch http://127.0.0.1:8006 or luna windows logs.\n' >&2
        exit 1
    fi
    sleep 2
done
