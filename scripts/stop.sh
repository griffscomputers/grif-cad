#!/usr/bin/env bash
# grif-cad — stop the web UI. (Stop the bridge with Ctrl+C in its own window.)
set -euo pipefail
proj="$(cd "$(dirname "$0")/.." && pwd)"
docker compose -f "$proj/deploy/docker-compose.yml" down
echo "Open WebUI stopped."
echo "To stop the docker engine as well:  colima stop"
