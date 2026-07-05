# Installing grif-cad

grif-cad is a talking CAD assistant: describe a part in a browser (type **or speak**),
watch it render, and — with a grown-up's OK — slice and print it on a Creality K2 Plus.
This guide takes a fresh fork to a working setup.

## What you need
- A **Mac with Apple Silicon** (M-series). *(Windows support is planned — not yet.)*
- A **Claude Pro or Max subscription** — the assistant runs on your plan (no per-use API bill).
- About **5 GB free** (the OpenSCAD/OrcaSlicer apps + the Open WebUI container image) and a few minutes.

You do **not** need to install Python, Docker, or any of the tools by hand — the script does it.

## 1. Get the code
```bash
git clone https://github.com/griffscomputers/grif-cad.git
cd grif-cad
```

## 2. Run the installer
```bash
bash setup.sh
```
This installs (idempotently — safe to re-run): **Claude Code**, **OpenSCAD**, **OrcaSlicer** +
**Creality Print** (slice in whichever you prefer), the open-source Docker runtime (**Colima** +
docker + compose), **uv**, a **Python 3.12 venv** with the CAD + bridge dependencies
(`requirements.txt`), and your local config files. If Homebrew isn't installed, it installs that
first (it'll ask for your Mac password).

## 3. Sign in to Claude (one time)
```bash
claude               # log in with your Claude Pro/Max account
claude setup-token   # creates a long-lived token (~1 year)
```
Paste the token into `config/bridge.env`:
```
CLAUDE_CODE_OAUTH_TOKEN=<paste it here>
```
*(Skip the token if you'll always have `claude` logged in — the bridge falls back to that.
The token just makes it work as a standing service.)*

## 4. (Optional) Point it at your printer
Only if you have the Creality K2 Plus on your network — edit `config/printer.env`:
```
K2_PLUS_HOST=192.168.1.50      # your printer's IP
```
Everything up to slicing works without a printer.

### (Optional) Let it find existing models
"Search before you build" pulls from Thingiverse. Add a free token — register an app at
https://www.thingiverse.com/developers/apps and paste it into `config/repos.env`:
```
THINGIVERSE_TOKEN=<paste it here>
```
Without it, search still gives browser links (Thingiverse, Creality Cloud, MakerWorld, Printables, Cults3D).

## 5. Start it
```bash
bash scripts/start.sh
```
Then open **http://localhost:3000**, pick the **grif-cad** model, and chat:
> "make a 30 mm cube with a 10 mm hole"

A picture of the model appears right in the chat. Click the **microphone** to talk instead of type.
Leave the `start.sh` window open while you use it; **Ctrl+C** stops the assistant.

### Pick your slicer (optional)
Each model in the chat shows **🛠 Open in OrcaSlicer** and **🛠 Open in Creality Print** — click whichever you like. To list your favourite first, set `SLICER_DEFAULT=orca` (or `creality`) in `config/bridge.env`. (Automated slicing always uses OrcaSlicer under the hood.)

`setup.sh` installs both slicers. To (re)install one by hand:
```bash
brew install --cask orcaslicer creality-print
```

### Turn on the microphone
The mic works on `localhost` out of the box. If it doesn't transcribe, open
**Admin → Settings → Audio → Speech-to-Text** and choose an engine (**Local Whisper** = offline;
**Web API** = no download).

### Give it a voice (optional, but very cool)
The assistant can *speak its replies* in a custom voice — fully local, nothing leaves the Mac.
It clones a voice from a short audio clip: 10–30 seconds of clean speech **is** the voice; no
training step.

```bash
bash voice/setup.sh        # one-time install (first server start downloads ~2-3 GB of model)
bash scripts/stack.sh restart
```

**Make it speak as anyone — you, ideally:**
1. Record ~20 seconds of yourself reading anything. The Voice Memos app is perfect.
2. `bash voice/make-reference.sh ~/Desktop/me.m4a myvoice`
3. Set `VOICE_DEFAULT=myvoice.wav` in `config/voice.env`, then `scripts/stack.sh restart`.

Then in the chat, click the **speaker icon** on any reply (or turn on auto-playback in
Settings → Audio). First-time note: if the web UI was installed before the voice, tell it where
to find the voice once in **Admin → Settings → Audio → Text-to-Speech**: engine **OpenAI**, URL
`http://host.docker.internal:8004/v1`, key `grifcad-local`, voice = your `.wav` name (the
settings live in the web UI's database, so the automatic wiring only applies to fresh installs).

Each sentence takes a couple of seconds to generate on the Mac's GPU — it starts speaking after
the first sentence, so it feels quick.

> **House rule:** cloned voices of real people are for personal use in this house only. The
> voice files stay on this Mac — they're never committed or shared.

## Stopping / starting again
- Stop the web UI: `bash scripts/stop.sh` (and `colima stop` to stop the engine).
- Start again later: `bash scripts/start.sh`.
- Auto-start the engine at login (optional): `brew services start colima`.

## Updating
```bash
git pull
bash setup.sh          # re-syncs tools + Python deps
docker compose -f deploy/docker-compose.yml pull   # newer Open WebUI, if any
```

## Safety
The assistant will design, render, and slice freely, but it **never starts a physical print on
its own** — that always needs a person to confirm. This gate holds even through the web UI.

## Troubleshooting
- **`docker compose` not found** → re-run `bash setup.sh` (it wires the compose plugin).
- **Image won't pull / credential error** → re-run `setup.sh` (it clears a stale credential helper).
- **Web UI loads but no model / "connection error"** → make sure the bridge window (`start.sh`) is
  running; it serves `http://localhost:8765`.
- **No picture appears after a build** → the bridge serves images at `http://localhost:8765/files/…`;
  confirm `start.sh` is still running.
- **Colima won't start** → `colima delete && colima start`.
