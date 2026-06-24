---
name: slice
description: Slice an STL to G-code for the Creality K2 Plus. Headless slicing uses the OrcaSlicer CLI (the only reliably scriptable slicer on macOS); Creality Print is open-in-GUI only. Covers profile loading, macOS invocation, and the CFS filament-change caveat.
argument-hint: <part-slug> [stl-name]
---

# slice

OrcaSlicer is the CLI-friendly slicer and ships a built-in **K2 Plus** profile. Output → `out/<slug>/<slug>.gcode`.

## Invocation (headless = OrcaSlicer)
On a Mac call the bundle binary directly — there is **no xvfb on macOS** (that's Linux-only):
```
/Applications/OrcaSlicer.app/Contents/MacOS/OrcaSlicer --slice 0 \
  --load-settings "profiles/k2plus_machine.json;profiles/k2plus_process.json" \
  --load-filaments "profiles/k2plus_filament.json" \
  --outputdir "out/<slug>" \
  --allow-newer-file \
  out/<slug>/prod.stl
```
- `--slice 0` = all plates. `--load-settings "machine;process"` is semicolon-separated. `--datadir` points at a profile store if not passing `--load-settings`.
- `scripts/slice.sh <slug> [stl-name]` wraps this: it resolves the binary and adds `xvfb-run` **only** on a headless Linux box.
- Export the K2 Plus presets once from the OrcaSlicer GUI into `profiles/`.

## Creality Print (GUI only)
Creality Print is an OrcaSlicer fork but has no reliable headless CLI on macOS and an **incompatible profile format** (no sharing with Orca), so it's open-in-GUI only:
```
open -a "Creality Print" out/<slug>/prod.stl
```
In the web UI this is the **🛠 Open in Creality Print** button (per-person preference via `SLICER_DEFAULT`). Creality Print has first-class K2 Plus + CFS support for manual multicolor work.

## Caveats
- Some K2 Plus profile versions shipped a missing/misplaced **CFS filament-change G-code** — for multicolor, open the profile and confirm the change-filament gcode before printing (OrcaSlicer #7607 / discussion #8892).
- Sanity-check the sliced output: model fits **350³**, expected print time + filament, sane first-layer temps. Then hand to `/print`.
