"""Collapse only micro-edges that violate Blender's QuadriFlow preflight."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import bmesh
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_manifold import QUADRIFLOW_EDGE_TOLERANCE_M, audit  # noqa: E402
from reduce_quadriflow import sha256_file, symmetric_deviation  # noqa: E402


def parse_args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output_blend", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--maximum-p99-m", type=float, default=0.00005)
    parser.add_argument("--maximum-max-m", type=float, default=0.00020)
    return parser.parse_args(values)


def collapse_micro_edges(obj: bpy.types.Object) -> dict[str, object]:
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.edges.ensure_lookup_table()
    selected = [edge for edge in bm.edges if edge.calc_length() <= QUADRIFLOW_EDGE_TOLERANCE_M]
    selected_rows = [
        {"index": edge.index, "length_m": float(edge.calc_length())}
        for edge in selected
    ]
    if not selected:
        bm.free()
        raise RuntimeError("No QuadriFlow micro-edge precondition defect was found")
    bmesh.ops.collapse(bm, edges=selected, uvs=False)
    bmesh.ops.dissolve_degenerate(bm, dist=1.0e-12, edges=list(bm.edges))
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    obj.data.update()
    bm.free()
    return {
        "operation": "collapse_edges_at_or_below_quadriflow_tolerance",
        "tolerance_m": QUADRIFLOW_EDGE_TOLERANCE_M,
        "selected_edges": selected_rows,
    }


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    output_blend = args.output_blend.resolve()
    report_path = args.report.resolve()
    if source.suffix.lower() != ".blend" or not source.is_file():
        raise RuntimeError("QuadriFlow precondition repair requires a native .blend source")
    if output_blend.exists() or report_path.exists():
        raise RuntimeError("QuadriFlow precondition repair refuses to overwrite an attempt")

    source_hash = sha256_file(source)
    bpy.ops.wm.open_mainfile(filepath=str(source))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError("QuadriFlow precondition repair requires exactly one mesh object")
    authority = meshes[0]
    authority.name = "SRC_RAC_ApprovedCleanup"
    before = audit(authority)
    if before["quadriflow_preconditions_ok"]:
        raise RuntimeError("Input already passes QuadriFlow preconditions; repair refused")
    if before["edges_at_or_below_quadriflow_tolerance"] <= 0:
        raise RuntimeError("Input failure is not the bounded micro-edge defect")
    unrelated_failures = [
        key
        for key in (
            "nonmanifold_edges",
            "nonmanifold_vertices",
            "inconsistent_winding_edges",
            "wire_edges",
            "invalid_vertices",
            "degenerate_faces",
            "loose_vertices",
            "duplicate_coordinate_groups",
        )
        if before[key] != 0
    ]
    if unrelated_failures:
        raise RuntimeError("Repair refuses unrelated topology defects: {0}".format(
            unrelated_failures))

    bpy.context.view_layer.objects.active = authority
    bpy.ops.object.select_all(action="DESELECT")
    authority.select_set(True)
    bpy.ops.object.duplicate()
    candidate = bpy.context.view_layer.objects.active
    candidate.name = "GEO_RAC_QuadriFlowPreconditionRepair"
    operation = collapse_micro_edges(candidate)
    after = audit(candidate)
    deviation = symmetric_deviation(authority, candidate)
    failures = []
    if not after["quadriflow_preconditions_ok"]:
        failures.append("repaired derivative still fails QuadriFlow preconditions")
    if after["connected_components"] != before["connected_components"]:
        failures.append("connected-component count changed")
    if after["faces"] < int(before["faces"] * 0.998) or after["faces"] > before["faces"]:
        failures.append("face count changed beyond the bounded repair contract")
    if deviation["p99_m"] > args.maximum_p99_m:
        failures.append("p99 surface deviation exceeds {0} m".format(args.maximum_p99_m))
    if deviation["max_m"] > args.maximum_max_m:
        failures.append("maximum surface deviation exceeds {0} m".format(args.maximum_max_m))

    output_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.data.objects.remove(authority, do_unlink=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    payload = {
        "schema": "reference-asset-compiler.quadriflow-precondition-repair.v1",
        "status": "passed" if not failures else "rejected",
        "source": str(source),
        "source_sha256": source_hash,
        "output": str(output_blend),
        "output_sha256": sha256_file(output_blend),
        "operation": operation,
        "before": before,
        "after": after,
        "symmetric_surface_deviation": deviation,
        "limits": {
            "maximum_p99_m": args.maximum_p99_m,
            "maximum_max_m": args.maximum_max_m,
            "maximum_face_loss_fraction": 0.002,
        },
        "failures": failures,
        "modeling_authority_changed": False,
        "production_grade": False,
    }
    report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if failures:
        print("RAC_QUADRIFLOW_PRECONDITION_REPAIR_REJECTED report={0}".format(
            report_path), flush=True)
        return 1
    print("RAC_QUADRIFLOW_PRECONDITION_REPAIR_OK report={0}".format(
        report_path), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
