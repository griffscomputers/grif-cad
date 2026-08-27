# Security model

`grif-cad` runs an **AI agent with filesystem write access and a shell allowlist on
your own machine**, plus an optional connection to a 3D printer on your LAN. That is
the point of the project, but it means the trust model matters. Read this before
exposing any part of it beyond your own computer.

## What the harness is allowed to do

The bridge (`bridge/app.py`) runs headless Claude Code with an explicit
`--allowedTools` allowlist (`allowed_tools()`). It permits:

- `Read` / `Edit` / `Write` / `Glob` / `Grep` inside the project directory
- a fixed set of Bash prefixes: `scripts/render.sh`, `scripts/project.sh`,
  `scripts/slice.sh`, `scripts/find_model.py`, `openscad`, the project venv Python,
  and `mkdir` / `ls` / `cat` / `cp`

It runs with `--permission-mode acceptEdits`, so file edits inside the project are
not individually confirmed.

**It never runs with `--dangerously-skip-permissions`.** If you find that flag in a
fork, that fork is not this project's security model.

## The printer is deliberately human-gated

`scripts/print.sh` and any direct Moonraker call are **excluded from the allowlist**.
A print is a real-world action with fire and mechanical risk, so starting one is
always an explicit human decision, including through the web UI. Do not add the
printer path to `allowed_tools()`.

There is a regression test for this (`tests/test_bridge.py`). If you change the
allowlist, that test is the thing standing between you and an agent that can turn on
a heater.

## Network exposure

Two host services listen on your machine:

| Service | Port | Auth | Notes |
|---|---|---|---|
| Bridge (Claude Code front end) | 8765 | **Bearer token** | `BRIDGE_TOKEN` in `config/bridge.env` |
| Voice / TTS (Chatterbox) | 8004 | **none** | see the known limitation below |

The bridge binds `0.0.0.0` by default because the Open WebUI container reaches it
over `host.docker.internal`, which does not arrive on loopback. Access is controlled
by the token instead of the bind address:

- `setup.sh` generates a random `BRIDGE_TOKEN` on first run.
- Any request to `/v1/*` without a matching `Authorization: Bearer` header gets a
  **401**. `/healthz` stays open so the health check works.
- If you delete `BRIDGE_TOKEN`, the bridge starts **unauthenticated** and logs a loud
  warning. Only do that on a machine you fully trust.
- To bind loopback-only anyway (CLI use with no Docker UI), set `BRIDGE_HOST=127.0.0.1`
  in `config/bridge.env`. This will stop the browser UI from reaching the bridge.

**Do not port-forward 8765 to the internet.** An unauthenticated caller who reaches
it gets an AI agent with write access to your files, billed to your Claude
subscription.

### Known limitation: the voice port is unauthenticated

The Chatterbox TTS server (`:8004`) binds `0.0.0.0` with no auth, because Open WebUI
calls it directly as an OpenAI-compatible audio endpoint. Anyone on your LAN can make
it synthesize speech. There is **no code execution and no billing** on that path, so
it is treated as low severity, but it is real: on an untrusted network, set
`VOICE_ENABLED=0` in `config/voice.env` or firewall the port.

`WEBUI_AUTH=false` in `deploy/docker-compose.yml` likewise disables the Open WebUI
login wall, which is intentional for a single-user home kiosk. Set it to `true` if
the machine is shared.

## Secrets

`config/*.env` is gitignored; only `*.env.example` and the secret-free
`config/voice.env` are tracked. `CLAUDE_CODE_OAUTH_TOKEN` and `BRIDGE_TOKEN` live in
`config/bridge.env` and must never be committed. Cloned-voice reference WAVs in
`voice/reference_audio/` are also gitignored — a cloned real person's voice is
personal-use only.

## Reporting a problem

This is a personal home project, not a supported product. If you find a security
issue, please open a GitHub issue describing the impact. Do not include working
exploit payloads that target other people's installations.
