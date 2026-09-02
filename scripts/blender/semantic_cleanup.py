"""Conservatively sanitize an approved AI modeling mesh without changing its shape."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def measure(obj: bpy.types.Object) -> dict[str, object]:
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    invalid_vertices = sum(
        not all(math.isfinite(value) for value in vertex.co) for vertex in bm.verts)
    degenerate_faces = sum(face.calc_area() <= 1.0e-12 for face in bm.faces)
    loose_vertices = sum(not vertex.link_edges and not vertex.link_faces for vertex in bm.verts)
    seen: set[int] = set()
    components = 0
    for vertex in bm.verts:
        if vertex.index in seen:
            continue
        components += 1
        seen.add(vertex.index)
        stack = [vertex]
        while stack:
            current = stack.pop()
            for edge in current.link_edges:
                other = edge.other_vert(current)
                if other.index not in seen:
                    seen.add(other.index)
                    stack.append(other)
    result = {
        "vertices": len(bm.verts),
        "faces": len(bm.faces),
        "components": components,
        "boundary_edges": sum(edge.is_boundary for edge in bm.edges),
        "non_manifold_edges": sum(not edge.is_manifold for edge in bm.edges),
        "invalid_vertices": invalid_vertices,
        "degenerate_faces": degenerate_faces,
        "loose_vertices": loose_vertices,
    }
    bm.free()
    return result


def bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return (
        Vector(tuple(min(point[index] for point in points) for index in range(3))),
        Vector(tuple(max(point[index] for point in points) for index in range(3))),
    )


def import_mesh(path: Path) -> bpy.types.Object:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    suffix = path.suffix.lower()
    if suffix in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path))
    else:
        raise RuntimeError("Semantic cleanup supports GLB, glTF, and FBX inputs")
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError("Semantic cleanup requires exactly one mesh object; found {0}".format(
            len(meshes)))
    return meshes[0]


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:]
    if len(argv) != 3:
        raise RuntimeError("Usage: semantic_cleanup.py <input> <output.blend> <report.json>")
    source, output, report_path = (Path(value).resolve() for value in argv)
    if output.exists() or report_path.exists():
        raise RuntimeError("Semantic cleanup refuses to overwrite an existing attempt")
    obj = import_mesh(source)
    before = measure(obj)
    before_min, before_max = bounds(obj)

    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1.0e-6)
    degenerate = [face for face in bm.faces if face.calc_area() <= 1.0e-12]
    if degenerate:
        bmesh.ops.delete(bm, geom=degenerate, context="FACES_ONLY")
    loose = [vertex for vertex in bm.verts if not vertex.link_edges and not vertex.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()

    after = measure(obj)
    after_min, after_max = bounds(obj)
    bbox_drift = max(
        *(abs(before_min[index] - after_min[index]) for index in range(3)),
        *(abs(before_max[index] - after_max[index]) for index in range(3)),
    )
    ok = (
        after["invalid_vertices"] == 0
        and after["degenerate_faces"] == 0
        and after["loose_vertices"] == 0
        and after["faces"] >= int(before["faces"] * 0.995)
        and bbox_drift <= 1.0e-6
    )
    if not ok:
        raise RuntimeError("Conservative cleanup contract failed: before={0} after={1} drift={2}".format(
            before, after, bbox_drift))

    if output.suffix.lower() != ".blend":
        raise RuntimeError("Semantic cleanup requires native .blend output for topology fidelity")
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    bpy.ops.wm.open_mainfile(filepath=str(output))
    roundtrip_meshes = [item for item in bpy.context.scene.objects if item.type == "MESH"]
    if len(roundtrip_meshes) != 1:
        raise RuntimeError("Semantic cleanup round-trip changed mesh object count")
    roundtrip = measure(roundtrip_meshes[0])
    if roundtrip != after:
        raise RuntimeError("Semantic cleanup round-trip changed topology: after={0} roundtrip={1}".format(
            after, roundtrip))
    report = {
        "schema": "reference-asset-compiler.semantic-cleanup-topology.v1",
        "source": str(source),
        "source_sha256": sha256_file(source),
        "output": str(output),
        "output_sha256": sha256_file(output),
        "operations": [
            "weld_coincident_vertices",
            "remove_degenerate_faces",
            "remove_loose_vertices",
            "recalculate_normals",
        ],
        "before": before,
        "after": after,
        "roundtrip": roundtrip,
        "bbox_max_drift_m": bbox_drift,
        "ok": True,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("RAC_SEMANTIC_CLEANUP_OK " + json.dumps(report, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
