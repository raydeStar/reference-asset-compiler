"""Pair compatible Feature-QEM triangles into quads without moving vertices."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import bmesh
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reduce_quadriflow import sha256_file, symmetric_deviation, topology  # noqa: E402


def parse_args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("qem_source", type=Path)
    parser.add_argument("ai_authority", type=Path)
    parser.add_argument("output_blend", type=Path)
    parser.add_argument("review_glb", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--face-angle-degrees", type=float, default=45.0)
    parser.add_argument("--shape-angle-degrees", type=float, default=45.0)
    parser.add_argument("--minimum-quad-fraction", type=float, default=0.80)
    return parser.parse_args(values)


def load_single_mesh(path: Path, name: str) -> bpy.types.Object:
    before = set(bpy.data.objects)
    with bpy.data.libraries.load(str(path), link=False) as (source, target):
        target.objects = source.objects
    loaded = [obj for obj in bpy.data.objects if obj not in before and obj.type == "MESH"]
    if len(loaded) != 1:
        raise RuntimeError("{0} must contain exactly one mesh".format(path))
    obj = loaded[0]
    if obj.name not in bpy.context.scene.collection.objects:
        bpy.context.scene.collection.objects.link(obj)
    obj.name = name
    return obj


def coordinate_fingerprint(obj: bpy.types.Object) -> list[tuple[float, float, float]]:
    return [tuple(round(value, 9) for value in vertex.co) for vertex in obj.data.vertices]


def quad_fraction(bm: bmesh.types.BMesh) -> float:
    quads = sum(len(face.verts) == 4 for face in bm.faces)
    return quads / max(1, len(bm.faces))


def remove_exact_duplicate_faces(bm: bmesh.types.BMesh) -> int:
    """Remove only stacked faces with the exact same vertex set.

    The augmenting pass can converge on the same local face through two paths.
    Blender's later mesh validation removes those faces opaquely and may also
    prune vertices, which violates the no-motion contract.  Resolve the exact
    duplicates while the BMesh is still authoritative, then let the ordinary
    manifold and coordinate gates judge the result.
    """
    bm.verts.ensure_lookup_table()
    bm.verts.index_update()
    bm.faces.ensure_lookup_table()
    seen: dict[tuple[int, ...], bmesh.types.BMFace] = {}
    duplicates: list[bmesh.types.BMFace] = []
    for face in list(bm.faces):
        key = tuple(sorted(vertex.index for vertex in face.verts))
        if key in seen:
            duplicates.append(face)
        else:
            seen[key] = face
    if duplicates:
        bmesh.ops.delete(bm, geom=duplicates, context="FACES_ONLY")
    return len(duplicates)


def closed_without_duplicate_faces(bm: bmesh.types.BMesh) -> bool:
    """Return whether a trial pairing preserves a closed two-manifold."""
    bm.verts.ensure_lookup_table()
    bm.verts.index_update()
    seen: set[tuple[int, ...]] = set()
    for face in bm.faces:
        key = tuple(sorted(vertex.index for vertex in face.verts))
        if key in seen:
            return False
        seen.add(key)
    return all(len(edge.link_faces) == 2 for edge in bm.edges)


def apply_augmentation(
    bm: bmesh.types.BMesh,
    diagonal_indices: tuple[int, int],
    edge_a_indices: tuple[int, int],
    edge_b_indices: tuple[int, int],
) -> bool:
    """Apply one indexed augmentation to a BMesh, if its elements still exist."""
    bm.verts.ensure_lookup_table()
    bm.verts.index_update()
    diagonal = [bm.verts[index] for index in diagonal_indices]
    edge_a = bm.edges.get(tuple(bm.verts[index] for index in edge_a_indices))
    edge_b = bm.edges.get(tuple(bm.verts[index] for index in edge_b_indices))
    if edge_a is None or edge_b is None or not edge_a.is_valid or not edge_b.is_valid:
        return False
    bmesh.ops.connect_verts(bm, verts=diagonal, check_degenerate=True)
    if not edge_a.is_valid or not edge_b.is_valid:
        return False
    bmesh.ops.dissolve_edges(
        bm, edges=[edge_a, edge_b], use_verts=False, use_face_split=False
    )
    return True


def pair_triangles_greedily(
    bm: bmesh.types.BMesh, maximum_face_angle_degrees: float
) -> int:
    """Pair adjacent triangles without Blender's invalid bulk join side effects."""
    bm.verts.ensure_lookup_table()
    bm.verts.index_update()
    bm.normal_update()
    maximum_angle = math.radians(maximum_face_angle_degrees)
    choices: list[tuple[float, tuple[int, int]]] = []
    for edge in bm.edges:
        if edge.seam or not edge.smooth or len(edge.link_faces) != 2:
            continue
        first, second = edge.link_faces
        if len(first.verts) != 3 or len(second.verts) != 3:
            continue
        if first.material_index != second.material_index:
            continue
        angle = edge.calc_face_angle(0.0)
        if angle <= maximum_angle:
            choices.append((angle, tuple(sorted(vertex.index for vertex in edge.verts))))
    choices.sort(key=lambda item: item[0])

    face_keys = {
        tuple(sorted(vertex.index for vertex in face.verts)) for face in bm.faces
    }
    joined = 0
    for _angle, edge_indices in choices:
        bm.verts.ensure_lookup_table()
        bm.verts.index_update()
        edge = bm.edges.get(tuple(bm.verts[index] for index in edge_indices))
        if edge is None or not edge.is_valid or len(edge.link_faces) != 2:
            continue
        first, second = edge.link_faces
        if len(first.verts) != 3 or len(second.verts) != 3:
            continue
        combined = tuple(sorted({
            vertex.index for face in (first, second) for vertex in face.verts
        }))
        if len(combined) != 4 or combined in face_keys:
            continue
        first_key = tuple(sorted(vertex.index for vertex in first.verts))
        second_key = tuple(sorted(vertex.index for vertex in second.verts))
        bmesh.ops.dissolve_edges(
            bm, edges=[edge], use_verts=False, use_face_split=False
        )
        face_keys.discard(first_key)
        face_keys.discard(second_key)
        face_keys.add(combined)
        joined += 1
    return joined


