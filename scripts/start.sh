#!/usr/bin/env bash
# grif-cad — start the talking assistant: docker engine + Open WebUI + the bridge.
# Run this each time you want to use it. Ctrl+C stops the bridge (the web UI keeps running;
# use scripts/stop.sh to shut that down too).
set -euo pipefail
proj="$(cd "$(dirname "$0")/.." && pwd)"
cd "$proj"

echo "==> Starting Colima (docker engine)…"
colima status >/dev/null 2>&1 || colima start

echo "==> Starting Open WebUI…"
docker compose -f deploy/docker-compose.yml up -d

echo
echo "==> Open the assistant at:  http://localhost:3000   (pick the 'grif-cad' model)"
echo "==> Starting the bridge — leave this window open. Press Ctrl+C to stop."
echo
exec bash bridge/run.sh
