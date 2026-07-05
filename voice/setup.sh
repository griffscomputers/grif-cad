#!/usr/bin/env bash
# voice/setup.sh — idempotent install of the local voice engine (Chatterbox TTS).
#
# What this does:
#   1. Clones devnen/Chatterbox-TTS-Server into voice/server/ at a PINNED commit.
#   2. Builds its own venv (tries Python 3.12, falls back to 3.10 — the upstream
#      README's floor) and installs the Mac (MPS) dependency set.
#   3. Patches voice/server/config.yaml: device=mps, port from config/voice.env,
#      and points reference audio at voice/reference_audio/.
#
# First model download (~2-3 GB from ResembleAI's Hugging Face repo) happens on
# the server's FIRST START, not here. Re-running this script is always safe.
#
# Supply chain: both repos are pinned to exact commits reviewed on 2026-07-04
# (server config has no telemetry; the only outbound fetches are HF model pulls).
set -euo pipefail

proj="$(cd "$(dirname "$0")/.." && pwd)"
cd "$proj"

SERVER_REPO="https://github.com/devnen/Chatterbox-TTS-Server"
SERVER_PIN="f0afcc6d01d4424ad72950038dff66646b24bc78"   # v2.0.0 line, reviewed
CHATTERBOX_REPO="https://github.com/devnen/chatterbox-v2.git"
CHATTERBOX_PIN="cc0357396d9c73fc1e6c544ee40bb596020edd09" # master resolved 2026-07-04
                                                          # (includes the MPS float64 fix)

# wiring
VOICE_PORT=8004
[ -f config/voice.env ] && . config/voice.env

SRV="voice/server"
VENV="$SRV/.venv"

info(){ echo "==> $*"; }

# ---- 1. clone + pin -----------------------------------------------------------
if [ ! -d "$SRV/.git" ]; then
  info "cloning Chatterbox-TTS-Server (pinned)..."
  git clone --quiet "$SERVER_REPO" "$SRV"
fi
if [ "$(git -C "$SRV" rev-parse HEAD)" != "$SERVER_PIN" ]; then
  git -C "$SRV" fetch --quiet origin
  git -C "$SRV" checkout --quiet "$SERVER_PIN"
fi
info "server at pinned commit $(git -C "$SRV" rev-parse --short HEAD)"

# ---- 2. venv + deps (try 3.12, fall back to 3.10) ------------------------------
install_deps(){
  local py="$1"
  info "creating venv with Python $py..."
  rm -rf "$VENV"
  uv venv "$VENV" --python "$py" --quiet
  info "installing server requirements (torch arm64 wheels include MPS)..."
  uv pip install --python "$VENV/bin/python" -r "$SRV/requirements.txt"
  # chatterbox engine: --no-deps per upstream (prevents resolver conflicts);
  # s3tokenizer/onnx ride along --no-deps to dodge the protobuf pin clash.
  uv pip install --python "$VENV/bin/python" --no-deps \
    "git+$CHATTERBOX_REPO@$CHATTERBOX_PIN" s3tokenizer==0.3.0 onnx==1.16.0
  # descript-audiotools pins protobuf<3.20 but onnx 1.16 needs >=3.20.2 at runtime;
  # upstream's start.py does this exact force-upgrade (audiotools is fine with new protobuf).
  uv pip install --python "$VENV/bin/python" --no-deps --force-reinstall "protobuf>=4.25.0"
}

venv_ok(){
  [ -x "$VENV/bin/python" ] &&
  "$VENV/bin/python" - <<'EOF' >/dev/null 2>&1
import torch, chatterbox, yaml
assert torch.backends.mps.is_available()
EOF
}

if venv_ok; then
  info "venv already good ($("$VENV/bin/python" -V 2>&1)) — skipping install"
else
  if install_deps 3.12 && venv_ok; then
    info "installed with Python 3.12"
  else
    info "3.12 install failed a check — falling back to Python 3.10 (upstream floor)..."
    install_deps 3.10
    venv_ok || { echo "!! install failed on 3.10 too — see output above"; exit 1; }
    info "installed with Python 3.10"
  fi
fi
"$VENV/bin/python" -c "import torch; print('    MPS available:', torch.backends.mps.is_available())"

# ---- 2.5 MPS patch: reference-audio resampling ---------------------------------
# torchaudio's sinc resampler hits MPS's conv1d channel limit (torch 2.5.1), and
# PYTORCH_ENABLE_MPS_FALLBACK does NOT rescue it (the op is "implemented", just
# capped). Only call site is chatterbox's get_resampler(), used for the tiny
# reference-prep step — run that one op on CPU. Upstream precedent: start.py
# applies its own chatterbox post-install patch for a different MPS bug.
"$VENV/bin/python" - <<'EOF'
import pathlib, chatterbox
f = pathlib.Path(chatterbox.__file__).parent / "models/s3gen/s3gen.py"
src = f.read_text()
if "grifcad-mps-patch" in src:
    print("    MPS resample patch already applied")
else:
    old = ("def get_resampler(src_sr, dst_sr, device):\n"
           "    return ta.transforms.Resample(src_sr, dst_sr).to(device)")
    new = ('''class _GrifcadCPUResample(torch.nn.Module):  # grifcad-mps-patch
    """MPS conv1d caps out on torchaudio's sinc kernel; do this tiny op on CPU."""
    def __init__(self, src_sr, dst_sr, device):
        super().__init__()
        self.resample = ta.transforms.Resample(src_sr, dst_sr)
        self.device = device
    def forward(self, x):
        return self.resample(x.detach().cpu()).to(self.device)


def get_resampler(src_sr, dst_sr, device):
    if str(device).startswith("mps"):
        return _GrifcadCPUResample(src_sr, dst_sr, device)
    return ta.transforms.Resample(src_sr, dst_sr).to(device)''')
    assert old in src, "upstream get_resampler changed — re-check the patch"
    f.write_text(src.replace(old, new, 1))
    print("    MPS resample patch applied (get_resampler -> CPU on mps)")
EOF

# ---- 3. patch config.yaml ------------------------------------------------------
mkdir -p voice/reference_audio
"$VENV/bin/python" - "$proj" "$VOICE_PORT" <<'EOF'
import sys, yaml, pathlib
proj, port = pathlib.Path(sys.argv[1]), int(sys.argv[2])
cfg_path = proj / "voice/server/config.yaml"
cfg = yaml.safe_load(cfg_path.read_text())
cfg.setdefault("server", {})["port"] = port
eng = cfg.setdefault("tts_engine", {})
eng["device"] = "mps"
eng["reference_audio_path"] = str(proj / "voice/reference_audio")
cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True))
print(f"    config.yaml: device=mps, port={port}, reference_audio -> voice/reference_audio/")
EOF

info "voice engine ready. Start it via: scripts/stack.sh start"
info "(first start downloads the ~2-3 GB model — watch .run/voice.log)"
