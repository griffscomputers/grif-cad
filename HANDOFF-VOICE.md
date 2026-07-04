# HANDOFF-VOICE.md — Give grif-cad a cloned JARVIS voice

> Work order, planned 2026-07-04 in a workspace meta session. Execute from a Claude Code
> session launched at the grif-cad repo root (so grif-cad's own hooks/settings load).
> Suggested launch prompt:
> **"Read HANDOFF-VOICE.md and execute it top to bottom. Verify each gate before moving on."**
>
> grif-cad is the proving ground: get the voice working standalone here first; every lesson
> gets logged in `tasks/lessons.md` tagged `VOICE`, then ported to Friday
> (`~/Documents/Code/Friday/handoffs/P3-UI-M5-BRIEF.md`). The two projects stay fully
> standalone — port patterns, never share processes, venvs, or config.

## Mission

grif-cad becomes a *talking* CAD assistant — spoken replies in a custom cloned voice
(**JARVIS**, his favorite), fully local, self-contained in this repo so a fork carries
everything. This is a birthday gift: the docs matter as much as the code.

## Current state (verified 2026-07-04)

- Stack: Colima → Open WebUI container `grifcad-openwebui` (:3000) → host bridge
  `bridge/app.py` (:8765, FastAPI over headless `claude -p`). Managed by `scripts/stack.sh`.
- **No TTS anywhere in the repo** — voice today is input-only (Open WebUI mic → Whisper STT).
- Machine: Apple M5, 24 GB RAM. `ffmpeg` NOT installed; use built-in `afconvert`. `uv` present,
  Python 3.12 available. Port **8004 is free** (Friday's voice server will take **8006** — both
  run on this machine, so ports must not collide).
- Open WebUI persists audio settings in its DB volume — compose env vars only seed a *fresh*
  volume. The running container must be configured once via Admin → Settings → Audio or the
  `POST /api/v1/audio/config/update` API (this exact dual-path was proven in Friday's UI-M4).
- `main` is 3 commits ahead of origin (unpushed) — Grif's call, don't push without asking.
- Stale docs to fix while in here: `CLAUDE.md` (~line 66) and `projects/README.md` (~lines
  46-48) still call the bridge's `out/preview/` → `projects/<slug>/` rewire a pending
  follow-up; it shipped 2026-06-29 (commit `77c747e`).

## Decisions already made (do not re-litigate)

1. **Engine: Chatterbox (Resemble AI) via `devnen/Chatterbox-TTS-Server`, pinned to v2.0.0
   commit `f0afcc6d01d4424ad72950038dff66646b24bc78`.** MIT code+weights. Zero-shot cloning:
   a clean 10–30 s reference WAV in its `reference_audio/` dir *is* the voice — no training.
   Serves OpenAI-compatible `POST /v1/audio/speech`; the voice is selected per-request by
   filename via the `voice` field, so one server can host many voices.
   Supply-chain rule: skim the pinned source before installing (it's a FastAPI app — check
   `server.py`/`config.yaml` for anything phoning home; model weights come from
   ResembleAI's Hugging Face repo on first run, ~2–3 GB).
2. **Runtime: native host service with MPS** (Grif's explicit choice). Docker on macOS has no
   GPU passthrough — containerized would be CPU-only and 3–10x slower. The voice server runs
   like the bridge does: a host process managed by `stack.sh`. Compose + `.env` still drive
   all *wiring* (ports, URLs, voice name).
3. **Rejected:** Piper (no zero-shot cloning — preset/trained voices only), Coqui XTTS-v2
   (non-commercial CPML weights, project dead), voicebox/jamiepine (current release crashes
   loading models on Apple Silicon — issues #606/#615; its OpenAI endpoint is unmerged
   PR #656). Voicebox may be mentioned in docs as an optional recording *studio*, nothing more.
4. **Voice: JARVIS**, cloned from
   `/Users/grif/Downloads/JARVIS_ A Second Screen Experience - All Audio.mp3` (~14.6 min —
   audition for clean, music/SFX-free speech segments). The Kerry Condon files in Downloads
   belong to **Friday**, not grif-cad.
5. **Cloned real-person voices are personal-use only.** Reference WAVs and the cloned output
   never get pushed: gitignore `voice/reference_audio/*.wav`. The make-your-own-voice docs are
   the shareable artifact.
6. **Expected latency:** ~2–6 s per sentence on MPS. Open WebUI's `AUDIO_TTS_SPLIT_ON`
   (punctuation) pipelines sentences, so perceived start-of-speech is one sentence, not the
   whole reply. Acceptable; do not chase streaming in this pass.

## Work items (in order)

### 1. `config/voice.env` — single source of wiring truth
New env file (follow the `config/bridge.env` pattern; commit a `voice.env.example` if the real
one holds nothing secret — it doesn't, so a tracked `config/voice.env` with defaults is fine):

```
VOICE_ENABLED=1
VOICE_PORT=8004
VOICE_DEFAULT=jarvis.wav      # filename in voice/reference_audio/
WEBUI_PORT=3000               # moved here so compose is fully env-driven
BRIDGE_PORT=8765
```

`stack.sh` sources it; compose consumes it via
`docker compose --env-file config/voice.env -f deploy/docker-compose.yml …` (update every
compose invocation in `stack.sh`).

### 2. `voice/setup.sh` — idempotent engine install
- `git clone https://github.com/devnen/Chatterbox-TTS-Server voice/server` +
  `git -C voice/server checkout f0afcc6d01d4424ad72950038dff66646b24bc78` (skip if present at
  that commit).
- Own venv: `uv venv voice/server/.venv --python 3.12` (drop to 3.11 only if chatterbox wheels
  refuse 3.12), install the server's requirements per its README Mac path (plain
  `requirements.txt` + torch from PyPI gives MPS wheels on arm64).
- Configure `voice/server/config.yaml`: `device: mps`, port from `VOICE_PORT`, and point its
  reference-audio dir at `voice/reference_audio/` (or symlink — whichever the server's config
  supports; check `config.yaml` keys, don't guess).
- `voice/reference_audio/` tracked with a `README.md` explaining the folder; `*.wav` gitignored.
- gitignore additions: `voice/server/`, `voice/reference_audio/*.wav`.
- Wire `voice/setup.sh` into the top-level `setup.sh` behind `VOICE_ENABLED` so a fresh fork
  gets it in one command (first model download ~2–3 GB — print a heads-up).

### 3. `voice/make-reference.sh` — recording → reference WAV (no ffmpeg)
`voice/make-reference.sh <input-audio> <name> [start_sec] [duration_sec]` →
`voice/reference_audio/<name>.wav`. Use built-ins only:
`afconvert -f WAVE -d LEI16@44100 -c 1` for format, and for trimming either `afconvert`'s
offset flags or a stdlib-Python one-liner via the project venv. Target: mono 16-bit WAV,
10–30 s. This script is also the son-facing "make your own voice" tool, so `--help` text
should be friendly.

### 4. Cut the JARVIS reference
Audition the source MP3 and cut 2–3 candidate segments of clean speech (no music/SFX/other
speakers), e.g. `jarvis.wav`, `jarvis-alt1.wav`. Generate a test line with each via direct
curl, listen (`afplay`), keep the best as `jarvis.wav`. Log which timestamp ranges won — that's
a lesson Friday will want.

### 5. `scripts/stack.sh` — voice becomes the 4th managed layer
- `start_voice` / `stop_voice` mirroring the bridge functions: nohup launch of the server's
  uvicorn (per its README start command) with pid file `.run/voice.pid`, log `.run/voice.log`.
  Skip cleanly (with an `ok "voice disabled"` line) when `VOICE_ENABLED=0` or
  `voice/server/` absent — the stack must keep working on forks that haven't run voice setup.
- `status` + `check` rows: listener on `:$VOICE_PORT`, plus a real synthesis probe in
  `check` (`curl -s -X POST :$VOICE_PORT/v1/audio/speech -d '{"input":"test","voice":"jarvis.wav"}'`
  → non-empty audio bytes; discover the server's actual health route from its code and prefer
  that for the cheap check).
- `check` also verifies container → host wiring: `docker exec` curl to
  `host.docker.internal:$VOICE_PORT` (same pattern as the existing bridge wiring check).

### 6. Open WebUI wiring (compose + running container)
- `deploy/docker-compose.yml`: parameterize with `${WEBUI_PORT:-3000}`, `${BRIDGE_PORT:-8765}`,
  and add the TTS seed block (fresh-volume path):
  ```
  - AUDIO_TTS_ENGINE=openai
  - AUDIO_TTS_OPENAI_API_BASE_URL=http://host.docker.internal:${VOICE_PORT:-8004}/v1
  - AUDIO_TTS_OPENAI_API_KEY=grifcad-local
  - AUDIO_TTS_MODEL=tts-1
  - AUDIO_TTS_VOICE=${VOICE_DEFAULT:-jarvis.wav}
  - AUDIO_TTS_SPLIT_ON=punctuation
  ```
- The **running** container has an existing volume, so also set the same values through the
  audio-config API (`POST /api/v1/audio/config/update`, WEBUI_AUTH=false makes this easy) or
  Admin → Settings → Audio, then verify with a Read-Aloud click.

### 7. `INSTALL.md` — "Give it a voice" section
After the microphone section: what it is (assistant *speaks back*, fully local), one-command
setup (`bash voice/setup.sh`), make-your-own-voice (record ~20 s on the Mac — Voice Memos is
fine — then `voice/make-reference.sh ~/Desktop/me.m4a myvoice` and set `VOICE_DEFAULT`),
the existing-volume Admin → Audio caveat, disk/first-download note, and the personal-use
line for cloned voices of real people. Keep the kid-friendly INSTALL.md tone.

### 8. `docs/MAKE-IT-YOURS.md` — the fork guide (the gift doc)
Written *to* the son. Three parts:
- **How your assistant talks** — 10 lines on how zero-shot voice cloning works (reference
  audio → speaker embedding → speech generation), pitched curious-teen level.
- **Make it speak as anyone (you, ideally)** — the record → make-reference → swap flow;
  why cloned voices of real people stay in the house.
- **Fork it into your own** — clone the repo under his own GitHub, what to change
  (`config/*.env`, voice, printer IP), how the pieces fit (browser → Open WebUI → bridge →
  Claude → OpenSCAD → printer; voice server on the side), and pointers for what to explore
  next (new skills, new voices, new parts). Link it from README.md.

### 9. Doc hygiene
- CLAUDE.md: add the voice layer to the architecture/layout sections (voice server :8004,
  `voice/` dir, `config/voice.env`), fix the stale `out/preview/` follow-up note.
- `projects/README.md`: same stale-note fix.
- `bridge/README.md`: mention the sibling voice service in the endpoint/stack picture.

### 10. Lessons (`tasks/lessons.md`, tag `VOICE`)
Log at minimum: Mac install quirks (torch/MPS, python version), the server's actual
config keys + health route, reference-clip selection findings (what made a clip good/bad),
measured latency per sentence, and anything about the audio-config-API step. These port
straight into Friday's P3-UI-M5.

### 11. Verification gates (all must pass before commit)
1. `curl -X POST http://127.0.0.1:8004/v1/audio/speech -H 'Content-Type: application/json' -d '{"model":"tts-1","input":"Good afternoon. All systems are online.","voice":"jarvis.wav"}' -o /tmp/jarvis-test.wav` → valid WAV/audio, `afplay` sounds like JARVIS.
2. Same call from inside the container via `host.docker.internal:8004` → 200.
3. Browser at `localhost:3000`: ask for a part, click Read-Aloud (and confirm auto-speak
   setting) → spoken reply in the cloned voice.
4. `scripts/stack.sh check` → ALL CHECKS PASSED including the new voice rows.
5. `scripts/stack.sh stop && scripts/stack.sh start` → voice comes back without manual steps.
6. Fork simulation: with `VOICE_ENABLED=0`, `stack.sh start` + `check` still pass (voice rows
   skipped, nothing errors).
7. Measure and record: seconds from Read-Aloud click to first audio for a ~3-sentence reply.

### 12. Commit
Conventional style matching the repo history (e.g. `feat: cloned local voice (Chatterbox) — the assistant speaks as JARVIS`).
Do **not** push (3 pre-existing unpushed commits — Grif decides when).

## Out of scope
- Anything in `agent-teams/` / Concilio / WealthOS — hard firewall, different track entirely.
- Friday and grif-webui-hub — Friday has its own brief (`P3-UI-M5-BRIEF.md`); the hub needs
  no changes for this work.
- Streaming TTS, STT changes, voicebox integration.
