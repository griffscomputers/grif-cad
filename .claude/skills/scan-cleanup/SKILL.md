---
name: scan-cleanup
description: Clean a 3D-scanner point cloud or raw mesh into a watertight reference mesh for the grif-cad pipeline. Use when processing scanner output. Drives pymeshlab (load → normals → Poisson reconstruction → decimate → export). CloudCompare can pre-process but cannot run Poisson headlessly.
argument-hint: <part-slug>
---

# scan-cleanup

Turn raw scan data in `scans/raw/<slug>.ply` into a clean mesh in `scans/clean/<slug>.ply`.

Tool: **pymeshlab** (`pip install pymeshlab`). `meshlabserver` is removed from modern MeshLab — do not use it. CloudCompare's CLI is fine for normals/registration/scaling but its Poisson plugin has **no CLI**, so keep Poisson in pymeshlab.

## Pipeline
```python
import pymeshlab as ml
ms = ml.MeshSet()
ms.load_new_mesh("scans/raw/<slug>.ply")
ms.compute_normal_for_point_clouds()                      # if input is a point cloud
ms.generate_surface_reconstruction_screened_poisson()     # watertight surface
ms.meshing_decimation_quadric_edge_collapse(targetfacenum=200000)
ms.save_current_mesh("scans/clean/<slug>.ply")
```
Wrapper: `python scripts/clean_scan.py <slug> [target_faces]`.

## After cleanup
- **Verify scale** against a known caliper measurement on the real object before trusting any dimension — scanners drift.
- A cleaned mesh is a **reference**, not a print target. Reverse-engineer key dimensions into a CadQuery model (`/cad-scripting`) rather than slicing the scan mesh directly — unless you deliberately want an organic as-scanned reprint.
