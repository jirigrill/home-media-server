#!/usr/bin/env bash
# FlareSolverr occasionally leaves Chromium processes behind after failed
# requests. They keep burning CPU until the container is restarted.
# Restart the container when a browser process outlives any plausible request.
#
# Installed by `make install-flaresolverr-guard` (script + /etc/cron.d entry).
set -euo pipefail

STALE_SECONDS=${STALE_SECONDS:-600}

docker inspect -f '{{.State.Running}}' flaresolverr 2>/dev/null | grep -qx true || exit 0

stale=$(docker top flaresolverr -o pid,etimes,comm 2>/dev/null \
    | awk -v max="$STALE_SECONDS" 'NR > 1 && $2 + 0 > max && $3 ~ /^(chromium|chrome|firefox)$/ {print $1; exit}')

if [ -n "$stale" ]; then
    logger -t flaresolverr-guard "stale browser pid $stale detected; restarting flaresolverr"
    docker restart flaresolverr >/dev/null
fi
