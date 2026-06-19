#!/usr/bin/env bash
# Slice an STL to G-code for the K2 Plus via the OrcaSlicer CLI.
# Usage:  scripts/slice.sh <slug> [stl-name]   (stl-name default: prod.stl)
#
# Export the K2 Plus machine/process/filament presets from the OrcaSlicer GUI
# into profiles/ first. OrcaSlicer links GUI libs even when slicing headless,
# so it runs under xvfb-run on a headless box.
# SCAFFOLD — validate flags/profile names on first run.
set -euo pipefail

slug="${1:?usage: slice.sh <slug> [stl-name]}"
stl="${2:-prod.stl}"
out="out/${slug}"

[ -f "${out}/${stl}" ] || { echo "no STL at ${out}/${stl} — export from /cad-scripting first" >&2; exit 1; }

xvfb-run orca-slicer --slice 0 \
  --load-settings "profiles/k2plus_machine.json;profiles/k2plus_process.json" \
  --load-filaments "profiles/k2plus_filament.json" \
  --outputdir "${out}" \
  --allow-newer-file \
  "${out}/${stl}"

echo "sliced → ${out}/ (rename the plate output to ${slug}.gcode for scripts/print.sh)"
