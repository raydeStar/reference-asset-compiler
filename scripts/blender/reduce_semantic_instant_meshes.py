"""Retopologize audited regions of one approved AI-derived mesh."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import bpy
import bmesh
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_semantic_retopology_regions import cut_closed_region  # noqa: E402
from reduce_instant_meshes import (  # noqa: E402
    evaluated_triangles,
    sha256_file,
    wait_for_session,
)
from reduce_quadriflow import symmetric_deviation, topology  # noqa: E402


def parse_args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("output_blend", type=Path)
    parser.add_argument("review_glb", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("remi_root", type=Path)
    parser.add_argument("remi_native", type=Path)
    parser.add_argument("--triangle-budget", type=int, default=20_000)
    parser.add_argument("--vertex-budget", type=int, default=15_000)
    parser.add_argument("--crease-angle-degrees", type=float, default=35.0)
    parser.add_argument("--maximum-p99-m", type=float, default=0.005)
    parser.add_argument("--maximum-max-m", type=float, default=0.020)
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    return parser.parse_args(values)


def build_combined_candidate(
    region_outputs: list[tuple[str, list[list[float]], list[list[int]]]],
    matrix_world,
) -> bpy.types.Object:
    all_vertices: list[list[float]] = []
    all_faces: list[list[int]] = []
    offset = 0
    for _name, vertices, faces in region_outputs:
        all_vertices.extend(vertices)
        all_faces.extend([[index + offset for index in face] for face in faces])
        offset += len(vertices)
    mesh = bpy.data.meshes.new("GEO_RAC_SemanticInstantMeshesCandidate")
    mesh.from_pydata(all_vertices, [], all_faces)
    mesh.validate(verbose=True)
    mesh.update(calc_edges=True)
    candidate = bpy.data.objects.new(mesh.name, mesh)
    bpy.context.collection.objects.link(candidate)
    candidate.matrix_world = matrix_world.copy()
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    return candidate


def close_extracted_region(
    name: str, vertices: np.ndarray, faces: np.ndarray
) -> tuple[list[list[float]], list[list[int]], dict[str, int | float]]:
    mesh = bpy.data.meshes.new("TMP_RAC_{0}".format(name))
    mesh.from_pydata(vertices.tolist(), [], faces.tolist())
    mesh.update(calc_edges=True)
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        boundaries = [edge for edge in bm.edges if edge.is_boundary]
        fill = bmesh.ops.holes_fill(bm, edges=boundaries, sides=0)
        bm.normal_update()
        bm.to_mesh(mesh)
        closure = {
            "boundary_edges_before_post_close": len(boundaries),
            "post_solver_cap_faces": len(fill.get("faces", [])),
        }
    finally:
        bm.free()
    mesh.validate(verbose=True)
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new(mesh.name, mesh)
    bpy.context.collection.objects.link(obj)
    stats = topology(obj)
    closure.update(stats)
    closed_vertices = [list(vertex.co) for vertex in mesh.vertices]
    closed_faces = [list(polygon.vertices) for polygon in mesh.polygons]
    bpy.data.objects.remove(obj, do_unlink=True)
    return closed_vertices, closed_faces, closure


def main() -> int:
    args = parse_args()
    paths = [
        args.source.resolve(),
        args.profile.resolve(),
        args.output_blend.resolve(),
        args.review_glb.resolve(),
        args.report.resolve(),
        args.remi_root.resolve(),
        args.remi_native.resolve(),
    ]
    source, profile_path, output_blend, review_glb, report_path, remi_root, remi_native = paths
    if any(path.exists() for path in (output_blend, review_glb, report_path)):
        raise RuntimeError("Semantic Instant Meshes refuses to overwrite an attempt")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    if profile["source_sha256"] != sha256_file(source):
        raise RuntimeError("Semantic profile is not bound to this AI-derived authority")
    sys.path.insert(0, str(remi_root))
    from remi.instant_meshes._native import Session  # noqa: PLC0415

    bpy.ops.wm.open_mainfile(filepath=str(source))
    sources = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(sources) != 1:
        raise RuntimeError("Semantic retopology requires exactly one source mesh")
    authority = sources[0]
    authority.name = "SRC_RAC_ApprovedAI_Cleanup"
    source_topology = topology(authority)
    region_outputs: list[tuple[str, list[list[float]], list[list[int]]]] = []
    region_records: list[dict[str, object]] = []
    for region in profile["regions"]:
        segmented, cut_records = cut_closed_region(authority, region, cap=False)
        segmented_topology = topology(segmented)
        vertices, triangles = evaluated_triangles(segmented)
        session = Session(
            vertices,
            triangles,
            target_faces=int(region["target_faces"]),
            pure_quad=True,
            crease_angle=args.crease_angle_degrees,
            extrinsic=True,
            align_boundaries=True,
            deterministic=True,
            smooth_iterations=2,
        )
        session.start_orientation()
        orientation_seconds = wait_for_session(session, "orientation", args.timeout_seconds)
        session.start_position()
        position_seconds = wait_for_session(session, "position", args.timeout_seconds)
        if not session.position_solved:
            raise RuntimeError("Region {0} did not solve".format(region["id"]))
        output_vertices, output_faces, _normals = session.extract()
        vertices_array = np.asarray(output_vertices, dtype=np.float32)
        faces_array = np.asarray(output_faces, dtype=np.int32)
        closed_vertices, closed_faces, closure = close_extracted_region(
            str(region["id"]), vertices_array, faces_array
        )
        region_outputs.append((str(region["id"]), closed_vertices, closed_faces))
        region_records.append(
            {
                "id": region["id"],
                "target_faces": region["target_faces"],
                "segmented_source_topology": segmented_topology,
                "cuts": cut_records,
                "native_output_topology": dict(session.output_topology),
                "post_solver_closure": closure,
                "timing_seconds": {
                    "orientation": orientation_seconds,
                    "position": position_seconds,
                },
            }
        )
        session.stop()
        bpy.data.objects.remove(segmented, do_unlink=True)

    candidate = build_combined_candidate(region_outputs, authority.matrix_world)
    candidate_topology = topology(candidate)
    deviation = symmetric_deviation(authority, candidate)
    failures: list[str] = []
    if candidate_topology["vertices"] > args.vertex_budget:
        failures.append("vertex budget exceeded")
    if candidate_topology["triangles"] > args.triangle_budget:
        failures.append("triangle budget exceeded")
    if candidate_topology["quad_fraction"] < 0.80:
        failures.append("quad fraction is below 0.80")
    if candidate_topology["boundary_edges"] or candidate_topology["nonmanifold_edges"]:
        failures.append("combined candidate is not closed two-manifold")
    if not all(math.isfinite(value) for vertex in candidate.data.vertices for value in vertex.co):
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
        filepath=str(review_glb), export_format="GLB", use_selection=True, export_materials="NONE"
    )
    bpy.data.objects.remove(authority, do_unlink=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    report = {
        "schema": "reference-asset-compiler.semantic-production-retopology-candidate.v1",
        "status": "mechanical_pass" if not failures else "rejected",
        "purpose": "Downstream region-aware retopology of approved AI geometry; not image reconstruction.",
        "source": {"path": str(source), "sha256": sha256_file(source), "topology": source_topology},
        "profile": {"path": str(profile_path), "sha256": sha256_file(profile_path)},
        "backend": "Remi Instant Meshes field solver",
        "backend_provenance": {
            "remi_version": "1.13.1",
            "native_module": str(remi_native),
            "native_module_sha256": sha256_file(remi_native),
            "instant_meshes_commit": "7b3160864a2e1025af498c84cfed91cbfb613698",
        },
        "regions": region_records,
        "output": {
            "path": str(output_blend),
            "sha256": sha256_file(output_blend),
            "review_glb": str(review_glb),
            "review_glb_sha256": sha256_file(review_glb),
            "closed_components_expected": len(region_outputs),
            **candidate_topology,
        },
        "symmetric_surface_deviation": deviation,
        "failures": failures,
        "requires_fixed_view_review": True,
        "requires_seam_closeup_review": True,
        "requires_dense_to_runtime_texture_bake": True,
        "production_grade": False,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("RAC_SEMANTIC_INSTANT_MESHES_{0} report={1}".format(
        "CANDIDATE_OK" if not failures else "REJECTED", report_path
    ))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
