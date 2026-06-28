#!/usr/bin/env bash
# grif-cad — start the talking assistant (docker engine + Open WebUI + the bridge).
# Thin wrapper: the real lifecycle controller is scripts/stack.sh. The bridge now runs
# DETACHED (no window to keep open). Stop with scripts/stack.sh stop; verify with check.
set -euo pipefail
exec "$(cd "$(dirname "$0")" && pwd)/stack.sh" start