def solidify_isolated_coincident_sheets(
    obj: bpy.types.Object, thickness_m: float = 0.00025
) -> dict[str, int | float]:
    """Give export-safe thickness to isolated two-sided detail triangles.

    Hunyuan/QEM can represent whisker and costume details as two coincident
    opposite faces. They look correct in Blender but exporters collapse one
    face and leave an open triangle. Preserve the original triangle exactly
    and add one offset apex plus three side faces, producing a tiny closed
    tetrahedral shell without erasing the authored detail.
    """
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.verts.index_update()
        groups: dict[tuple[int, ...], list[bmesh.types.BMFace]] = {}
        for face in bm.faces:
            key = tuple(sorted(vertex.index for vertex in face.verts))
            groups.setdefault(key, []).append(face)
        eligible: list[tuple[list[bmesh.types.BMFace], list[bmesh.types.BMVert]]] = []
        component_count = 0
        for faces in groups.values():
            if len(faces) != 2:
                continue
            face_set = set(faces)
            if all(set(edge.link_faces) == face_set for face in faces for edge in face.edges):
                eligible.append((faces, list(faces[0].verts)))
                component_count += 1
        for faces, vertices in eligible:
            normal = faces[0].normal.normalized()
            centre = sum((vertex.co for vertex in vertices), vertices[0].co.copy() * 0.0) / 3.0
            bmesh.ops.delete(bm, geom=faces, context="FACES_ONLY")
            apex = bm.verts.new(centre + normal * thickness_m)
            bm.faces.new(vertices)
            for index in range(3):
                bm.faces.new((
                    vertices[index],
                    vertices[(index + 1) % 3],
                    apex,
                ))
        bm.normal_update()
        bm.to_mesh(obj.data)
        obj.data.update(calc_edges=True)
        return {
            "components_solidified": component_count,
            "input_faces_removed": component_count * 2,
            "faces_added": component_count * 4,
            "vertices_added": component_count,
            "thickness_m": thickness_m,
        }
    finally:
        bm.free()


