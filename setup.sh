#!/usr/bin/env bash
# grif-cad — one-shot installer for macOS (Apple Silicon).
#
# Installs every "bit" needed to run the talking CAD assistant:
#   Claude Code (the brain) · OpenSCAD + OrcaSlicer (CAD/slice) ·
#   Colima + docker + compose (open-source container runtime) ·
#   a Python 3.12 venv with the CAD + bridge deps · local config.
#
# Idempotent: safe to re-run. The two steps it CAN'T automate (Claude login and,
# optionally, your printer's address) are printed at the end. See INSTALL.md.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
cd "$here"

say()  { printf "\n\033[1;36m==> %s\033[0m\n" "$1"; }
ok()   { printf "  \033[32m✓\033[0m %s\n" "$1"; }
warn() { printf "  \033[33m!\033[0m %s\n" "$1"; }

# --- platform guard ---
if [ "$(uname)" != "Darwin" ]; then
  echo "This installer targets macOS (Apple Silicon). Windows support is planned — see INSTALL.md." >&2
  exit 1
fi

# --- Homebrew ---
say "Homebrew"
if ! command -v brew >/dev/null 2>&1; then
  warn "Homebrew not found — installing it (you'll be asked for your Mac password)…"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  eval "$(/opt/homebrew/bin/brew shellenv)" 2>/dev/null || true
fi
ok "brew $(brew --version | head -1 | awk '{print $2}')"

brew_cask()    { brew list --cask "$1"    >/dev/null 2>&1 && ok "$1 (already)" || { warn "installing $1…"; brew install --cask "$1"; }; }
brew_formula() { brew list --formula "$1" >/dev/null 2>&1 && ok "$1 (already)" || { warn "installing $1…"; brew install "$1"; }; }

# --- apps & tools ---
say "Claude Code, CAD apps, Docker runtime, uv"
brew_cask claude-code
brew_cask openscad@snapshot     # Apple-Silicon-native build (the plain 'openscad' cask is an old Intel one)
brew_cask orcaslicer           # drives headless slicing + the "Open in OrcaSlicer" button
brew_cask creality-print       # the "Open in Creality Print" button (GUI; pick your default via SLICER_DEFAULT)
brew_formula colima
brew_formula docker
brew_formula docker-compose
brew_formula uv

# --- make `docker compose` find the brew plugin; drop a dead cred helper if present ---
say "Docker compose wiring"
python3 - <<'PY'
import json, pathlib, shutil
p = pathlib.Path.home()/".docker"/"config.json"
p.parent.mkdir(exist_ok=True)
cfg = {}
if p.exists():
    try: cfg = json.loads(p.read_text() or "{}")
    except Exception: cfg = {}
dirs = set(cfg.get("cliPluginsExtraDirs", []))
dirs.add("/opt/homebrew/lib/docker/cli-plugins")
cfg["cliPluginsExtraDirs"] = sorted(dirs)
cs = cfg.get("credsStore")
if cs and not shutil.which(f"docker-credential-{cs}"):
    cfg.pop("credsStore", None)   # avoids image-pull failures when the helper isn't installed
p.write_text(json.dumps(cfg, indent=2))
print("  done")
PY
ok "~/.docker/config.json"

# --- Python venv + deps ---
say "Python 3.12 venv + CAD/bridge dependencies"
[ -x ".venv/bin/python" ] || uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
ok "venv ready ($(.venv/bin/python --version))"

# --- local config from examples ---
say "Local config"
for name in printer bridge repos; do
  ex="config/${name}.env.example"; cf="config/${name}.env"
  if [ -f "$ex" ] && [ ! -f "$cf" ]; then cp "$ex" "$cf"; ok "created $cf (edit it)"; else ok "$cf"; fi
done

# --- executables + start the engine so first launch is smooth ---
chmod +x scripts/*.sh bridge/run.sh setup.sh 2>/dev/null || true
say "Starting Colima (open-source docker engine)"
colima status >/dev/null 2>&1 || colima start
ok "colima running"

cat <<'NEXT'

──────────────────────────────────────────────────────────────────────
  Two manual steps left (they need your login / a browser):

  1) Sign in to Claude Code and mint a durable token:
       claude               # log in once — uses your Claude Pro/Max plan
       claude setup-token   # paste the token into config/bridge.env
                            #   (CLAUDE_CODE_OAUTH_TOKEN=...)

  2) (optional) If you have the Creality K2 Plus, set its address:
       open config/printer.env   →   K2_PLUS_HOST=<printer-ip>

  3) (optional) Search Thingiverse for existing models — add a free token:
       https://www.thingiverse.com/developers/apps  →  config/repos.env (THINGIVERSE_TOKEN=)

  Then start everything:
       bash scripts/start.sh
       open http://localhost:3000     # pick the "grif-cad" model and chat / talk

  Full guide + troubleshooting:  INSTALL.md
──────────────────────────────────────────────────────────────────────
NEXT
