#!/usr/bin/env bash
# render.sh — multi-angle PNG previews of a .scad or .stl model (the agent's "eyes").
# Usage:  scripts/render.sh <model.scad|model.stl> [outdir]   (default outdir: out/preview)
# Renders iso / front / side / top PNGs headlessly via OpenSCAD so the model can be
# visually reviewed (by the agent and by you) before slicing.
set -euo pipefail

model="${1:?usage: render.sh <model.scad|.stl> [outdir]}"
outdir="${2:-out/preview}"
mkdir -p "$outdir"

# Locate the OpenSCAD CLI — the macOS cask installs a versioned .app (e.g.
# OpenSCAD-2021.01.app) and does not symlink to PATH.
OSCAD="$(command -v openscad || true)"
if [ -z "$OSCAD" ]; then
  for app in /Applications/OpenSCAD*.app/Contents/MacOS/OpenSCAD; do
    [ -x "$app" ] && OSCAD="$app" && break
  done
fi
[ -n "$OSCAD" ] || { echo "OpenSCAD not found — brew install --cask openscad" >&2; exit 1; }

# OpenSCAD renders .scad directly; wrap an .stl in a throwaway import() scad.
src="$model"; tmp=""
if [[ "$model" == *.stl || "$model" == *.STL ]]; then
  abspath="$(cd "$(dirname "$model")" && pwd)/$(basename "$model")"
  tmp="$(mktemp -t grifcad-render-XXXXXX).scad"
  printf 'import("%s");\n' "$abspath" > "$tmp"
  src="$tmp"
fi
trap '[ -n "$tmp" ] && rm -f "$tmp"' EXIT

base="$(basename "${model%.*}")"
size="1100,825"
scheme="Tomorrow"

view () {  # $1 = name   $2 = rotx,roty,rotz
  "$OSCAD" -o "$outdir/${base}-$1.png" \
    --imgsize="$size" --autocenter --viewall \
    --colorscheme="$scheme" \
    --camera="0,0,0,$2,0" "$src"
  echo "  $outdir/${base}-$1.png"
}

echo "rendering $model -> $outdir/"
view iso   "55,0,25"
view front "90,0,0"
view side  "90,0,90"
view top   "0,0,0"

# make an STL available beside the PNGs (for the 3D viewer + "open in slicer"):
# export it from an OpenSCAD source, or pass a downloaded/imported .stl straight through.
if [[ "$model" == *.scad || "$model" == *.SCAD ]]; then
  "$OSCAD" -o "$outdir/${base}.stl" "$model" 2>/dev/null && echo "  $outdir/${base}.stl"
elif [[ "$model" == *.stl || "$model" == *.STL ]]; then
  cp -f "$model" "$outdir/${base}.stl" && echo "  $outdir/${base}.stl"
fi
echo "done."
