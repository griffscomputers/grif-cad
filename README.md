# grif-cad

A Claude Code harness for a home **CAD → slice → print** pipeline, targeting a Creality K2 Plus. Describe a part, prototype it in OpenSCAD or build it in CadQuery, clean a 3D scan into a reference, slice with OrcaSlicer, and print over Moonraker — with a human confirmation gate before any physical print.

Operate this from inside Claude Code: the skills drive each stage — `/cad-scripting`, `/scan-cleanup`, `/slice`, `/print`. See `CLAUDE.md` for the pipeline, engine-selection rule, and safety rules.

## Setup
- Install: OpenSCAD, OrcaSlicer, and (Python 3.12) `pip install cadquery pymeshlab`.
- `cp config/printer.env.example config/printer.env` and set `K2_PLUS_HOST` to the printer's LAN address.
- Export the K2 Plus machine/process/filament presets from the OrcaSlicer GUI into `profiles/`.
