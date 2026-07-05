# reference_audio/ — the voices

Each `.wav` in this folder **is** a voice. The TTS engine (Chatterbox, running at
`:8004`) does zero-shot cloning: give it 10–30 seconds of clean speech and it speaks
any text in that voice — no training step.

- Make one from any recording: `bash voice/make-reference.sh <recording> <name>`
- Pick the active voice: `VOICE_DEFAULT=<name>.wav` in `config/voice.env`, then
  `scripts/stack.sh restart`.

**The `.wav` files are gitignored on purpose.** Cloned voices of real people are for
personal use in this house only — they never get committed, pushed, or shared.
