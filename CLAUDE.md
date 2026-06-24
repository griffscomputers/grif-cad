# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What grif-cad is

A Claude Code **harness for a CAD → slice → print pipeline** — a home workshop project. This session is the orchestrator: turn an idea into a printable part, slice it, and (with explicit human confirmation) send it to the printer. The hard part of this project is **not** orchestration — it is getting dimensionally-correct, printable geometry out of the CAD step. Concentrate iteration there; do not over-build the harness to compensate.

Target hardware: **Creality K2 Plus** — CoreXY, **350 × 350 × 350 mm** build volume, 0.4 mm nozzle (max **350 °C**), textured-PEI flex plate, optional CFS multi-material unit. Firmware is **Klipper-based (Creality OS)** with **Moonraker + Fluidd built in** at `http://<printer-ip>:4408`.

This is a self-contained subproject in the `~/Documents/Code` workspace and its own git repo. The workspace `CLAUDE.md` one level up also applies — Plan Mode default, subagent strategy, lessons loop, verification-before-done.

## The pipeline (prototype → production → print)

Units are **millimeters, always.** Each part gets a `<slug>`; all artifacts for it live under that slug.

| Stage | Tool | Output | When |
|---|---|---|---|
| 0 · Spec | — | function, key dims, material, tolerances | always first — pin dimensions before modeling |
| 1 · Prototype | **OpenSCAD** | `out/<slug>/proto.stl` | default start: fast, parametric, form/fit checks |
| 2 · Production | **CadQuery** | `out/<slug>/prod.stl` + `prod.step` | tolerances, assemblies, fillets/lofts, STEP archive, data-driven geometry |
| 3 · Scan-assist | **pymeshlab** | `scans/clean/<slug>.ply` | reverse-engineer an existing object; feeds stage 1/2 |
| 4 · Slice | **OrcaSlicer CLI** | `out/<slug>/<slug>.gcode` | K2 Plus profile |
| 5 · Print | **Moonraker API** | physical part | **requires explicit human confirmation** |
| 6 · Verify | calipers + `tasks/lessons.md` | measured deltas → model fixes | close the ralph loop |

### CAD engine selection rule
- **OpenSCAD** — simple extrusions/booleans with a few parameters → quick prototypes.
- **CadQuery** — dimensional tolerances/fits, STEP output (archive/CAM), fillets/chamfers/sweeps/lofts, multi-part assemblies, or geometry generated from data.
- Promotion prototype→production is deliberate: port to CadQuery only once a prototype passes a fit/form check and is committed to as a real part. A genuinely simple parametric part can stay in OpenSCAD.

## Skills (the knowledge layer)

Procedure lives in `.claude/skills/` — invoke as slash commands or let them fire by relevance:
- **`/cad-scripting`** — OpenSCAD + CadQuery conventions, headless render/export, printability rules. Highest-value skill; this is the weak link in the chain.
- **`/scan-cleanup`** — 3D-scan mesh repair via pymeshlab (load → normals → Poisson → decimate → export).
- **`/slice`** — OrcaSlicer headless CLI with the K2 Plus profile.
- **`/print`** — Moonraker upload + start to the K2 Plus, with the safety gate.

## Safety — physical machine

A print is a real-world action with fire/mechanical risk. **Never auto-start a print.** Before stage 5, show the human: file + slug, estimated time + filament, material, nozzle/bed temps, and "is the bed clear and the plate seated?" — then wait for an explicit go. Do not emit raw G-code that heats or moves axes without the same confirmation. Reject/warn on models exceeding the **350³ mm** build volume or nozzle **> 350 °C**. Stock bed max temp is **unverified** — confirm on the unit before high-temp materials.

## Architecture decisions (start simple, promote on evidence)

Decomposition heuristic: knowledge → **Skill**, context → **subagent**, capability → **MCP server**; build the cheapest artifact that moves the axis.
- **No MCP servers yet** — Bash runs OpenSCAD/CadQuery/OrcaSlicer and `curl`s Moonraker directly. Promote to a Moonraker MCP only when free-form curl gets error-prone.
- **No subagents yet** — add a scan-processing subagent when point-cloud iteration starts polluting main context.
- **Interactive CLI, not the Agent SDK** — graduate to the SDK only for unattended/embedded runs.

## Web / voice front end (Open WebUI → headless Claude Code)
A browser chat (microphone + inline renders) for non-CLI use — see `bridge/README.md` and `deploy/docker-compose.yml`.
- **Open WebUI** runs in Docker (Colima — open-source engine; `colima start`) at `http://localhost:3000`, pre-wired to the bridge.
- **`bridge/`** (host, FastAPI :8765) exposes an OpenAI-compatible API and runs this harness via **headless `claude -p`** — reusing these same skills, `render.sh`, and the print gate, not a reimplementation. Auth is the **Claude subscription** (`CLAUDE_CODE_OAUTH_TOKEN`), not an API key. Default model **sonnet**.
- Rendered PNGs are served at `:8765/files/*` and attached to replies as inline images (image URLs use `localhost`; the OpenWebUI→bridge API connection uses `host.docker.internal`).
- Each reply also offers **🔄 Spin it around** (three.js STL viewer at `:8765/view/<model>`) and **🛠 Open in OrcaSlicer** (`:8765/slicer/open` launches the slicer on the host). `render.sh` exports an `.stl` beside the PNGs.
- **Safety holds through the UI:** the bridge's `--allowedTools` allowlist covers render/slice but **not** the printer; `print.sh`/Moonraker stays human-only. Never `--dangerously-skip-permissions`.

## Layout
- `models/openscad/` — `.scad` sources · `models/cadquery/` — `.py` sources
- `profiles/` — OrcaSlicer machine/process/filament JSON for the K2 Plus
- `scans/raw/` (gitignored) raw scanner output · `scans/clean/` cleaned meshes
- `out/` (gitignored) — generated STL/STEP/G-code
- `scripts/` — pipeline helpers: `render.sh` (preview PNGs), `clean_scan.py`, `slice.sh`, `print.sh`
- `bridge/` — OpenAI-compatible front end over headless Claude Code (`app.py`, `run.sh`)
- `deploy/docker-compose.yml` — Open WebUI container
- `config/printer.env` · `config/bridge.env` (both gitignored; copy from `.example`) — `K2_PLUS_HOST` · `CLAUDE_CODE_OAUTH_TOKEN`
- `tasks/lessons.md` — corrections + measured-vs-modeled deltas (review at session start)

## Open items to verify on real hardware
- Whether Moonraker upload/print-start works **without rooting** on this firmware build (root fallback: on-printer Settings → Root account information; creds `root` / `creality_2024`).
- Exact stock **bed max temp**.
- Pin **CadQuery to Python 3.12** (3.13 wheels unverified).
- OrcaSlicer K2 Plus profile: confirm the **CFS filament-change G-code** before any multicolor print.
