# grif-cad

A Claude Code harness for a home **CAD → slice → print** pipeline, targeting a Creality K2 Plus. Describe a part, prototype it in OpenSCAD or build it in CadQuery, clean a 3D scan into a reference, slice with OrcaSlicer, and print over Moonraker — with a human confirmation gate before any physical print.

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

## Two ways to use it
- **Browser / voice app** — `scripts/start.sh` → http://localhost:3000. Type or **speak** a
  request and watch it render. Built to be friendly for a non-CLI user (a kid). Open WebUI →
  the bridge → headless Claude Code; see `bridge/README.md`.
- **Inside Claude Code** — the skills drive each stage directly: `/cad-scripting`,
  `/scan-cleanup`, `/slice`, `/print`. See `CLAUDE.md` for the pipeline, engine-selection rule, and safety rules.

## Manual setup
Prefer to wire it up yourself? Install OpenSCAD + OrcaSlicer, create a Python 3.12 venv and
`uv pip install -r requirements.txt`, `cp config/printer.env.example config/printer.env` (set
`K2_PLUS_HOST`), and export the K2 Plus presets from OrcaSlicer into `profiles/`.
