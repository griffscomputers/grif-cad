# HANDOFF-VOICE-DEBUG.md — Read-aloud works at the API, feels dead in the browser

> Written 2026-07-04 at the end of the session that shipped the voice layer (commit
> `c89ddb4`) and the Meshy studio build (commit `518f246`, committed by Grif). Launch a
> fresh session from the grif-cad repo root and start here. Suggested prompt:
> **"Read HANDOFF-VOICE-DEBUG.md and fix the browser read-aloud experience."**

## Where things stand (all verified this session)

**Everything below is DONE, committed, and green — do not rebuild it:**
- Voice layer shipped per `HANDOFF-VOICE.md`: Chatterbox-TTS-Server pinned `f0afcc6d`
  (engine `chatterbox-v2` pinned `cc035739`), native MPS host service `:8004`, 4th
  `stack.sh` layer, `voice/setup.sh` idempotent installer (includes an MPS resample
  patch + protobuf force-upgrade), `voice/make-reference.sh`, fork-safe `VOICE_ENABLED=0`.
- **JARVIS voice chosen and working**: `voice/reference_audio/jarvis.wav` (cut 4:36–4:56
  of the Downloads MP3; alts at 7:30 / 5:20 kept beside it). Grif A/B'd by ear.
- All 8 verification gates passed **except the human browser test**:
  direct `:8004/v1/audio/speech` → 200 audio; container→host wiring OK;
  `stack.sh check` + `--deep` ALL PASSED (deep = real synthesis + real claude round-trip);
  stop/start resilience OK; `VOICE_ENABLED=0` fork sim OK.
- Open WebUI audio config is correct **in its DB** (verified via
  `GET /api/v1/audio/config`): engine openai, `http://host.docker.internal:8004/v1`,
  key `grifcad-local`, model tts-1, voice `jarvis.wav`, split punctuation. The compose
  `AUDIO_TTS_*` env seed applied to the existing volume because audio keys had never
  been written before.
- Meshy build (earlier same day): 5 mode model-ids from the bridge, `/studio` gallery,
  digest-pinned Open WebUI + `deploy/webui/custom.css` skin. All still green in `check`.
