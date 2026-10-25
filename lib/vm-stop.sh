#!/usr/bin/env bash
# Stop one Luna VM: bash <root>/lib/vm-stop.sh <compose_file> <windows|macos>.
set -euo pipefail

compose_file=${1:-}
service=${2:-}
case "$service" in
    windows)
        label=Windows
        ;;
    macos)
        label=macOS
        ;;
    *)
        printf 'Usage: bash <root>/lib/vm-stop.sh <compose_file> <windows|macos>\n' >&2
        exit 1
        ;;
esac

if [[ ! -r $compose_file ]]; then
    printf 'Cannot read %s VM configuration: %s. Restore the Compose file and retry.\n' "$label" "$compose_file" >&2
    exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
    printf 'Docker is required to stop %s. Install Docker and retry.\n' "$label" >&2
    exit 1
fi

# Include stopped containers so an old restart policy cannot revive them later.
compose=(docker compose --project-name "luna-$service" --file "$compose_file")
if ! container_ids=$("${compose[@]}" ps --all -q "$service"); then
    printf 'Cannot find the %s VM container. Check docker info and retry luna %s stop.\n' "$label" "$service" >&2
    exit 1
fi
containers=()
while IFS= read -r container; do
    if [[ -n $container ]]; then
        containers+=("$container")
    fi
done <<< "$container_ids"
if (( ${#containers[@]} == 0 )); then
    printf 'No %s VM container to stop.\n' "$label"
    exit 0
fi

# A policy update failure must not prevent the stop attempt or become a success.
result=0
if ! docker update --restart=no "${containers[@]}" >/dev/null; then
    printf 'Cannot disable automatic restart for %s. Still attempting shutdown; retry luna %s stop.\n' "$label" "$service" >&2
    result=1
fi
if ! "${compose[@]}" stop --timeout 120 "$service"; then
    printf 'Cannot stop %s. Check luna %s logs and retry luna %s stop.\n' "$label" "$service" "$service" >&2
    result=1
fi

# Verify every discovered VM container, even when an earlier operation failed.
for container in "${containers[@]}"; do
    if ! state=$(docker inspect --format '{{.State.Running}} {{.State.Restarting}} {{.HostConfig.RestartPolicy.Name}}' "$container"); then
        printf 'Cannot verify %s shutdown (%s). Check docker info and retry luna %s stop.\n' "$label" "$container" "$service" >&2
        result=1
    elif [[ $state != 'false false no' ]]; then
        printf '%s shutdown is unverified (%s: %s). Expected stopped with restart disabled; retry luna %s stop.\n' "$label" "$container" "$state" "$service" >&2
        result=1
    fi
done

if (( result == 0 )); then
    printf '%s VM stopped.\n' "$label"
fi
exit "$result"
