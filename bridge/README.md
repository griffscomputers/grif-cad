# grif-cad bridge

An OpenAI-compatible HTTP front end over **headless Claude Code**. Open WebUI (or any
OpenAI client) talks to this; it runs `claude -p` inside the grif-cad project — the full
harness (skills, `render.sh`, the print safety gate) — and streams the reply back, with
rendered preview PNGs attached as inline images.

```
Open WebUI ──/v1/chat/completions──▶ bridge ──spawns──▶ claude -p (grif-cad project)
                                       │                    └─ OpenSCAD / render.sh / venv
                                       └──/files/*.png──▶ inline previews in the chat
```

## Why headless CLI (not the Agent SDK)
`claude -p` runs the *whole* existing project unchanged and can authenticate with your
**Claude subscription** (no metered API key). The Agent SDK is API-key-metered and would
mean re-plumbing tools. A plain LLM proxy (LiteLLM) only relays chat and can't run OpenSCAD.

## Run
```bash
# 1. one-time: durable subscription token (skip if you're already logged into `claude`)
cp config/bridge.env.example config/bridge.env
claude setup-token            # paste the token into config/bridge.env (CLAUDE_CODE_OAUTH_TOKEN=)

# 2. start the bridge (host)
bash bridge/run.sh            # http://localhost:8765  (container reaches it at host.docker.internal:8765)

# 3. start Open WebUI (pre-wired to the bridge)
docker compose -f deploy/docker-compose.yml up -d
```

## Use it (browser)
1. Open **http://localhost:3000**. The **grif-cad** model is already connected — just chat ("make a 30 mm cube with a 10 mm hole"); a render appears inline.
2. **Microphone:** click the mic and speak. If it doesn't transcribe, set the engine in **Admin → Settings → Audio → Speech-to-Text** (local Whisper = offline; "Web API" = zero-download). Mic needs `localhost` (it is) or HTTPS.
3. *(optional)* Kid-friendly starters: **Admin → Settings → Interface → Default Prompt Suggestions** — e.g. "Design a phone stand", "Make a wall hook", "Build a name tag".

## Endpoints
- `GET /v1/models` — advertises the `grif-cad` model
- `POST /v1/chat/completions` — streaming (SSE) and non-streaming; runs a build, returns text + preview images + spin/slice links
- `GET /files/<name>` — serves `out/preview/*` (PNG previews and the exported `.stl`)
- `GET /view/<model>` — interactive three.js viewer (drag to orbit, scroll to zoom); exports the STL on demand. *(loads three.js from a CDN — needs internet)*
- `GET /slicer/open?model=<model>&app=<orca|creality>` — launches the chosen slicer on the host with the model (default = `SLICER_DEFAULT`); 404s with a friendly note if that slicer isn't installed
- `GET /healthz`

Each reply that shows a model appends **🔄 Spin it around** (→ `/view`) and an **Open in &lt;slicer&gt;** launcher for each slicer (OrcaSlicer + Creality Print; `SLICER_DEFAULT` first). `render.sh` exports an `.stl` next to the PNGs so they're ready.

## Config (`config/bridge.env`)
`CLAUDE_CODE_OAUTH_TOKEN` (subscription), `GRIFCAD_MODEL` (default `sonnet`), `PORT` (8765),
`PUBLIC_BASE` (browser-facing image base, default `http://localhost:8765`).

## Safety
claude runs with `--permission-mode acceptEdits` and an explicit `--allowedTools` allowlist
covering modelling/rendering/slicing but **not** the printer step (`print.sh` / Moonraker).
Starting a physical print stays a human action even through the web UI. Never add
`--dangerously-skip-permissions`.
