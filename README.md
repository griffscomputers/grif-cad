# grif-cad

A Claude Code harness for a home **CAD → slice → print** pipeline, targeting a Creality K2 Plus. Describe a part, prototype it in OpenSCAD or build it in CadQuery, clean a 3D scan into a reference, slice with OrcaSlicer, and print over Moonraker — with a human confirmation gate before any physical print.

## Branches
- **`main`** — the stable branch. Clone or fork this one.
- **`dev`** — where changes land first; promoted to `main` only after
  `scripts/stack.sh check --deep` passes on real hardware. PRs should target `dev`.

## Quick start (fork & run)
One command installs everything — Claude Code, OpenSCAD, OrcaSlicer, the open-source Docker
runtime, the Python stack, and local config (macOS Apple Silicon):
```bash
git clone https://github.com/griffscomputers/grif-cad.git && cd grif-cad
bash setup.sh
```
Then sign in once (`claude` + `claude setup-token` → `config/bridge.env`) and launch:
```bash
bash scripts/start.sh      # then open http://localhost:3000
```
Full walkthrough + troubleshooting: **[INSTALL.md](INSTALL.md)**.
Want to clone the voice, reskin it, or fork the whole assistant into your own? **[docs/MAKE-IT-YOURS.md](docs/MAKE-IT-YOURS.md)**.

## Two ways to use it
- **Browser / voice app** — `scripts/start.sh` → http://localhost:3000. Type or **speak** a
  request, watch it render, and hear it **talk back in a cloned voice** (fully local — see
  the voice section of `INSTALL.md`). Built to be friendly for a non-CLI user (a kid).
  Open WebUI → the bridge → headless Claude Code; see `bridge/README.md`.
- **Inside Claude Code** — the skills drive each stage directly: `/cad-scripting`,
  `/scan-cleanup`, `/slice`, `/print`. See `CLAUDE.md` for the pipeline, engine-selection rule, and safety rules.

## Manual setup
Prefer to wire it up by hand (macOS)? `setup.sh` runs all of this for you, but the pieces are:
```bash
# apps + tools (both slicers)
brew install --cask claude-code openscad@snapshot orcaslicer creality-print
brew install colima docker docker-compose uv
# python stack
uv venv --python 3.12 .venv && uv pip install -r uv.lock   # lockfile = reproducible
# local config
cp config/printer.env.example config/printer.env   # set K2_PLUS_HOST
cp config/bridge.env.example  config/bridge.env     # set CLAUDE_CODE_OAUTH_TOKEN, SLICER_DEFAULT
openssl rand -hex 32                                # -> BRIDGE_TOKEN (auth for the bridge)
```
Then export the K2 Plus presets from OrcaSlicer into `profiles/`.

## Security
This runs an AI agent with **filesystem write access and a shell allowlist on your
machine**, and the bridge listens on your network. `setup.sh` generates a
`BRIDGE_TOKEN` so `/v1/*` is authenticated by default — do not expose port 8765 to
an untrusted network, and never add the printer path to the tool allowlist.
Read **[SECURITY.md](SECURITY.md)** before running it anywhere shared.

Physical printing is deliberately human-gated: the web UI can model, render and
slice, but starting a print is always an explicit person's decision.

## License
[MIT](LICENSE).
