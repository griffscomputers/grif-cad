#!/usr/bin/env bash
# Slice an STL to G-code for the K2 Plus via the OrcaSlicer CLI (headless).
# Usage:  scripts/slice.sh <slug> [stl-name]   (stl-name default: prod.stl)
#
# Headless slicing always uses OrcaSlicer — the only reliably scriptable slicer on
# macOS. (Creality Print is GUI-only here; use the web UI's "Open in Creality Print",
# or `open -a "Creality Print" <file>`.) Export the K2 Plus machine/process/filament
# presets from the OrcaSlicer GUI into profiles/ first.
# SCAFFOLD — validate flags/profile names on first run.
set -euo pipefail

slug="${1:?usage: slice.sh <slug> [stl-name]}"
# Canonical home is projects/<slug>/; fall back to the legacy out/<slug>/ layout.
out="projects/${slug}"; [ -d "$out" ] || out="out/${slug}"
# Default STL: the per-project <slug>.stl if present, else the legacy prod.stl.
stl="${2:-}"
if [ -z "$stl" ]; then
  if [ -f "${out}/${slug}.stl" ]; then stl="${slug}.stl"; else stl="prod.stl"; fi
fi
[ -f "${out}/${stl}" ] || { echo "no STL at ${out}/${stl} — export from /cad-scripting first" >&2; exit 1; }

# Locate the OrcaSlicer CLI — macOS installs an .app and doesn't put it on PATH.
OSLICER="$(command -v orca-slicer || true)"
if [ -z "$OSLICER" ] && [ -x "/Applications/OrcaSlicer.app/Contents/MacOS/OrcaSlicer" ]; then
  OSLICER="/Applications/OrcaSlicer.app/Contents/MacOS/OrcaSlicer"
fi
[ -n "$OSLICER" ] || { echo "OrcaSlicer not found — brew install --cask orcaslicer" >&2; exit 1; }

# OrcaSlicer links GUI libs even in CLI mode, so it needs a virtual display ONLY on a
# headless Linux box. macOS (Quartz) has no xvfb — call the binary directly there.
WRAP=""
if [ "$(uname)" = "Linux" ] && command -v xvfb-run >/dev/null 2>&1; then WRAP="xvfb-run"; fi

$WRAP "$OSLICER" --slice 0 \
  --load-settings "profiles/k2plus_machine.json;profiles/k2plus_process.json" \
  --load-filaments "profiles/k2plus_filament.json" \
  --outputdir "${out}" \
  --allow-newer-file \
  "${out}/${stl}"

echo "sliced → ${out}/ (rename the plate output to ${slug}.gcode for scripts/print.sh)"
