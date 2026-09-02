"""Create an immutable-source AutoRemesher reduction candidate.

This is a challenger, not automatic promotion. It emits topology evidence and
an untextured GLB plus Blender file. Fixed-view silhouette review and texture
baking against the dense authority remain downstream gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bmesh
import bpy


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def triangles(obj) -> int:
    return sum(max(0, len(polygon.vertices) - 2) for polygon in obj.data.polygons)


def parse_args():
    arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--triangle-budget", type=int, default=20_000)
    parser.add_argument("--target-quads", type=int, default=9_000)
    parser.add_argument("--adaptivity", type=float, default=0.5)
    parser.add_argument("--island-detail", type=int, default=10)
    parser.add_argument("--weld-shells", action="store_true")
    return parser.parse_args(arguments)


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    report_path = args.report.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if output.exists() or output.with_suffix(".blend").exists() or report_path.exists():
        raise RuntimeError("Refusing to overwrite an existing reduction candidate")
    # AutoRemesher's target is advisory. The retained female canary requested
    # 9,000 quads and returned 4,590 quads / 9,774 triangles. Permit a target
    # up to the triangle budget and let the measured output gate decide; the
    # old half-budget restriction made calibrated runs impossible while adding
    # no safety, because the post-run triangle check is already authoritative.
    if not 1_000 <= args.target_quads <= args.triangle_budget:
        raise RuntimeError("Target quads must be between 1,000 and the triangle budget")
    if not hasattr(bpy.context.scene, "autoremesher"):
        raise RuntimeError("AutoRemesher extension is not enabled")

    # Do not factory-reset: Blender's extension preference is the licensed
    # runtime under test. Native .blend transport preserves shared topology;
    # GLB may split vertices at face-corner normals and turn a closed surface
    # into hundreds of thousands of disconnected edges on re-import.
    if source.suffix.lower() == ".blend":
        bpy.ops.wm.open_mainfile(filepath=str(source))
    else:
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
        bpy.ops.import_scene.gltf(filepath=str(source))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError("Source contains no meshes")
    inventory = [
        {"name": obj.name, "vertices": len(obj.data.vertices), "triangles": triangles(obj)}
        for obj in sorted(meshes, key=lambda item: item.name)
    ]
    bpy.ops.object.select_all(action="DESELECT")
    for mesh in meshes:
        mesh.select_set(True)
    source_obj = max(meshes, key=lambda item: len(item.data.polygons))
    bpy.context.view_layer.objects.active = source_obj
    if len(meshes) > 1:
        bpy.ops.object.join()
    source_obj.name = "SRC_RAC_DenseAuthority"
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    source_triangles = triangles(source_obj)

    settings = bpy.context.scene.autoremesher
    settings.target_quad_count = args.target_quads
    settings.edge_scaling = 1.0
    settings.adaptivity = args.adaptivity
    settings.sharp_edge = math.radians(100.0)
    settings.smooth_normal = math.radians(90.0)
    settings.island_detail = args.island_detail
    settings.preserve_thin = True
    settings.weld_shells = args.weld_shells
    result = bpy.ops.object.autoremesher_remesh()
    if "FINISHED" not in result:
        raise RuntimeError("AutoRemesher failed: {0}".format(sorted(result)))
    candidates = [
        obj for obj in bpy.context.scene.objects
        if obj.type == "MESH" and obj != source_obj
    ]
    if len(candidates) != 1:
        raise RuntimeError("Expected one reduction candidate, found {0}".format(len(candidates)))
    candidate = candidates[0]
    candidate.name = "GEO_RAC_AutoRemesherCandidate"
    candidate_triangles = triangles(candidate)
    quads = sum(len(polygon.vertices) == 4 for polygon in candidate.data.polygons)
    quad_fraction = quads / max(1, len(candidate.data.polygons))
    finite = all(
        math.isfinite(component)
        for vertex in candidate.data.vertices
        for component in vertex.co
    )
    bm = bmesh.new()
    bm.from_mesh(candidate.data)
    boundary_edges = sum(edge.is_boundary for edge in bm.edges)
    nonmanifold_edges = sum(not edge.is_manifold for edge in bm.edges)
    bm.free()
    failures = []
    if candidate_triangles > args.triangle_budget:
        failures.append(
            "{0} triangles exceeds budget {1}".format(
                candidate_triangles, args.triangle_budget
            )
        )
    if quad_fraction < 0.80:
        failures.append("quad fraction {0:.3f} is below 0.80".format(quad_fraction))
    if boundary_edges:
        failures.append(
            "candidate has {0} boundary edges; production retopology must be closed".format(
                boundary_edges
            )
        )
    if nonmanifold_edges:
        failures.append(
            "candidate has {0} non-manifold edges; production retopology must be manifold".format(
                nonmanifold_edges
            )
        )
    if not finite:
        failures.append("candidate contains non-finite coordinates")

    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    for polygon in candidate.data.polygons:
        polygon.use_smooth = True
    candidate.data.materials.clear()
    bpy.ops.object.select_all(action="DESELECT")
    candidate.select_set(True)
    bpy.context.view_layer.objects.active = candidate
    bpy.ops.export_scene.gltf(
        filepath=str(output), export_format="GLB", use_selection=True,
        export_materials="NONE",
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(output.with_suffix(".blend")))
    report = {
        "schema": "reference-asset-compiler.reduction-candidate.v1",
        "status": "mechanical_pass" if not failures else "rejected",
        "source": {"path": str(source), "sha256": sha256(source),
                   "parts": inventory, "triangles": source_triangles},
        "backend": "AutoRemesher",
        "settings": {"target_quads": args.target_quads,
                     "triangle_budget": args.triangle_budget,
                     "adaptivity": args.adaptivity,
                     "island_detail": args.island_detail,
                     "preserve_thin": True, "weld_shells": args.weld_shells},
        "output": {"path": str(output), "sha256": sha256(output),
                   "vertices": len(candidate.data.vertices),
                   "polygons": len(candidate.data.polygons),
                   "triangles": candidate_triangles, "quads": quads,
                   "quad_fraction": quad_fraction,
                   "boundary_edges": boundary_edges,
                   "nonmanifold_edges": nonmanifold_edges},
        "failures": failures,
        "requires_fixed_view_review": True,
        "requires_texture_bake_from_dense_authority": True,
        "production_grade": False,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if failures:
        print("RAC_REDUCTION_REJECTED report={0}".format(report_path))
        return 1
    print("RAC_REDUCTION_CANDIDATE_OK report={0}".format(report_path))
    print("The polygon count bows politely; the silhouette must still testify.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
