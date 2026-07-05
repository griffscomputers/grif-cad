# Make It Yours

This whole thing — the chat, the studio, the voice, the printer pipeline — is yours to
mess with. This page explains how the coolest part works, how to make it speak as *you*,
and how to fork the entire assistant into something that's completely your own.

## How your assistant talks

The voice isn't a recording and it isn't a robot voice from a menu. It's **zero-shot voice
cloning**, and the trick is wild:

1. You give the engine a short clip of someone talking — 10 to 30 seconds is enough.
2. A neural network listens to it once and squeezes *how that voice sounds* — pitch, pace,
   accent, the little rasp on certain words — into a list of a few hundred numbers called a
   **speaker embedding**. Not the words. Just the *voice*.
3. When the assistant wants to say something new, a second network generates speech from
   the text, steering the sound with that embedding — so it says things the original
   speaker never said, in their voice.

That's why the file in `voice/reference_audio/` *is* the voice. No training, no cloud —
the whole thing runs on this Mac's GPU. Swap the file, swap the voice.

## Make it speak as anyone (you, ideally)

1. Open **Voice Memos** and record ~20 seconds of yourself reading anything. One voice,
   no music, no fan noise, normal talking speed.
2. Turn it into a voice:
   ```bash
   bash voice/make-reference.sh ~/Desktop/me.m4a myvoice
   ```
3. Point the assistant at it — in `config/voice.env`:
   ```
   VOICE_DEFAULT=myvoice.wav
   ```
   then `scripts/stack.sh restart`. Done. It speaks as you now.

**Why cloned voices of real people stay in the house:** a cloned voice can say *anything*,
including things the real person never said and never would. That's a power you only use
on yourself, or with someone's permission, and never in public. The `.wav` files are
gitignored on purpose — they never leave this Mac, even if you push the repo.

## Fork it into your own

The assistant is just a git repo. Clone it under your own GitHub account and it's yours:

```bash
git clone <this-repo> my-assistant && cd my-assistant
bash setup.sh
```

**How the pieces fit** (each one is swappable):

```
browser (Open WebUI :3000) ──▶ bridge (:8765) ──▶ Claude ──▶ OpenSCAD/CadQuery ──▶ renders
        │ voice replies                                          │ G-code (you confirm!)
        ▼                                                        ▼
voice server (:8004, your voice)                          Creality K2 Plus
```

**What to change to make it yours:**
- `config/voice.env` — your voice, your ports
- `config/printer.env` — your printer's IP (or none — it works fine printer-less)
- `deploy/webui/custom.css` — the look; recolor it, rename it (`WEBUI_NAME` in
  `deploy/docker-compose.yml`)
- `bridge/app.py` → `PERSONA` — how the assistant talks to you; `MODES` — what the
  mode picker offers

**Things to explore next:**
- Add a skill in `.claude/skills/` — teach it a new procedure (new slicer? laser cutter?)
- Add a mode — copy a `MODES` entry in `bridge/app.py` and give it its own persona
- New voices — one `.wav` each in `voice/reference_audio/`; switch anytime
- New parts — `/studio` is your gallery; everything you design lives in `projects/`

Break it. `git checkout .` un-breaks it. That's the whole game.
