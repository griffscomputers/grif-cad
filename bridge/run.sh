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

export PROJECT_DIR="$proj"
exec "$proj/.venv/bin/python" -m uvicorn app:app \
  --host 0.0.0.0 --port "${PORT:-8765}" --app-dir "$here"
