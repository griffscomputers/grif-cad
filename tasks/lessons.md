# grif-cad lessons

Ralph-loop memory for the CAD→slice→print pipeline. **Review at session start.** Append after any correction, failed print, or measured-vs-modeled discrepancy. Per the workspace lessons-routing rule, project-specific lessons stay here; promote a cross-cutting Claude Code lesson to `../tasks/lessons.md` (workspace root) only if it would apply to another subproject.

## Format
`YYYY-MM-DD — <what went wrong / what was measured> → <rule for next time>`

## Calibration log (measured vs modeled)
Track real-world deltas so tolerances stop being guesses — the dimensional-accuracy feedback loop is where this project's iterations should concentrate.

| date | part | feature | modeled (mm) | measured (mm) | delta | fix |
|---|---|---|---|---|---|---|

## Lessons

### Project organization (per-part folders + catalog)
- 2026-06-29 — **Each part now owns a folder `projects/<slug>/`** holding all its files (source, renders, STL/STEP, G-code, data), gitignored; the repo tracks only `projects/index.tsv` (the catalog) + `projects/README.md`. Manage via `scripts/project.sh` (`new`/`ls`/`show`/`render`/`reindex`/`path`/`rm`). The slug *is* the identity — files are named `<slug>.*`. `slice.sh`/`print.sh` resolve `projects/<slug>/` and fall back to legacy `out/<slug>/`. → Start parts with `project.sh new <slug>`; "go back to <part>" = `project.sh show <slug>`. Don't put part sources back under `models/` or check artifacts into git.
- 2026-06-29 — **macOS ships bash 3.2 — no `declare -A`.** `project.sh reindex` first used bash associative arrays and died with `declare: -A: invalid option` under `/usr/bin/env bash`. → Do map/merge work in **awk** (native assoc arrays, version-independent); discriminate the two input files by `FILENAME==FACTS` (not `NR==FNR`, which misfires when the first file is empty).
- 2026-06-29 — **Bridge rewired to `projects/<slug>/` (done).** `bridge/app.py` now mounts `/files` on `projects/` and serves nested `/files/<slug>/<file>`, scans `projects/*/*.png`, keys model identity on the slug (folder name), and `ensure_stl` exports from `projects/<slug>/<slug>.{scad,py}` (CadQuery `.py` runs to export). `render.sh`'s default outdir is now the model's own folder, so `render.sh projects/<slug>/<slug>.scad` lands PNGs+STL in place. Persona + `--allowedTools` updated (added `project.sh`). The bridge has **no `--reload`**, so code changes need `scripts/stack.sh restart`. → **Still pending:** `/find-model` downloads to `models/downloads/` and renders to a non-`projects/` dir, so find-model results don't surface in the chat UI — relocate its download/render into `projects/<slug>/` next.

### Web/voice bridge (Open WebUI → headless Claude Code)
- 2026-06-24 — **Stream died on image reads** (Open WebUI showed `TransferEncodingError: Not enough data to satisfy transfer length header`). `claude -p --output-format stream-json` emits one JSON object *per line*; a line carrying a read image exceeds asyncio's 64 KiB readline default → `ValueError: Separator is not found, and chunk exceed the limit` → the SSE generator crashes mid-stream. → Pass a large `limit=` (we use 16 MiB) to `asyncio.create_subprocess_exec`, and wrap any SSE generator so it always emits a final stop chunk + `[DONE]` even on error — never let it truncate the HTTP response.
- 2026-06-24 — **Images didn't appear even when renders already existed.** The bridge only attached previews whose mtime *changed* that turn, so "show me the existing renders" surfaced nothing. → Also surface preview PNGs the assistant *reads* this turn (track `Read` tool_use on `out/preview/*.png`), not just re-rendered ones. Image URLs must use `localhost:8765` (the browser runs on the host); `host.docker.internal` only resolves *inside* the container and is for the API connection. Base64-inline images render buggily in Open WebUI — serve URLs.
- 2026-06-24 — **`--allowedTools` wildcard syntax.** `Bash(bash scripts/render.sh *)` (space-star) does NOT match — render was blocked. → Use `Bash(prefix:*)` (colon-star), and cover the cwd-relative forms the agent actually uses (`bash scripts/render.sh:*`, `scripts/render.sh:*`) since `claude -p` runs with cwd=project root. Keep `print.sh`/Moonraker OUT of the allowlist so the physical-print gate holds through the UI.
- 2026-06-24 — **Headless billing.** `claude -p` uses the logged-in **subscription** when no `ANTHROPIC_API_KEY` is set; setting that env var silently forces metered API billing. → The bridge unsets `ANTHROPIC_API_KEY` and relies on `CLAUDE_CODE_OAUTH_TOKEN` (`claude setup-token`). Default model `sonnet`, not Opus, to spare plan quota.

### Toolchain / install (macOS Apple Silicon)
- 2026-06-24 — **OpenSCAD stable cask is ancient.** `brew install --cask openscad` installs the 2021.01 Intel build, which macOS kills on launch (`Killed: 9`) under Rosetta. → Use `brew install --cask openscad@snapshot` (arm64-native, current). `render.sh` globs `/Applications/OpenSCAD*.app` for the binary.
- 2026-06-24 — **Removing OrbStack breaks Docker.** A stale `credsStore: osxkeychain` left in `~/.docker/config.json` points at OrbStack's now-missing helper → image pulls fail (`docker-credential-osxkeychain not found`); and brew's `docker` CLI needs `cliPluginsExtraDirs` for `docker compose` to resolve. → `setup.sh` fixes both (drops a `credsStore` whose helper isn't on PATH; adds the brew cli-plugins dir). `host.docker.internal` works on Colima/Lima for container→host (the earlier worry was unfounded).

### Slicers
- 2026-06-24 — **OrcaSlicer vs Creality Print.** Only OrcaSlicer is reliably scriptable on macOS (headless `--slice` CLI; ships built-in K2 Plus profiles). Creality Print (v7.1, an Orca fork) has a CLI but it's undocumented + crash-prone on Mac → treat as **open-in-GUI only** (`open -a "Creality Print" <file>`). Profiles use **incompatible variable names** despite shared lineage — NOT interchangeable; keep them as separate profile worlds. → Slicer choice is a per-person preference governing the GUI-launch button (both shown; `SLICER_DEFAULT` orders them); headless `/slice` stays OrcaSlicer; printing is slicer-agnostic (Moonraker). Neither has a headless network-print CLI.
- 2026-06-24 — **No xvfb on macOS.** `xvfb-run` is Linux-only — the slice path must call the OrcaSlicer bundle binary directly on Mac (`/Applications/OrcaSlicer.app/Contents/MacOS/OrcaSlicer`). `scripts/slice.sh` now adds `xvfb-run` only when `uname` = Linux.