def augment_pairing_to_contract(
    bm: bmesh.types.BMesh, minimum_quad_fraction: float
) -> int:
    """Use length-three augmenting paths without moving any mesh vertices."""
    augmentations = 0
    rejected_choices: set[
        tuple[tuple[int, int], tuple[int, int], tuple[int, int]]
    ] = set()
    while quad_fraction(bm) < minimum_quad_fraction:
        bm.verts.ensure_lookup_table()
        bm.verts.index_update()
        choices = []
        for quad in bm.faces:
            if not quad.is_valid or len(quad.verts) != 4:
                continue
            ordered_vertices = list(quad.verts)
            ordered_edges = [
                bm.edges.get((ordered_vertices[index], ordered_vertices[(index + 1) % 4]))
                for index in range(4)
            ]
            triangle_edges = []
            for index, edge in enumerate(ordered_edges):
                if edge is None or edge.seam or not edge.smooth or len(edge.link_faces) != 2:
                    continue
                neighbor = next(face for face in edge.link_faces if face is not quad)
                if len(neighbor.verts) == 3 and neighbor.material_index == quad.material_index:
                    triangle_edges.append((index, edge, neighbor))
            for first in range(len(triangle_edges)):
                for second in range(first + 1, len(triangle_edges)):
                    index_a, edge_a, neighbor_a = triangle_edges[first]
                    index_b, edge_b, neighbor_b = triangle_edges[second]
                    if neighbor_a is neighbor_b:
                        continue
                    diagonal = None
                    if (index_a < 2) != (index_b < 2):
                        diagonal = (ordered_vertices[0], ordered_vertices[2])
                    elif (index_a in {1, 2}) != (index_b in {1, 2}):
                        diagonal = (ordered_vertices[1], ordered_vertices[3])
                    if diagonal is None or bm.edges.get(diagonal) is not None:
                        continue
                    diagonal_indices = tuple(sorted(vertex.index for vertex in diagonal))
                    edge_a_indices = tuple(sorted(vertex.index for vertex in edge_a.verts))
                    edge_b_indices = tuple(sorted(vertex.index for vertex in edge_b.verts))
                    choice_key = (
                        diagonal_indices, min(edge_a_indices, edge_b_indices),
                        max(edge_a_indices, edge_b_indices))
                    if choice_key in rejected_choices:
                        continue
                    score = edge_a.calc_face_angle(0.0) + edge_b.calc_face_angle(0.0)
                    choices.append((
                        score, choice_key, diagonal_indices,
                        edge_a_indices, edge_b_indices))
        if not choices:
            break
        (_score, choice_key, diagonal_indices,
         edge_a_indices, edge_b_indices) = min(choices, key=lambda item: item[0])

        # Test the local rewrite on a disposable copy. The earlier greedy pass
        # admitted five choices that created duplicate faces and 15 open edges.
        # Transactional validation lets us skip only those choices while
        # preserving every source coordinate and the rest of the matching.
        trial = bm.copy()
        try:
            trial_ok = apply_augmentation(
                trial, diagonal_indices, edge_a_indices, edge_b_indices
            ) and closed_without_duplicate_faces(trial)
        finally:
            trial.free()
        if not trial_ok:
            rejected_choices.add(choice_key)
            continue
        if not apply_augmentation(
            bm, diagonal_indices, edge_a_indices, edge_b_indices
        ):
            break
        augmentations += 1
    return augmentations


