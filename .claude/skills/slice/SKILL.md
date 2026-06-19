---
name: slice
description: Slice an STL to G-code for the Creality K2 Plus using the OrcaSlicer headless CLI. Use after a model is exported and before printing. Covers profile loading, the xvfb requirement, and the CFS filament-change caveat.
argument-hint: <part-slug> [stl-name]
---

# slice

OrcaSlicer is the CLI-friendly slicer and ships a built-in **K2 Plus** profile. Output → `out/<slug>/<slug>.gcode`.

## Invocation
```
xvfb-run orca-slicer --slice 0 \
  --load-settings "profiles/k2plus_machine.json;profiles/k2plus_process.json" \
  --load-filaments "profiles/k2plus_filament.json" \
  --outputdir "out/<slug>" \
  --allow-newer-file \
  out/<slug>/prod.stl
```
- `--slice 0` = all plates. `--load-settings "machine;process"` is semicolon-separated. `--datadir` points at a profile store if not passing `--load-settings`.
- OrcaSlicer links GUI libs even headless — run under `xvfb-run` on a headless box.
- Export the K2 Plus machine/process/filament presets once from the OrcaSlicer GUI into `profiles/`.
- Wrapper: `scripts/slice.sh <slug> [stl-name]`.

## Caveats
- Some K2 Plus profile versions shipped a missing/misplaced **CFS filament-change G-code** — for multicolor, open the profile and confirm the change-filament gcode before printing (OrcaSlicer #7607 / discussion #8892).
- Sanity-check the sliced output: model fits **350³**, expected print time + filament, sane first-layer temps. Then hand to `/print`.
