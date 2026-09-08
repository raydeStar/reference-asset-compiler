"""Add source-projectable samples to a bounded region of existing native quads.

This is downstream subdivision, not geometry acquisition or manual sculpting.
The separate source projection stage must place the new samples on the retained
AI authority. This intermediate is never a production approval.
"""
import argparse
import json
from pathlib import Path
import sys

import bmesh
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from project_retopology_surface import digest
from reduce_regional_autoremesher import object_topology


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--minimum-height-ratio", type=float, required=True)
    parser.add_argument("--maximum-height-ratio", type=float, default=1.0)
    parser.add_argument("--front-only", action="store_true")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    source, destination = args.source.resolve(), args.destination.resolve()
    if destination.exists():
        raise RuntimeError("Retained candidates do not enter the recycling chute")
    if not 0 <= args.minimum_height_ratio < args.maximum_height_ratio <= 1:
        raise ValueError("Invalid bounded refinement region")
    bpy.ops.wm.open_mainfile(filepath=str(source))
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError("Refinement requires an isolated native retopology mesh")
    obj = meshes[0]
    before = object_topology(obj)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    low, high = min(v.co.z for v in bm.verts), max(v.co.z for v in bm.verts)
    z0 = low + (high - low) * args.minimum_height_ratio
    z1 = low + (high - low) * args.maximum_height_ratio
    middle_y = (min(v.co.y for v in bm.verts) + max(v.co.y for v in bm.verts)) / 2
    selected = [f for f in bm.faces if z0 <= f.calc_center_median().z <= z1
                and (not args.front_only or f.calc_center_median().y < middle_y)]
    edges = {e for f in selected for e in f.edges}
    bmesh.ops.subdivide_edges(bm, edges=list(edges), cuts=1, use_grid_fill=True,
                              smooth=0.0)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    after = object_topology(obj)
    failures = []
    if after["vertices"] > 15000 or after["triangles"] > 20000:
        failures.append("runtime budget exceeded")
    if after["boundary_edges"] or after["nonmanifold_edges"] or after["quad_fraction"] < .8:
        failures.append("closed quad-dominant topology requirement failed")
    destination.mkdir(parents=True)
    output = destination / "refined.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    report = {"source": {"path": str(source), "sha256": digest(source)},
              "output": {"path": str(output), "sha256": digest(output)},
              "region": {"minimum_height_ratio": args.minimum_height_ratio,
                         "maximum_height_ratio": args.maximum_height_ratio,
                         "front_only": args.front_only, "selected_faces": len(selected)},
              "before": before, "after": after, "failures": failures,
              "requires_source_projection": True, "production_grade": False}
    (destination / "refinement.json").write_text(json.dumps(report, indent=2) + "\n")
    print("REFINEMENT_COUNTS", json.dumps(report))
    if failures:
        raise RuntimeError("Refinement retained for diagnosis, not promotion")


if __name__ == "__main__":
    main()
