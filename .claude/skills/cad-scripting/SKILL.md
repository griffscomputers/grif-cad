---
name: cad-scripting
description: Author printable parametric CAD for the grif-cad pipeline. Use when generating or editing OpenSCAD (.scad) prototypes or CadQuery (.py) production models, choosing between the two engines, or exporting STL/STEP. Encodes units, printability rules, and headless render/export for the Creality K2 Plus.
argument-hint: <part-slug> [what to model]
---

# cad-scripting

Generate dimensionally-correct, printable geometry. Units are **mm**. The K2 Plus build volume is **350 × 350 × 350 mm** — never exceed it.

**Source real dimensions — never hallucinate fit-critical numbers.** Look them up (dimensions.com is good for consumer hardware) or have the user caliper them. Put every uncertain dimension in a named `*_fit` parameter with a `// PROXY - verify` comment so what still needs grounding is obvious. The model can be geometrically perfect and still not fit if the numbers are guesses.

## Project home (one folder per part)
Every part lives in **`projects/<slug>/`** — source, renders, STL/STEP, G-code, data all together. Start a part with `scripts/project.sh new <slug> [--engine openscad|cadquery]` (scaffolds the source + registers it in `projects/index.tsv`); recall one with `scripts/project.sh show <slug>`. The folder is gitignored; only the catalog is tracked.

## Engine choice
- **OpenSCAD** — simple extrusions/booleans, a few parameters, fast prototypes → `projects/<slug>/<slug>.scad`.
- **CadQuery** — tolerances/fits, STEP output, fillets/chamfers/sweeps/lofts, assemblies, data-driven geometry → `projects/<slug>/<slug>.py`.

## OpenSCAD (prototype)
Parameterize at the top of the file; raise `$fn` for round parts (e.g. `$fn = 64`). Render headless:
```
openscad -o projects/<slug>/<slug>.stl projects/<slug>/<slug>.scad
openscad -o projects/<slug>/<slug>.stl -D 'height=40' -D 'wall=2.4' projects/<slug>/<slug>.scad
openscad -o projects/<slug>/<slug>.stl -p params.json -P large projects/<slug>/<slug>.scad   # Customizer set
```
Use one mechanism per variable — `-D` may not override a value pinned by a Customizer set (openscad#4419).

## CadQuery (production)
Pin Python **3.12**; `pip install cadquery`. Export via the unified `.export()` (format inferred from extension) — there is no top-level `exportStl`/`exportStep` anymore.
```python
import cadquery as cq
part = cq.Workplane("XY").box(20, 20, 10)
part.export("projects/<slug>/<slug>.stl")    # mesh for slicing
part.export("projects/<slug>/<slug>.step")   # B-rep for archive/CAM
```

## Printability rules (FDM, 0.4 mm nozzle)
- Min wall ≥ 2 perimeters ≈ **0.8 mm**; prefer ≥ 1.2 mm for structure.
- Overhangs past ~45° need support — design to avoid them; orient to minimize.
- Fit clearance: **0.2 mm** loose / **0.1 mm** snug per mating face — tune with a printed tolerance test and log results to `tasks/lessons.md`.
- Avoid knife-edges on the bed; add a chamfer/base for adhesion.
- Vertical holes print undersized — oversize ~0.2–0.4 mm or model + ream.
- Encode print orientation in the model's intent (layer lines ⟂ to load).

## Preview — the visual self-correction loop
`scripts/render.sh <file.scad|.stl> [outdir]` renders iso/front/side/top PNGs headlessly (it locates the OpenSCAD app on macOS). For CLI work use **`scripts/project.sh render <slug>`**, which renders the source straight into `projects/<slug>/` so the PNGs + STL stay with the part. (`render.sh`'s bare default outdir is still `out/preview`, which the web bridge relies on — pass the project folder explicitly, or just use `project.sh render`.) The loop: **edit params → render → read the PNGs → fix what's wrong → re-render** (sub-second). Inspect your own geometry — wrong proportions, overhangs, parts clipping the build plate or each other — *before* exporting STL. Keep the OpenSCAD GUI open too; it live-reloads the file on each edit for interactive orbit.

## Hand-off
Export STL → `/slice`. For scanned references, run `/scan-cleanup` first, then reverse-engineer dimensions into a CadQuery model — don't slice raw scan meshes unless you deliberately want an as-scanned reprint.
