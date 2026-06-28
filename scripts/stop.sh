#!/usr/bin/env bash
# grif-cad — stop the assistant (bridge + Open WebUI). Thin wrapper over scripts/stack.sh.
set -euo pipefail
exec "$(cd "$(dirname "$0")" && pwd)/stack.sh" stop
