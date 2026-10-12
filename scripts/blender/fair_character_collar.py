"""Fair a bounded acquired collar edge without replacing the head or its skin.

The source hash, measured region and displacement ceiling are mandatory. UVs,
topology, skin weights, all other meshes and every bone remain unchanged.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import bmesh
import bpy


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--object", required=True)
    parser.add_argument("--box", nargs=6, type=float, required=True,
                        metavar=("X0", "X1", "Y0", "Y1", "Z0", "Z1"))
    parser.add_argument("--max-displacement-m", type=float, default=0.008)
    parser.add_argument("--iterations", type=int, default=20)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    if args.max_displacement_m <= 0 or args.iterations < 1:
        raise ValueError("Use a positive displacement ceiling and iteration count")
    source, out = args.source.resolve(), args.out.resolve()
    if sha(source) != args.source_sha256:
        raise ValueError("Source changed; this tailor requires the correct customer, sir.")
    if out.exists():
        raise FileExistsError("Keep previous evidence; choose a fresh output directory")
    out.mkdir(parents=True)
    bpy.ops.wm.open_mainfile(filepath=str(source))
    obj = bpy.data.objects[args.object]
    if any(abs(s - 1.0) > 1e-5 for s in obj.matrix_world.to_scale()):
        raise ValueError("Apply mesh scale first so the displacement ceiling is measured in metres")
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    original = {v: v.co.copy() for v in bm.verts}
    box = args.box

    def inside(vertex):
        p = obj.matrix_world @ vertex.co
        return all(box[2*i] <= p[i] <= box[2*i+1] for i in range(3))

    boundary = {v for v in bm.verts if inside(v) and any(e.is_boundary for e in v.link_edges)}
    if not boundary:
        raise ValueError("No collar boundary inside the measured box")
    affected = set(boundary)
    for vertex in list(boundary):
        affected.update(e.other_vert(vertex) for e in vertex.link_edges if inside(e.other_vert(vertex)))
    for _ in range(args.iterations):
        changes = {}
        for vertex in affected:
            neighbours = [e.other_vert(vertex) for e in vertex.link_edges
                          if vertex not in boundary or e.is_boundary]
            if not neighbours:
                continue
            mean = sum((v.co for v in neighbours), vertex.co * 0) / len(neighbours)
            candidate = vertex.co.lerp(mean, 0.35 if vertex in boundary else 0.12)
            delta = candidate - original[vertex]
            if delta.length > args.max_displacement_m:
                candidate = original[vertex] + delta.normalized() * args.max_displacement_m
            changes[vertex] = candidate
        for vertex, value in changes.items():
            vertex.co = value
    changed = {v.index: (v.co - original[v]).length for v in affected if (v.co - original[v]).length > 1e-7}
    # Write only coordinates: bmesh round-trips can discard custom loop normals.
    for vertex in affected:
        obj.data.vertices[vertex.index].co = vertex.co
    bm.free()
    obj.data.update()
    target = out / "Character02_UE5_seams.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(target), copy=True)
    report = {"source": str(source), "source_sha256": args.source_sha256,
              "script_sha256": sha(__file__), "blender": bpy.app.version_string,
              "box": box, "iterations": args.iterations,
              "max_displacement_m": args.max_displacement_m,
              "changed_vertices": len(changed), "boundary_vertices": len(boundary),
              "measured_max_displacement_m": max(changed.values(), default=0),
              "output_sha256": sha(target), "production_ready": False}
    (out / "collar.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("COLLAR: a bounded fitting, sir; no borrowed face. " + json.dumps(report))


if __name__ == "__main__":
    main()