- Lessons: `tasks/lessons.md` → `VOICE` section (6 entries); 2 cross-cutting entries in
  `~/Documents/Code/tasks/lessons.md` (bash-3.2 unicode-after-`$var`; harness timeout
  kills nohup'd daemons started in the same call).

## THE OPEN BUG (two distinct symptoms — don't conflate)

**Symptom A (read-aloud):** clicking read-aloud "is not responding and showing multiple
disconnects."

**Symptom B (voice mode / hands-free call):** "stuck in listening." Evidence from
`docker logs grifcad-openwebui`: mic audio IS reaching the container (WAV received,
converted to MP3, "Chunk paths" logged at 02:17:11 and 02:17:26) but **no transcription
result ever follows** — STT is `stt.ENGINE: ""` = local faster-whisper (`WHISPER_MODEL:
base`) running on **container CPU**; first use downloads the model and/or transcribes
too slowly, so voice mode never leaves "listening". No errors in the container log.
Fix candidates: pre-pull/warm the whisper model, switch STT to the browser's Web API
engine (Settings → Audio → STT), or accept and document. NOTE voice mode chains
STT → claude chat (10–60 s) → TTS (~15–60 s/sentence) — even with every stage healthy,
hands-free conversation mode may be the wrong UX for this stack today; read-aloud on
demand is the realistic target. Decide deliberately.

**Evidence gathered before handoff:**
- The engine received 12 `OpenAI speech` requests total this session and synthesized
  successfully every time (`.run/voice.log` — last success 21:11:04, 109 KB WAV).
- Generation speed on the M5/MPS is the problem: the T3 token loop runs ~27 it/s over
  up to 1000 steps → **~40–60 s per sentence chunk** (measured: 68 s first request
  after warmup, then 10–27 s for short lines; single sentence via the Open WebUI proxy
  15 s). The 2–6 s/sentence estimate in HANDOFF-VOICE.md was optimistic.
- `.run/voice.log` shows `BF16 optimization disabled (TTS_BF16=off or hardware
  unsupported)` at engine load — an untried speed lever.
- One vocoder op falls back to CPU per request (`aten::unfold_backward` warning) — minor.
- Open WebUI frontend almost certainly times out / drops its socket while waiting tens
  of seconds for `/api/v1/audio/speech`, hence "disconnects". The container log shows no
  crashes (only the standard CORS warning).

## Attack plan (in order)

1. **Reproduce with eyes on both logs.** Browser click with
   `tail -f .run/voice.log` and `docker logs -f grifcad-openwebui` side by side; check
   the browser devtools Network tab for which request aborts and after how many seconds.
   Distinguish: frontend socket timeout vs aiohttp proxy timeout vs queued requests
   piling on the single-threaded engine.
2. **Speed: try `TTS_BF16=on`** env on the server launch (stack.sh `start_voice`) — the
   engine logline implies support is detected at load; MPS bf16 could roughly halve
   generation time. Re-measure with the deep-check synthesis probe.
3. **Speed: try shortening generation.** `voice/server/config.yaml`
   `generation_defaults:` (temperature 0.8, exaggeration 1.3, cfg_weight 0.5) — check
   the pinned server's docs/code for a max-token / steps knob for short sentences.
4. **Timeout: raise Open WebUI's outbound TTS timeout** if that's where it dies —
   look at `AIOHTTP_CLIENT_TIMEOUT` (and TTS-specific variants) in Open WebUI env docs;
   add to `deploy/docker-compose.yml` (remember: env only seeds fresh volumes — check
   whether this one is a PersistentConfig or plain env read; plain env applies on
   recreate).
5. **UX: pre-warm on start.** After `start_voice` health passes, fire one throwaway
   synthesis (`All systems online`) so the first user click never eats the ~60 s warmup.
   Cheap and high-value regardless of 2–4.
6. **If MPS simply can't get under ~8 s/sentence:** consider the smaller/faster path —
   the server supports `model.repo_id` alternatives (currently `chatterbox-turbo`), or
   accept click-to-speak (no auto-play) and set expectations in INSTALL.md. Do NOT
   switch to Docker (no GPU) or an external TTS API (stays on-box, always).
7. Whatever fixes it → log under `VOICE` in `tasks/lessons.md` (Friday's P3-UI-M5
   inherits this) and update the latency numbers in INSTALL.md's voice section.

## Orientation (fresh session cheat sheet)

- Stack: `scripts/stack.sh start|stop|status|check [--deep]|logs [-f] [voice]`.
  Layers: colima → Open WebUI container `:3000` → bridge `:8765` → voice `:8004`.
- Wiring truth: `config/voice.env` (VOICE_ENABLED/VOICE_PORT/VOICE_DEFAULT/WEBUI_PORT/
  BRIDGE_PORT). Compose reads it via `--env-file` (stack.sh `compose()` helper).
- Voice server code: `voice/server/` (gitignored, pinned clone; venv inside). Rerunning
  `bash voice/setup.sh` is always safe and re-applies the MPS patch + config.yaml.
- Direct synthesis test:
  `curl -X POST http://127.0.0.1:8004/v1/audio/speech -H 'Content-Type: application/json' -d '{"model":"tts-1","input":"test line","voice":"jarvis.wav"}' -o /tmp/t.wav && afplay /tmp/t.wav`
- Admin API token (kiosk mode): `POST /api/v1/auths/signin` with `{"email":"","password":""}`.
- **Gotchas that already cost time (don't repay):** start daemons in their own
  short-lived Bash call (harness timeout kills the process group); ASCII only after
  `$var` in bash strings; PYTORCH_ENABLE_MPS_FALLBACK does not fix the resampler
  (already patched in setup.sh); never `--quiet` installer pip steps.
- Repo state at handoff: `main` at `c89ddb4` (+ this file), **not pushed** — Grif pushes.

## Out of scope (unchanged from HANDOFF-VOICE.md)
Friday / grif-webui-hub, streaming TTS, STT changes, voicebox, anything Concilio.
