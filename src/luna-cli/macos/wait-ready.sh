#!/usr/bin/env bash
# A VNC protocol response means the console is ready, not that macOS is installed.
set -euo pipefail
compose_file=$1
wait_seconds=$2
compose=(docker compose --project-name luna-macos --file "$compose_file")
deadline=$((SECONDS + wait_seconds))

while true; do
    container=$("${compose[@]}" ps --status running -q macos)
    if [[ -z $container ]]; then
        printf 'macOS container stopped. Check luna macos logs.\n' >&2
        exit 1
    fi
    if timeout 2 bash "$(dirname -- "$0")/vnc-ready.sh" 2>/dev/null; then
        exit 0
    fi
    if ((SECONDS >= deadline)); then
        printf 'macOS console is not ready yet; the VM remains running. Watch http://127.0.0.1:8007 or luna macos logs.\n' >&2
        exit 1
    fi
    sleep 2
done
