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
This installs (idempotently — safe to re-run): **Claude Code**, **OpenSCAD**, **OrcaSlicer**,
the open-source Docker runtime (**Colima** + docker + compose), **uv**, a **Python 3.12 venv**
with the CAD + bridge dependencies (`requirements.txt`), and your local config files. If
Homebrew isn't installed, it installs that first (it'll ask for your Mac password).

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

## 5. Start it
```bash
bash scripts/start.sh
```
Then open **http://localhost:3000**, pick the **grif-cad** model, and chat:
> "make a 30 mm cube with a 10 mm hole"

A picture of the model appears right in the chat. Click the **microphone** to talk instead of type.
Leave the `start.sh` window open while you use it; **Ctrl+C** stops the assistant.

### Turn on the microphone
The mic works on `localhost` out of the box. If it doesn't transcribe, open
**Admin → Settings → Audio → Speech-to-Text** and choose an engine (**Local Whisper** = offline;
**Web API** = no download).

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
