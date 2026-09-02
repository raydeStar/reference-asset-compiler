"""Create one explicit joint-guide-driven Instant Meshes challenger."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reduce_instant_meshes import (  # noqa: E402
    build_candidate,
    evaluated_triangles,
    sha256_file,
    wait_for_session,
)
from reduce_quadriflow import symmetric_deviation, topology  # noqa: E402


def parse_args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("guide_report", type=Path)
    parser.add_argument("guide_decision", type=Path)
    parser.add_argument("output_blend", type=Path)
    parser.add_argument("review_glb", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("remi_root", type=Path)
    parser.add_argument("remi_native", type=Path)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--target-faces", type=int, default=10_000)
    parser.add_argument("--triangle-budget", type=int, default=20_000)
    parser.add_argument("--crease-angle-degrees", type=float, default=35.0)
    parser.add_argument("--maximum-p99-m", type=float, default=0.005)
    parser.add_argument("--maximum-max-m", type=float, default=0.020)
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    return parser.parse_args(values)


def accepted_decision(decision: dict, guide_hash: str, attempt_id: str) -> dict:
    accepted = [
        trial
        for trial in decision.get("trials", [])
        if trial.get("audit_report_sha256") == guide_hash
        and trial.get("decision") == "accepted_for_single_solver_attempt"
    ]
    attempts = [
        attempt
        for attempt in decision.get("solver_attempts", [])
        if attempt.get("id") == attempt_id
        and attempt.get("decision") == "authorized_after_diagnosis"
    ]
    if len(accepted) != 1 or len(attempts) != 1:
        raise RuntimeError("Guide audit or named solver attempt is not authorized")
    return accepted[0]


def stroke_arrays(guide: dict) -> tuple[np.ndarray, ...]:
    rings = guide.get("rings", [])
    if not rings:
        raise RuntimeError("Guide audit contains no rings")
    offsets = [0]
    positions: list[list[float]] = []
    normals: list[list[float]] = []
    faces: list[int] = []
    for ring in rings:
        hits = list(ring.get("hits", []))
        if (
            len(hits) > 2
            and hits[0]["face"] == hits[-1]["face"]
            and np.allclose(hits[0]["position"], hits[-1]["position"], atol=1.0e-7)
        ):
            hits.pop()
        if len(hits) < 3:
            raise RuntimeError("Each guide ring requires at least three hits")
        positions.extend(hit["position"] for hit in hits)
        normals.extend(hit["normal"] for hit in hits)
        faces.extend(int(hit["face"]) for hit in hits)
        offsets.append(len(positions))
    return (
        np.ones(len(rings), dtype=np.int32),
        np.asarray(offsets, dtype=np.int32),
        np.asarray(positions, dtype=np.float32),
        np.asarray(normals, dtype=np.float32),
        np.asarray(faces, dtype=np.int32),
    )


def main() -> int:
    args = parse_args()
    paths = [
        args.source.resolve(),
        args.guide_report.resolve(),
        args.guide_decision.resolve(),
        args.output_blend.resolve(),
        args.review_glb.resolve(),
        args.report.resolve(),
        args.remi_root.resolve(),
        args.remi_native.resolve(),
    ]
    source, guide_path, decision_path, output_blend, review_glb, report_path, remi_root, remi_native = paths
    if source.suffix.lower() != ".blend" or not source.is_file():
        raise RuntimeError("Guided retopology requires a topology-verified .blend source")
    if any(path.exists() for path in (output_blend, review_glb, report_path)):
        raise RuntimeError("Guided retopology refuses to overwrite an existing attempt")
    if not (remi_root / "remi" / "__init__.py").is_file():
        raise RuntimeError("Remi root must contain remi/__init__.py")
    if not remi_native.is_file() or remi_native.suffix.lower() != ".pyd":
        raise RuntimeError("A verified Windows Remi native module is required")
    if not 1_000 <= args.target_faces <= args.triangle_budget // 2:
        raise RuntimeError("Target faces must be between 1,000 and half the triangle budget")

    guide = json.loads(guide_path.read_text(encoding="utf-8"))
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    source_hash = sha256_file(source)
    guide_hash = sha256_file(guide_path)
    if guide.get("source", {}).get("sha256") != source_hash:
        raise RuntimeError("Guide audit is not bound to this AI-derived source")
    if decision.get("source_sha256") != source_hash:
        raise RuntimeError("Guide decision is not bound to this AI-derived source")
    accepted_trial = accepted_decision(decision, guide_hash, args.attempt_id)

    sys.path.insert(0, str(remi_root))
    from remi.instant_meshes._native import Session  # noqa: PLC0415

    bpy.ops.wm.open_mainfile(filepath=str(source))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError("Guided retopology requires exactly one mesh object")
    authority = meshes[0]
    authority.name = "SRC_RAC_ApprovedCleanup"
    authority_topology = topology(authority)
    vertices, triangles = evaluated_triangles(authority)
    strokes = stroke_arrays(guide)
    if np.max(strokes[4]) >= len(triangles):
        raise RuntimeError("Guide references a face outside the evaluated source mesh")

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
    session.set_strokes(*strokes)
    session.start_orientation()
    orientation_seconds = wait_for_session(session, "orientation", args.timeout_seconds)
    session.start_position()
    position_seconds = wait_for_session(session, "position", args.timeout_seconds)
    if not session.position_solved:
        raise RuntimeError("Guided Instant Meshes did not solve its position field")
    extracted_vertices, extracted_faces, _normals = session.extract()
    native_topology = dict(session.output_topology)
    candidate = build_candidate(
        np.asarray(extracted_vertices, dtype=np.float32),
        np.asarray(extracted_faces, dtype=np.int32),
    )
    candidate.matrix_world = authority.matrix_world.copy()
    candidate_topology = topology(candidate)
    deviation = symmetric_deviation(authority, candidate)
    finite = all(math.isfinite(value) for vertex in candidate.data.vertices for value in vertex.co)
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
        filepath=str(review_glb), export_format="GLB", use_selection=True, export_materials="NONE"
    )
    bpy.data.objects.remove(authority, do_unlink=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    report = {
        "schema": "reference-asset-compiler.guided-production-retopology-candidate.v1",
        "status": "mechanical_pass" if not failures else "rejected",
        "source": {"path": str(source), "sha256": source_hash, "topology": authority_topology},
        "guide_evidence": {
            "audit_report": str(guide_path),
            "audit_report_sha256": guide_hash,
            "profile": guide["profile"],
            "decision": str(decision_path),
            "decision_sha256": sha256_file(decision_path),
            "accepted_trial": accepted_trial["id"],
            "solver_attempt": args.attempt_id,
            "stroke_type": "output_edge",
            "stroke_representation": "open_path_with_repeated_terminal_ring_sample_omitted",
            "stroke_count": len(guide["rings"]),
            "stroke_point_count": int(len(strokes[2])),
        },
        "backend": "Remi Instant Meshes field solver",
        "backend_provenance": {
            "remi_version": "1.13.1",
            "native_module": str(remi_native),
            "native_module_sha256": sha256_file(remi_native),
            "instant_meshes_commit": "7b3160864a2e1025af498c84cfed91cbfb613698",
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
            "explicit_surface_strokes": len(guide["rings"]),
            "maximum_p99_m": args.maximum_p99_m,
            "maximum_max_m": args.maximum_max_m,
        },
        "timing_seconds": {"orientation": orientation_seconds, "position": position_seconds},
        "native_output_topology": native_topology,
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
        "requires_wireframe_review": True,
        "requires_deformation_review": True,
        "production_grade": False,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    session.stop()
    if failures:
        print("RAC_GUIDED_INSTANT_MESHES_REJECTED report={0}".format(report_path), flush=True)
        return 1
    print("RAC_GUIDED_INSTANT_MESHES_CANDIDATE_OK report={0}".format(report_path), flush=True)
    print("The rings may guide the field; only evidence may crown it.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