def main() -> int:
    args = parse_args()
    qem_source = args.qem_source.resolve()
    authority_path = args.ai_authority.resolve()
    output_blend = args.output_blend.resolve()
    review_glb = args.review_glb.resolve()
    report_path = args.report.resolve()
    if any(path.exists() for path in (output_blend, review_glb, report_path)):
        raise RuntimeError("Triangle-pairing attempt refuses to overwrite evidence")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    qem = load_single_mesh(qem_source, "SRC_RAC_FeatureQEM")
    authority = load_single_mesh(authority_path, "SRC_RAC_ApprovedAI_Cleanup")
    qem_input_topology = topology(qem)
    qem_sanitation = solidify_isolated_coincident_sheets(qem)
    qem_topology = topology(qem)
    before_coordinates = coordinate_fingerprint(qem)

    candidate = qem.copy()
    candidate.data = qem.data.copy()
    candidate.name = "GEO_RAC_PairedFeatureQEM"
    bpy.context.scene.collection.objects.link(candidate)
    bm = bmesh.new()
    try:
        bm.from_mesh(candidate.data)
        joined_faces = pair_triangles_greedily(bm, args.face_angle_degrees)
        augmentations = augment_pairing_to_contract(bm, args.minimum_quad_fraction)
        duplicate_faces_removed = remove_exact_duplicate_faces(bm)
        bm.normal_update()
        bm.to_mesh(candidate.data)
    finally:
        bm.free()
    validation_changed_mesh = candidate.data.validate(verbose=True)
    candidate.data.update(calc_edges=True)
    candidate_topology = topology(candidate)
    coordinates_unchanged = before_coordinates == coordinate_fingerprint(candidate)
    deviation = symmetric_deviation(authority, candidate)
    failures: list[str] = []
    if not coordinates_unchanged:
        failures.append("triangle pairing changed vertex coordinates")
    if validation_changed_mesh:
        failures.append("Blender mesh validation changed paired topology")
    if candidate_topology["quad_fraction"] < args.minimum_quad_fraction:
        failures.append("quad fraction is below {0}".format(args.minimum_quad_fraction))
    if candidate_topology["triangles"] > 20_000 or candidate_topology["vertices"] > 15_000:
        failures.append("runtime topology budget exceeded")
    if candidate_topology["boundary_edges"] or candidate_topology["nonmanifold_edges"]:
        failures.append("candidate is not closed two-manifold")
    if deviation["p99_m"] > 0.005 or deviation["max_m"] > 0.020:
        failures.append("candidate exceeds surface-deviation contract")

    output_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.data.objects.remove(qem, do_unlink=True)
    bpy.data.objects.remove(authority, do_unlink=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    bpy.ops.wm.open_mainfile(filepath=str(output_blend))
    roundtrip_meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(roundtrip_meshes) != 1:
        raise RuntimeError("Paired QEM native round-trip changed mesh object count")
    candidate = roundtrip_meshes[0]
    roundtrip_topology = topology(candidate)
    roundtrip_coordinates_unchanged = before_coordinates == coordinate_fingerprint(candidate)
    if roundtrip_topology != candidate_topology:
        failures.append(
            "native round-trip changed topology: before={0} after={1}".format(
                candidate_topology, roundtrip_topology))
    if not roundtrip_coordinates_unchanged:
        failures.append("native round-trip changed vertex coordinates")

    bpy.ops.object.select_all(action="DESELECT")
    candidate.select_set(True)
    bpy.context.view_layer.objects.active = candidate
    bpy.ops.export_scene.gltf(
        filepath=str(review_glb), export_format="GLB", use_selection=True, export_materials="NONE"
    )
    report = {
        "schema": "reference-asset-compiler.paired-feature-qem-candidate.v1",
        "status": "mechanical_pass" if not failures else "rejected",
        "purpose": "Downstream topology pairing of an AI-derived QEM surface; no image reconstruction.",
        "qem_source": {
            "path": str(qem_source),
            "sha256": sha256_file(qem_source),
            "input_topology": qem_input_topology,
            "sanitation": qem_sanitation,
            "topology": qem_topology,
        },
        "ai_authority": {"path": str(authority_path), "sha256": sha256_file(authority_path)},
        "settings": {
            "face_angle_degrees": args.face_angle_degrees,
            "shape_angle_degrees": args.shape_angle_degrees,
            "preserve_seams_sharp_uvs_vertex_colors_materials": True,
        },
        "operation": {
            "joined_faces_reported": joined_faces,
            "augmenting_paths_applied": augmentations,
            "exact_duplicate_faces_removed": duplicate_faces_removed,
            "vertex_coordinates_unchanged": roundtrip_coordinates_unchanged,
        },
        "output": {
            "path": str(output_blend),
            "sha256": sha256_file(output_blend),
            "review_glb": str(review_glb),
            "review_glb_sha256": sha256_file(review_glb),
            **roundtrip_topology,
        },
        "symmetric_surface_deviation": deviation,
        "failures": failures,
        "requires_fixed_view_review": True,
        "requires_deformation_flow_review": True,
        "production_grade": False,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("RAC_PAIRED_FEATURE_QEM_{0} report={1}".format(
        "CANDIDATE_OK" if not failures else "REJECTED", report_path
    ))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
