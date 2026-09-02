"""Create one field- and crease-guided Instant Meshes retopology challenger."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
import time

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reduce_quadriflow import (  # noqa: E402
    sha256_file,
    symmetric_deviation,
    topology,
)


def parse_args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output_blend", type=Path)
    parser.add_argument("review_glb", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("remi_root", type=Path)
    parser.add_argument("remi_native", type=Path)
    parser.add_argument("--target-faces", type=int, default=9_000)
    parser.add_argument("--triangle-budget", type=int, default=20_000)
    parser.add_argument("--crease-angle-degrees", type=float, default=35.0)
    parser.add_argument("--maximum-p99-m", type=float, default=0.005)
    parser.add_argument("--maximum-max-m", type=float, default=0.020)
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    return parser.parse_args(values)


def evaluated_triangles(obj: bpy.types.Object) -> tuple[np.ndarray, np.ndarray]:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        mesh.calc_loop_triangles()
        vertices = np.empty((len(mesh.vertices), 3), dtype=np.float32)
        mesh.vertices.foreach_get("co", vertices.ravel())
        triangles = np.empty((len(mesh.loop_triangles), 3), dtype=np.int32)
        mesh.loop_triangles.foreach_get("vertices", triangles.ravel())
        return vertices, triangles
    finally:
        evaluated.to_mesh_clear()


def wait_for_session(session, stage: str, timeout_seconds: float) -> float:
    started = time.monotonic()
    while session.active:
        if time.monotonic() - started > timeout_seconds:
            session.stop()
            raise RuntimeError(
                "Instant Meshes {0} solve exceeded {1:.1f} seconds".format(
                    stage, timeout_seconds
                )
            )
        time.sleep(0.02)
    return time.monotonic() - started


def build_candidate(vertices: np.ndarray, faces: np.ndarray) -> bpy.types.Object:
    mesh = bpy.data.meshes.new("GEO_RAC_InstantMeshesCandidate")
    mesh.from_pydata(vertices.tolist(), [], faces.tolist())
    mesh.validate(verbose=True)
    mesh.update(calc_edges=True)
    candidate = bpy.data.objects.new(mesh.name, mesh)
    bpy.context.collection.objects.link(candidate)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    mesh.update()
    return candidate


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    output_blend = args.output_blend.resolve()
    review_glb = args.review_glb.resolve()
    report_path = args.report.resolve()
    remi_root = args.remi_root.resolve()
    remi_native = args.remi_native.resolve()
    if source.suffix.lower() != ".blend" or not source.is_file():
        raise RuntimeError("Instant Meshes requires a topology-verified .blend source")
    if not (remi_root / "remi" / "__init__.py").is_file():
        raise RuntimeError("Remi root must contain remi/__init__.py")
    if not remi_native.is_file() or remi_native.suffix.lower() != ".pyd":
        raise RuntimeError("A verified Windows Remi native module is required")
    if any(path.exists() for path in (output_blend, review_glb, report_path)):
        raise RuntimeError("Instant Meshes refuses to overwrite an existing attempt")
    if not 1_000 <= args.target_faces <= args.triangle_budget // 2:
        raise RuntimeError("Target faces must be between 1,000 and half the triangle budget")

    sys.path.insert(0, str(remi_root))
    from remi.instant_meshes._native import Session  # noqa: PLC0415

    bpy.ops.wm.open_mainfile(filepath=str(source))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError("Instant Meshes requires exactly one mesh object")
    authority = meshes[0]
    authority.name = "SRC_RAC_ApprovedCleanup"
    authority_topology = topology(authority)
    vertices, triangles = evaluated_triangles(authority)

    session = Session(
        vertices,
        triangles,
        target_faces=args.target_faces,
        pure_quad=True,
        crease_angle=args.crease_angle_degrees,
        extrinsic=True,
        align_boundaries=True,
        deterministic=True,
        smooth_iterations=2,
    )
    session.start_orientation()
    orientation_seconds = wait_for_session(
        session, "orientation", args.timeout_seconds
    )
    session.start_position()
    position_seconds = wait_for_session(session, "position", args.timeout_seconds)
    if not session.position_solved:
        raise RuntimeError("Instant Meshes did not produce a solved position field")
    extracted_vertices, extracted_faces, _normals = session.extract()
    output_topology = dict(session.output_topology)
    candidate = build_candidate(
        np.asarray(extracted_vertices, dtype=np.float32),
        np.asarray(extracted_faces, dtype=np.int32),
    )
    candidate.matrix_world = authority.matrix_world.copy()
    candidate_topology = topology(candidate)
    deviation = symmetric_deviation(authority, candidate)
    finite = all(
        math.isfinite(value)
        for vertex in candidate.data.vertices
        for value in vertex.co
    )
    failures: list[str] = []
    if candidate_topology["triangles"] > args.triangle_budget:
        failures.append("triangle budget exceeded")
    if candidate_topology["quad_fraction"] < 0.80:
        failures.append("quad fraction is below the articulated 0.80 contract")
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
        filepath=str(review_glb),
        export_format="GLB",
        use_selection=True,
        export_materials="NONE",
    )
    bpy.data.objects.remove(authority, do_unlink=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    report = {
        "schema": "reference-asset-compiler.production-retopology-candidate.v1",
        "status": "mechanical_pass" if not failures else "rejected",
        "source": {
            "path": str(source),
            "sha256": sha256_file(source),
            "topology": authority_topology,
        },
        "backend": "Remi Instant Meshes field solver",
        "backend_provenance": {
            "remi_version": "1.13.1",
            "remi_root": str(remi_root),
            "native_module": str(remi_native),
            "native_module_sha256": sha256_file(remi_native),
            "instant_meshes_commit": "7b3160864a2e1025af498c84cfed91cbfb613698",
            "tbb_commit": "550c18b1132ae1b06285b2488f0344617c46f0ed",
            "eigen_commit": "c34a9130bc585b288703bd9716d7efae194974e2",
        },
        "settings": {
            "target_faces": args.target_faces,
            "triangle_budget": args.triangle_budget,
            "pure_quad": True,
            "crease_angle_degrees": args.crease_angle_degrees,
            "extrinsic": True,
            "align_boundaries": True,
            "deterministic": True,
            "smooth_iterations": 2,
            "explicit_surface_strokes": 0,
            "source_crease_guidance": True,
            "maximum_p99_m": args.maximum_p99_m,
            "maximum_max_m": args.maximum_max_m,
        },
        "timing_seconds": {
            "orientation": orientation_seconds,
            "position": position_seconds,
        },
        "native_output_topology": output_topology,
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
    session.stop()
    if failures:
        print("RAC_INSTANT_MESHES_REJECTED report={0}".format(report_path), flush=True)
        return 1
    print("RAC_INSTANT_MESHES_CANDIDATE_OK report={0}".format(report_path), flush=True)
    print("The field has spoken; the fixed views retain the right of appeal.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
