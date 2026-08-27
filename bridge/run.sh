#!/usr/bin/env bash
# Launch the grif-cad bridge: an OpenAI-compatible front end over headless Claude Code.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
proj="$(cd "$here/.." && pwd)"

# Load config if present.
if [ -f "$proj/config/bridge.env" ]; then
  set -a; . "$proj/config/bridge.env"; set +a
else
  echo "note: no config/bridge.env — copy config/bridge.env.example and set CLAUDE_CODE_OAUTH_TOKEN." >&2
fi

# Subscription path only — never let a stray API key force metered billing.
unset ANTHROPIC_API_KEY
if [ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
  echo "note: CLAUDE_CODE_OAUTH_TOKEN not set — relying on the existing 'claude' login." >&2
  echo "      Run 'claude setup-token' for a durable token when running this as a service." >&2
fi

# The bridge is an AI agent with write access — an open port is a real hole.
# BRIDGE_TOKEN is the control (Open WebUI sends it as its OpenAI key); the bind
# address is NOT, because the Open WebUI container reaches us over
# host.docker.internal, which does not arrive on loopback. See SECURITY.md.
if [ -z "${BRIDGE_TOKEN:-}" ]; then
  echo "WARNING: BRIDGE_TOKEN is not set — /v1/* is UNAUTHENTICATED." >&2
  echo "         Anyone who can reach ${BRIDGE_HOST:-0.0.0.0}:${PORT:-8765} gets an agent" >&2
  echo "         with write access to this repo, on your Claude subscription." >&2
  echo "         Fix: set BRIDGE_TOKEN in config/bridge.env (see SECURITY.md)." >&2
fi

export PROJECT_DIR="$proj"
exec "$proj/.venv/bin/python" -m uvicorn app:app \
  --host "${BRIDGE_HOST:-0.0.0.0}" --port "${PORT:-8765}" --app-dir "$here"
