"""Pair QEM triangles while preserving explicit AI-surface joint cycles."""

from __future__ import annotations

import argparse
import heapq
import json
import math
from pathlib import Path
import sys

import bmesh
import bpy
from mathutils import Vector
from mathutils.kdtree import KDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pair_feature_qem_triangles import (  # noqa: E402
    augment_pairing_to_contract,
    coordinate_fingerprint,
    load_single_mesh,
)
from reduce_quadriflow import sha256_file, symmetric_deviation, topology  # noqa: E402


def parse_args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("qem_source", type=Path)
    parser.add_argument("ai_authority", type=Path)
    parser.add_argument("guide_report", type=Path)
    parser.add_argument("output_blend", type=Path)
    parser.add_argument("review_glb", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--minimum-quad-fraction", type=float, default=0.80)
    parser.add_argument("--plane-band-m", type=float, default=0.045)
    return parser.parse_args(values)


def nearest_vertices(bm: bmesh.types.BMesh, positions: list[list[float]]) -> list[int]:
    tree = KDTree(len(bm.verts))
    for vertex in bm.verts:
        tree.insert(vertex.co, vertex.index)
    tree.balance()
    result = []
    for position in positions:
        _co, index, _distance = tree.find(Vector(position))
        if not result or result[-1] != index:
            result.append(index)
    if len(result) > 1 and result[0] == result[-1]:
        result.pop()
    return result


def shortest_band_path(
    bm: bmesh.types.BMesh,
    start: int,
    end: int,
    center: Vector,
    axis: Vector,
    plane_band: float,
    forbidden: set[int],
) -> list[int]:
    if start == end:
        return [start]
    distances = {start: 0.0}
    previous: dict[int, int] = {}
    queue = [(0.0, start)]
    while queue:
        distance, index = heapq.heappop(queue)
        if distance != distances.get(index):
            continue
        if index == end:
            break
        vertex = bm.verts[index]
        for edge in vertex.link_edges:
            neighbor = edge.other_vert(vertex)
            if neighbor.index in forbidden:
                continue
            plane_distance = abs((neighbor.co - center).dot(axis))
            if plane_distance > plane_band and neighbor.index != end:
                continue
            penalty = 1.0 + 12.0 * (plane_distance / plane_band) ** 2
            candidate = distance + edge.calc_length() * penalty
            if candidate < distances.get(neighbor.index, math.inf):
                distances[neighbor.index] = candidate
                previous[neighbor.index] = index
                heapq.heappush(queue, (candidate, neighbor.index))
    if end not in distances:
        raise RuntimeError("No local QEM edge path connects joint-ring anchors")
    path = [end]
    while path[-1] != start:
        path.append(previous[path[-1]])
    path.reverse()
    return path


def protect_joint_cycles(
    bm: bmesh.types.BMesh, guide: dict, plane_band: float
) -> tuple[set[tuple[int, int]], list[dict[str, object]]]:
    protected: set[tuple[int, int]] = set()
    records = []
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    for ring in guide.get("rings", []):
        hits = list(ring["hits"])
        if hits[0]["face"] == hits[-1]["face"]:
            hits.pop()
        anchors = nearest_vertices(bm, [hit["position"] for hit in hits])
        if len(anchors) < 6:
            raise RuntimeError("Joint ring collapsed to fewer than six QEM anchors")
        center = sum(
            (Vector(hit["position"]) for hit in hits), Vector((0.0, 0.0, 0.0))
        ) / len(hits)
        axis = Vector(ring["axis"]).normalized()
        ordered = []
        ring_edges: set[tuple[int, int]] = set()
        used_vertices: set[int] = set()
        anchor_set = set(anchors)
        for index, start in enumerate(anchors):
            end = anchors[(index + 1) % len(anchors)]
            forbidden = (used_vertices | anchor_set) - {start, end}
            path = shortest_band_path(
                bm, start, end, center, axis, plane_band, forbidden
            )
            if ordered:
                ordered.extend(path[1:])
            else:
                ordered.extend(path)
            for first, second in zip(path, path[1:]):
                key = tuple(sorted((first, second)))
                ring_edges.add(key)
                protected.add(key)
            used_vertices.update(path[:-1])
        degree: dict[int, int] = {}
        for first, second in ring_edges:
            degree[first] = degree.get(first, 0) + 1
            degree[second] = degree.get(second, 0) + 1
        branch_vertices = sum(value != 2 for value in degree.values())
        if branch_vertices:
            raise RuntimeError(
                "Protected ring {0} is not one closed degree-two cycle".format(ring["id"])
            )
        records.append(
            {
                "id": ring["id"],
                "anchors": len(anchors),
                "cycle_vertices": len(degree),
                "cycle_edges": len(ring_edges),
                "branch_vertices": branch_vertices,
            }
        )
    for first, second in protected:
        edge = bm.edges.get((bm.verts[first], bm.verts[second]))
        if edge is None:
            raise RuntimeError("Protected joint edge vanished before pairing")
        edge.seam = True
    return protected, records


def main() -> int:
    args = parse_args()
    qem_path = args.qem_source.resolve()
    authority_path = args.ai_authority.resolve()
    guide_path = args.guide_report.resolve()
    output_blend = args.output_blend.resolve()
    review_glb = args.review_glb.resolve()
    report_path = args.report.resolve()
    if any(path.exists() for path in (output_blend, review_glb, report_path)):
        raise RuntimeError("Joint-aware pairing refuses to overwrite evidence")
    guide = json.loads(guide_path.read_text(encoding="utf-8"))
    if guide.get("source", {}).get("sha256") != sha256_file(authority_path):
        raise RuntimeError("Joint guides are not bound to the AI authority")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    qem = load_single_mesh(qem_path, "SRC_RAC_FeatureQEM")
    authority = load_single_mesh(authority_path, "SRC_RAC_ApprovedAI_Cleanup")
    before_coordinates = coordinate_fingerprint(qem)
    candidate = qem.copy()
    candidate.data = qem.data.copy()
    candidate.name = "GEO_RAC_JointAwarePairedQEM"
    bpy.context.scene.collection.objects.link(candidate)

    bm = bmesh.new()
    try:
        bm.from_mesh(candidate.data)
        bm.verts.ensure_lookup_table()
        protected, cycle_records = protect_joint_cycles(bm, guide, args.plane_band_m)
        triangles = [face for face in bm.faces if len(face.verts) == 3]
        result = bmesh.ops.join_triangles(
            bm,
            faces=triangles,
            angle_face_threshold=math.pi,
            angle_shape_threshold=math.pi,
            cmp_seam=True,
            cmp_sharp=True,
            cmp_uvs=True,
            cmp_vcols=True,
            cmp_materials=True,
            deselect_joined=False,
        )
        joined_faces = len(result.get("faces", []))
        augmentations = augment_pairing_to_contract(bm, args.minimum_quad_fraction)
        remaining_protected = sum(
            bm.edges.get((bm.verts[first], bm.verts[second])) is not None
            for first, second in protected
        )
        bm.normal_update()
        bm.to_mesh(candidate.data)
    finally:
        bm.free()

    candidate.data.validate(verbose=True)
    candidate.data.update(calc_edges=True)
    output_topology = topology(candidate)
    coordinates_unchanged = before_coordinates == coordinate_fingerprint(candidate)
    deviation = symmetric_deviation(authority, candidate)
    failures = []
    if not coordinates_unchanged:
        failures.append("joint-aware pairing changed vertex coordinates")
    if remaining_protected != len(protected):
        failures.append("one or more protected joint-cycle edges were dissolved")
    if output_topology["quad_fraction"] < args.minimum_quad_fraction:
        failures.append("quad fraction is below the articulated contract")
    if output_topology["triangles"] > 20_000 or output_topology["vertices"] > 15_000:
        failures.append("runtime topology budget exceeded")
    if output_topology["boundary_edges"] or output_topology["nonmanifold_edges"]:
        failures.append("candidate is not closed two-manifold")
    if deviation["p99_m"] > 0.005 or deviation["max_m"] > 0.020:
        failures.append("candidate exceeds surface-deviation contract")

    output_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    candidate.select_set(True)
    bpy.context.view_layer.objects.active = candidate
    bpy.ops.export_scene.gltf(
        filepath=str(review_glb), export_format="GLB", use_selection=True, export_materials="NONE"
    )
    bpy.data.objects.remove(qem, do_unlink=True)
    bpy.data.objects.remove(authority, do_unlink=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    report = {
        "schema": "reference-asset-compiler.joint-aware-paired-qem-candidate.v1",
        "status": "mechanical_pass" if not failures else "rejected",
        "purpose": "Preserve closed joint cycles on an AI-derived QEM surface while pairing triangles without moving vertices.",
        "qem_source": {"path": str(qem_path), "sha256": sha256_file(qem_path)},
        "ai_authority": {"path": str(authority_path), "sha256": sha256_file(authority_path)},
        "guide_report": {"path": str(guide_path), "sha256": sha256_file(guide_path)},
        "settings": {
            "plane_band_m": args.plane_band_m,
            "minimum_quad_fraction": args.minimum_quad_fraction,
            "preserve_guided_cycles_as_seams_during_pairing": True,
        },
        "operation": {
            "protected_cycle_count": len(cycle_records),
            "protected_edges": len(protected),
            "protected_edges_remaining": remaining_protected,
            "cycles": cycle_records,
            "joined_faces_reported": joined_faces,
            "augmenting_paths_applied": augmentations,
            "vertex_coordinates_unchanged": coordinates_unchanged,
        },
        "output": {
            "path": str(output_blend),
            "sha256": sha256_file(output_blend),
            "review_glb": str(review_glb),
            "review_glb_sha256": sha256_file(review_glb),
            **output_topology,
        },
        "symmetric_surface_deviation": deviation,
        "failures": failures,
        "requires_fixed_view_review": True,
        "requires_wireframe_review": True,
        "requires_deformation_flow_review": True,
        "production_grade": False,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        "RAC_JOINT_AWARE_PAIRED_QEM_{0} report={1}".format(
            "CANDIDATE_OK" if not failures else "REJECTED", report_path
        )
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
