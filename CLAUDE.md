# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What grif-cad is

A Claude Code **harness for a CAD → slice → print pipeline** — a home workshop project. This session is the orchestrator: turn an idea into a printable part, slice it, and (with explicit human confirmation) send it to the printer. The hard part of this project is **not** orchestration — it is getting dimensionally-correct, printable geometry out of the CAD step. Concentrate iteration there; do not over-build the harness to compensate.

Target hardware: **Creality K2 Plus** — CoreXY, **350 × 350 × 350 mm** build volume, 0.4 mm nozzle (max **350 °C**), textured-PEI flex plate, optional CFS multi-material unit. Firmware is **Klipper-based (Creality OS)** with **Moonraker + Fluidd built in** at `http://<printer-ip>:4408`.

This is a self-contained subproject in the `~/Documents/Code` workspace and its own git repo. The workspace `CLAUDE.md` one level up also applies — Plan Mode default, subagent strategy, lessons loop, verification-before-done.

## The pipeline (prototype → production → print)

Units are **millimeters, always.** Each part gets a `<slug>` and **its own folder `projects/<slug>/`** holding *every* file it produces (source, renders, STL/STEP, G-code, data). Those folders are **gitignored**; the repo tracks only the catalog `projects/index.tsv`. Create/list/recall parts with `scripts/project.sh` (`new` / `ls` / `show` / `render` / `reindex`). See `projects/README.md`.

| Stage | Tool | Output | When |
|---|---|---|---|
| 0 · Spec | — | function, key dims, material, tolerances | always first — pin dimensions before modeling |
| 1 · Prototype | **OpenSCAD** | `projects/<slug>/<slug>.stl` | default start: fast, parametric, form/fit checks |
| 2 · Production | **CadQuery** | `projects/<slug>/<slug>.stl` + `.step` | tolerances, assemblies, fillets/lofts, STEP archive, data-driven geometry |
| 3 · Scan-assist | **pymeshlab** | `scans/clean/<slug>.ply` | reverse-engineer an existing object; feeds stage 1/2 |
| 4 · Slice | **OrcaSlicer CLI** | `projects/<slug>/<slug>.gcode` | K2 Plus profile |
| 5 · Print | **Moonraker API** | physical part | **requires explicit human confirmation** |
| 6 · Verify | calipers + `tasks/lessons.md` | measured deltas → model fixes | close the ralph loop |

**Reuse before building:** before stage 1, consider `/find-model` to pull an existing design (license-aware) instead of modeling from scratch.

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
- **`/find-model`** — search for an existing printable model before building from scratch: auto-searches Thingiverse (license-aware, downloads to `models/downloads/`), plus browser search links for Creality Cloud / MakerWorld / Printables / Cults3D. Needs a free `THINGIVERSE_TOKEN` (`config/repos.env`); Creality Cloud is also reachable inside Creality Print.

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
- **`bridge/`** (host, FastAPI :8765) exposes an OpenAI-compatible API and runs this harness via **headless `claude -p`** — reusing these same skills, `render.sh`, and the print gate, not a reimplementation. Auth is the **Claude subscription** (`CLAUDE_CODE_OAUTH_TOKEN`), not an API key. Model routing: **sonnet** by default, auto-escalating to **opus** for hard jobs (assemblies/tolerances/complex geometry; `GRIFCAD_AUTOROUTE`, with `use opus`/`use sonnet` as a per-message override).
- Rendered PNGs are served at `:8765/files/*` and attached to replies as inline images (image URLs use `localhost`; the OpenWebUI→bridge API connection uses `host.docker.internal`).
- Each reply also offers **🔄 Spin it around** (three.js STL viewer at `:8765/view/<model>`) and a per-person **Open in <slicer>** launcher — both OrcaSlicer and Creality Print buttons show; `SLICER_DEFAULT` lists the preferred one first. Headless `/slice` always uses OrcaSlicer (the only reliably scriptable slicer on macOS); Creality Print is open-in-GUI only and its profiles are a separate world (not interchangeable with Orca). `render.sh` exports an `.stl` beside the PNGs.
- **Safety holds through the UI:** the bridge's `--allowedTools` allowlist covers render/slice but **not** the printer; `print.sh`/Moonraker stays human-only. Never `--dangerously-skip-permissions`.

## Layout
- `projects/<slug>/` (gitignored) — **one folder per part**: source (`.scad`/`.py`), renders, STL/STEP, G-code, data. The repo tracks only `projects/index.tsv` (catalog) + `projects/README.md`; manage with `scripts/project.sh`.
- `profiles/` — OrcaSlicer machine/process/filament JSON for the K2 Plus
- `scans/raw/` (gitignored) raw scanner output · `scans/clean/` cleaned meshes
- `out/` (gitignored) — scratch/legacy generated artifacts; the **web bridge still renders previews to `out/preview/`** (moving it to write into `projects/<slug>/` is a tracked follow-up — see `tasks/lessons.md`)
- `scripts/` — pipeline helpers: `project.sh` (per-part folders + catalog), `render.sh` (preview PNGs), `clean_scan.py`, `slice.sh`, `print.sh`, `stack.sh` (web stack control)
- `bridge/` — OpenAI-compatible front end over headless Claude Code (`app.py`, `run.sh`)
- `deploy/docker-compose.yml` — Open WebUI container
- `config/printer.env` · `config/bridge.env` (both gitignored; copy from `.example`) — `K2_PLUS_HOST` · `CLAUDE_CODE_OAUTH_TOKEN`
- `tasks/lessons.md` — corrections + measured-vs-modeled deltas (review at session start)

## Open items to verify on real hardware
- Whether Moonraker upload/print-start works **without rooting** on this firmware build (root fallback: on-printer Settings → Root account information; creds `root` / `creality_2024`).
- Exact stock **bed max temp**.
- Pin **CadQuery to Python 3.12** (3.13 wheels unverified).
- OrcaSlicer K2 Plus profile: confirm the **CFS filament-change G-code** before any multicolor print.
