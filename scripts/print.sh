#!/usr/bin/env bash
# Upload sliced G-code to the K2 Plus and (ONLY with --confirm) start the print.
# Usage:  scripts/print.sh <slug> [--confirm]
#
# SAFETY: starting a print is a physical, fire/mechanical-risk action. Without
# --confirm this only uploads and prints a summary — it never starts the print.
set -euo pipefail

slug="${1:?usage: print.sh <slug> [--confirm]}"
confirm="${2:-}"

# shellcheck source=/dev/null
source config/printer.env
host="${K2_PLUS_HOST:?set K2_PLUS_HOST in config/printer.env}"
base="http://${host}:4408"
# Canonical home is projects/<slug>/; fall back to the legacy out/<slug>/ layout.
dir="projects/${slug}"; [ -d "$dir" ] || dir="out/${slug}"
gcode="${dir}/${slug}.gcode"

[ -f "$gcode" ] || { echo "no gcode at $gcode — run scripts/slice.sh $slug first" >&2; exit 1; }

echo "Uploading ${gcode} → ${base} ..."
curl -s -F "file=@${gcode}" "${base}/server/files/upload" >/dev/null
echo "Uploaded ${slug}.gcode."

if [ "$confirm" != "--confirm" ]; then
  cat <<EOF

NOT starting the print (no --confirm).
Confirm: bed clear, plate seated, correct filament loaded — then run:
  scripts/print.sh ${slug} --confirm
EOF
  exit 0
fi

echo "Starting print of ${slug}.gcode ..."
curl -s -X POST "${base}/printer/print/start?filename=${slug}.gcode" >/dev/null
echo "Print started. Monitor at ${base}"
