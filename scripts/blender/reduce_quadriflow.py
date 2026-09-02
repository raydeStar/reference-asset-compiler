"""Create a direct QuadriFlow production-retopology challenger from a clean mesh."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bmesh
import bpy
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_manifold import audit  # noqa: E402


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def triangle_count(obj: bpy.types.Object) -> int:
    return sum(max(0, len(face.vertices) - 2) for face in obj.data.polygons)


def topology(obj: bpy.types.Object) -> dict[str, int | float]:
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    quads = sum(len(face.verts) == 4 for face in bm.faces)
    result = {
        "vertices": len(bm.verts),
        "polygons": len(bm.faces),
        "triangles": triangle_count(obj),
        "quads": quads,
        "quad_fraction": quads / max(1, len(bm.faces)),
        "boundary_edges": sum(edge.is_boundary for edge in bm.edges),
        "nonmanifold_edges": sum(not edge.is_manifold for edge in bm.edges),
    }
    bm.free()
    return result


def world_geometry(obj: bpy.types.Object) -> tuple[list[tuple[float, float, float]], list[tuple[int, ...]]]:
    matrix = obj.matrix_world
    vertices = [tuple(matrix @ vertex.co) for vertex in obj.data.vertices]
    polygons = [tuple(face.vertices) for face in obj.data.polygons]
    return vertices, polygons


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def symmetric_deviation(
    source: bpy.types.Object, candidate: bpy.types.Object, samples: int = 10_000
) -> dict[str, float | int]:
    source_vertices, source_faces = world_geometry(source)
    candidate_vertices, candidate_faces = world_geometry(candidate)
    source_tree = BVHTree.FromPolygons(source_vertices, source_faces, all_triangles=False)
    candidate_tree = BVHTree.FromPolygons(
        candidate_vertices, candidate_faces, all_triangles=False)
    source_stride = max(1, len(source_vertices) // samples)
    candidate_stride = max(1, len(candidate_vertices) // samples)
    distances: list[float] = []
    for point in source_vertices[::source_stride]:
        hit = candidate_tree.find_nearest(point)
        if hit[0] is not None:
            distances.append(float(hit[3]))
    for point in candidate_vertices[::candidate_stride]:
        hit = source_tree.find_nearest(point)
        if hit[0] is not None:
            distances.append(float(hit[3]))
    if not distances:
        raise RuntimeError("Surface deviation sampling found no comparable points")
    return {
        "samples": len(distances),
        "mean_m": sum(distances) / len(distances),
        "p95_m": percentile(distances, 0.95),
        "p99_m": percentile(distances, 0.99),
        "max_m": max(distances),
    }


def parse_args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output_blend", type=Path)
    parser.add_argument("review_glb", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--triangle-budget", type=int, default=20_000)
    parser.add_argument("--target-quads", type=int, default=9_000)
    parser.add_argument("--maximum-p99-m", type=float, default=0.005)
    parser.add_argument("--maximum-max-m", type=float, default=0.020)
    return parser.parse_args(values)


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    output_blend = args.output_blend.resolve()
    review_glb = args.review_glb.resolve()
    report_path = args.report.resolve()
    if source.suffix.lower() != ".blend" or not source.is_file():
        raise RuntimeError("Direct QuadriFlow requires a topology-verified .blend source")
    if any(path.exists() for path in (output_blend, review_glb, report_path)):
        raise RuntimeError("Direct QuadriFlow refuses to overwrite an existing attempt")
    if not 1_000 <= args.target_quads <= args.triangle_budget // 2:
        raise RuntimeError("Target quads must be between 1,000 and half the triangle budget")

    bpy.ops.wm.open_mainfile(filepath=str(source))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError("Direct QuadriFlow requires exactly one mesh object")
    authority = meshes[0]
    authority.name = "SRC_RAC_ApprovedCleanup"
    authority_topology = topology(authority)
    strict_preflight = audit(authority)
    if not strict_preflight["quadriflow_preconditions_ok"]:
        raise RuntimeError(
            "QuadriFlow strict preflight failed: {0} short edges, {1} nonmanifold "
            "edges, {2} winding defects. Run the read-only manifold audit before "
            "selecting a bounded repair.".format(
                strict_preflight["edges_at_or_below_quadriflow_tolerance"],
                strict_preflight["nonmanifold_edges"],
                strict_preflight["inconsistent_winding_edges"],
            )
        )
    bpy.context.view_layer.objects.active = authority
    bpy.ops.object.select_all(action="DESELECT")
    authority.select_set(True)
    bpy.ops.object.duplicate()
    candidate = bpy.context.view_layer.objects.active
    candidate.name = "GEO_RAC_QuadriFlowCandidate"
    result = bpy.ops.object.quadriflow_remesh(
        use_mesh_symmetry=False,
        use_preserve_sharp=True,
        use_preserve_boundary=False,
        preserve_attributes=False,
        smooth_normals=True,
        mode="FACES",
        target_faces=args.target_quads,
        seed=0,
    )
    if "FINISHED" not in result:
        raise RuntimeError("QuadriFlow refused the clean authority: {0}".format(sorted(result)))
    candidate_topology = topology(candidate)
    deviation = symmetric_deviation(authority, candidate)
    finite = all(
        math.isfinite(value)
        for vertex in candidate.data.vertices
        for value in vertex.co
    )
    failures = []
    if candidate_topology["triangles"] > args.triangle_budget:
        failures.append("triangle budget exceeded")
    if candidate_topology["quad_fraction"] < 0.90:
        failures.append("quad fraction is below 0.90")
    if candidate_topology["boundary_edges"] or candidate_topology["nonmanifold_edges"]:
        failures.append("candidate is not a closed two-manifold surface")
    if not finite:
        failures.append("candidate contains non-finite coordinates")
    if deviation["p99_m"] > args.maximum_p99_m:
        failures.append("p99 surface deviation exceeds {0} m".format(args.maximum_p99_m))
    if deviation["max_m"] > args.maximum_max_m:
        failures.append("maximum surface deviation exceeds {0} m".format(args.maximum_max_m))

    output_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    candidate.select_set(True)
    bpy.context.view_layer.objects.active = candidate
    bpy.ops.export_scene.gltf(
        filepath=str(review_glb), export_format="GLB", use_selection=True,
        export_materials="NONE")
    bpy.data.objects.remove(authority, do_unlink=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    report = {
        "schema": "reference-asset-compiler.production-retopology-candidate.v1",
        "status": "mechanical_pass" if not failures else "rejected",
        "source": {
            "path": str(source),
            "sha256": sha256_file(source),
            "topology": authority_topology,
            "strict_preflight": strict_preflight,
        },
        "backend": "Blender QuadriFlow direct",
        "settings": {
            "target_quads": args.target_quads,
            "triangle_budget": args.triangle_budget,
            "maximum_p99_m": args.maximum_p99_m,
            "maximum_max_m": args.maximum_max_m,
            "voxelization": False,
            "decimation_fallback": False,
        },
        "output": {
            "path": str(output_blend),
            "sha256": sha256_file(output_blend),
            "review_glb": str(review_glb),
            "review_glb_sha256": sha256_file(review_glb),
            **candidate_topology,
        },
        "symmetric_surface_deviation": deviation,
        "failures": failures,
        "requires_fixed_view_review": True,
        "requires_dense_to_runtime_texture_bake": True,
        "production_grade": False,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if failures:
        print("RAC_QUADRIFLOW_REJECTED report={0}".format(report_path), flush=True)
        return 1
    print("RAC_QUADRIFLOW_CANDIDATE_OK report={0}".format(report_path), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
