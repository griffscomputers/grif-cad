#!/usr/bin/env bash
# voice/make-reference.sh — turn any recording into a voice the assistant can speak with.
#
#   Usage:  bash voice/make-reference.sh <input-audio> <name> [start_sec] [duration_sec]
#
#   <input-audio>   any audio file (m4a from Voice Memos, mp3, wav, ...)
#   <name>          what to call the voice (letters/numbers/dashes) — becomes <name>.wav
#   [start_sec]     where in the recording to start cutting (default: 0)
#   [duration_sec]  how many seconds to keep (default: 20; the engine ignores >30)
#
#   Example — clone YOUR voice:
#     1. Record ~20 seconds of yourself reading anything (Voice Memos is perfect).
#     2. bash voice/make-reference.sh ~/Desktop/me.m4a myvoice
#     3. Set VOICE_DEFAULT=myvoice.wav in config/voice.env, then: scripts/stack.sh restart
#
#   Tips for a good clip: one voice only, no music or background noise, natural
#   talking (not shouting/whispering), 10-30 seconds.
#
#   Uses only macOS built-ins (afconvert + python3) — no ffmpeg needed.
set -euo pipefail

if [ $# -lt 2 ] || [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
fi

proj="$(cd "$(dirname "$0")/.." && pwd)"
in="$1"
name="$(echo "$2" | tr -cd 'A-Za-z0-9_-')"
start="${3:-0}"
dur="${4:-20}"
outdir="$proj/voice/reference_audio"
out="$outdir/$name.wav"

[ -f "$in" ] || { echo "!! input not found: $in"; exit 1; }
[ -n "$name" ] || { echo "!! bad name"; exit 1; }
mkdir -p "$outdir"

tmp="$(mktemp -t makeref).wav"
trap 'rm -f "$tmp"' EXIT

# 1. convert to the format the engine likes: WAV, 16-bit, 44.1 kHz, mono
afconvert -f WAVE -d LEI16@44100 -c 1 "$in" "$tmp"

# 2. cut the piece we want (stdlib python — no extra installs)
python3 - "$tmp" "$out" "$start" "$dur" <<'EOF'
import sys, wave
src, dst, start, dur = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
with wave.open(src, "rb") as w:
    rate = w.getframerate()
    total = w.getnframes()
    a = min(int(start * rate), total)
    n = min(int(dur * rate), total - a)
    w.setpos(a)
    frames = w.readframes(n)
    params = w.getparams()
with wave.open(dst, "wb") as o:
    o.setparams(params)
    o.writeframes(frames)
print(f"    kept {n/rate:.1f}s -> {dst}")
EOF

secs="$(python3 -c "import wave,sys;w=wave.open(sys.argv[1]);print(round(w.getnframes()/w.getframerate(),1))" "$out")"
echo "==> voice '$name' ready: voice/reference_audio/$name.wav (${secs}s)"
case "$secs" in
  [0-9].*) echo "    heads-up: under 10s — cloning works better with 10-30s of speech" ;;
esac
if python3 -c "import sys; sys.exit(0 if float('$secs') > 30 else 1)"; then
  echo "    heads-up: over 30s — the engine only uses the first 30s"
fi
echo "    try it:  set VOICE_DEFAULT=$name.wav in config/voice.env, then scripts/stack.sh restart"
