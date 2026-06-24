# grif-cad lessons

Ralph-loop memory for the CAD→slice→print pipeline. **Review at session start.** Append after any correction, failed print, or measured-vs-modeled discrepancy. Per the workspace lessons-routing rule, project-specific lessons stay here; promote a cross-cutting Claude Code lesson to `../tasks/lessons.md` (workspace root) only if it would apply to another subproject.

## Format
`YYYY-MM-DD — <what went wrong / what was measured> → <rule for next time>`

## Calibration log (measured vs modeled)
Track real-world deltas so tolerances stop being guesses — the dimensional-accuracy feedback loop is where this project's iterations should concentrate.

| date | part | feature | modeled (mm) | measured (mm) | delta | fix |
|---|---|---|---|---|---|---|

## Lessons

### Web/voice bridge (Open WebUI → headless Claude Code)
- 2026-06-24 — **Stream died on image reads** (Open WebUI showed `TransferEncodingError: Not enough data to satisfy transfer length header`). `claude -p --output-format stream-json` emits one JSON object *per line*; a line carrying a read image exceeds asyncio's 64 KiB readline default → `ValueError: Separator is not found, and chunk exceed the limit` → the SSE generator crashes mid-stream. → Pass a large `limit=` (we use 16 MiB) to `asyncio.create_subprocess_exec`, and wrap any SSE generator so it always emits a final stop chunk + `[DONE]` even on error — never let it truncate the HTTP response.
- 2026-06-24 — **Images didn't appear even when renders already existed.** The bridge only attached previews whose mtime *changed* that turn, so "show me the existing renders" surfaced nothing. → Also surface preview PNGs the assistant *reads* this turn (track `Read` tool_use on `out/preview/*.png`), not just re-rendered ones. Image URLs must use `localhost:8765` (the browser runs on the host); `host.docker.internal` only resolves *inside* the container and is for the API connection. Base64-inline images render buggily in Open WebUI — serve URLs.
- 2026-06-24 — **`--allowedTools` wildcard syntax.** `Bash(bash scripts/render.sh *)` (space-star) does NOT match — render was blocked. → Use `Bash(prefix:*)` (colon-star), and cover the cwd-relative forms the agent actually uses (`bash scripts/render.sh:*`, `scripts/render.sh:*`) since `claude -p` runs with cwd=project root. Keep `print.sh`/Moonraker OUT of the allowlist so the physical-print gate holds through the UI.
- 2026-06-24 — **Headless billing.** `claude -p` uses the logged-in **subscription** when no `ANTHROPIC_API_KEY` is set; setting that env var silently forces metered API billing. → The bridge unsets `ANTHROPIC_API_KEY` and relies on `CLAUDE_CODE_OAUTH_TOKEN` (`claude setup-token`). Default model `sonnet`, not Opus, to spare plan quota.

### Toolchain / install (macOS Apple Silicon)
- 2026-06-24 — **OpenSCAD stable cask is ancient.** `brew install --cask openscad` installs the 2021.01 Intel build, which macOS kills on launch (`Killed: 9`) under Rosetta. → Use `brew install --cask openscad@snapshot` (arm64-native, current). `render.sh` globs `/Applications/OpenSCAD*.app` for the binary.
- 2026-06-24 — **Removing OrbStack breaks Docker.** A stale `credsStore: osxkeychain` left in `~/.docker/config.json` points at OrbStack's now-missing helper → image pulls fail (`docker-credential-osxkeychain not found`); and brew's `docker` CLI needs `cliPluginsExtraDirs` for `docker compose` to resolve. → `setup.sh` fixes both (drops a `credsStore` whose helper isn't on PATH; adds the brew cli-plugins dir). `host.docker.internal` works on Colima/Lima for container→host (the earlier worry was unfounded).
