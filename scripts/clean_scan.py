#!/usr/bin/env python3
"""Clean a raw 3D scan into a watertight reference mesh.

Usage:  python scripts/clean_scan.py <slug> [target_faces]
Reads:  scans/raw/<slug>.ply   Writes: scans/clean/<slug>.ply

Uses pymeshlab (meshlabserver is removed in modern MeshLab). The normals step
assumes point-cloud input; drop it if the source is already a normal-bearing mesh.

SCAFFOLD — validate against real scanner output on first run; tune target_faces
and Poisson depth to the object. Always verify scale against a caliper measurement.
"""
import sys
from pathlib import Path

import pymeshlab as ml


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: clean_scan.py <slug> [target_faces]")
    slug = sys.argv[1]
    target = int(sys.argv[2]) if len(sys.argv) > 2 else 200_000

    src = Path(f"scans/raw/{slug}.ply")
    dst = Path(f"scans/clean/{slug}.ply")
    if not src.exists():
        sys.exit(f"no scan at {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)

    ms = ml.MeshSet()
    ms.load_new_mesh(str(src))
    ms.compute_normal_for_point_clouds()                    # point-cloud input
    ms.generate_surface_reconstruction_screened_poisson()   # watertight surface
    ms.meshing_decimation_quadric_edge_collapse(targetfacenum=target)
    ms.save_current_mesh(str(dst))
    print(f"wrote {dst}")


if __name__ == "__main__":
    main()
