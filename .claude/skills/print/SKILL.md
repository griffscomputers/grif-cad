---
name: print
description: Send sliced G-code to the Creality K2 Plus over the LAN via Moonraker (upload + start). Use as the final pipeline stage. ENFORCES the safety gate — never start a print without explicit human confirmation.
argument-hint: <part-slug>
---

# print

The K2 Plus runs Moonraker at `http://$K2_PLUS_HOST:4408` (set `K2_PLUS_HOST` in `config/printer.env`). No cloud needed.

## SAFETY GATE — non-negotiable
A print is a physical, fire/mechanical-risk action. **Never start a print without explicit human confirmation.** Before starting, show:
- file + slug, estimated print time + filament use, material, nozzle/bed temps, and "is the bed clear and the plate seated?"

Then wait for an explicit "go." Do not emit raw G-code that heats or moves axes without the same confirmation.

## Upload, then start (two steps)
```
# 1. upload
curl -s -F "file=@out/<slug>/<slug>.gcode" \
  "http://$K2_PLUS_HOST:4408/server/files/upload"

# 2. start — ONLY after the human confirms
curl -s -X POST \
  "http://$K2_PLUS_HOST:4408/printer/print/start?filename=<slug>.gcode"
```
Wrapper: `scripts/print.sh <slug>` uploads + prints a summary; `scripts/print.sh <slug> --confirm` also starts.

## Monitor / fallbacks
- Status: `curl -s "http://$K2_PLUS_HOST:4408/printer/objects/query?print_stats"`, or open Fluidd at `http://$K2_PLUS_HOST:4408`.
- If upload/start fails with permission errors, the firmware build may gate Moonraker behind root: on the printer, Settings → Root account information (creds `root` / `creality_2024`) — **unverified on this unit, test first.**
- Offline fallback: copy the G-code to USB/SD and start from the touchscreen.

After the print: measure with calipers, log measured-vs-modeled deltas to `tasks/lessons.md`, feed back into the model.
