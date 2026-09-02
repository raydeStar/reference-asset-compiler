"""Replace audited limb bands with projected bridge-loop topology."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
import sys

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_limb_band_surgery import (  # noqa: E402
    LIMBS,
    face_centroid,
    fill_small_selection_holes,
    ring_geometry,
)
from pair_feature_qem_triangles import (  # noqa: E402
    augment_pairing_to_contract,
    load_single_mesh,
)
from reduce_instant_meshes import evaluated_triangles  # noqa: E402
from reduce_quadriflow import sha256_file, symmetric_deviation, topology  # noqa: E402


def parse_args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("authority", type=Path)
    parser.add_argument("guide_report", type=Path)
    parser.add_argument("band_audit", type=Path)
    parser.add_argument("output_blend", type=Path)
    parser.add_argument("review_glb", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--arm-cuts", type=int, default=6)
    parser.add_argument("--leg-cuts", type=int, default=8)
    parser.add_argument("--radial-filter-window", type=int, default=3)
    parser.add_argument("--boundary-support-fraction", type=float, default=0.05)
    return parser.parse_args(values)


def selections_from_audit(
    mesh: bpy.types.Mesh, guide: dict, audit: dict
) -> dict[str, set[int]]:
    settings = audit["settings"]
    records = {record["id"]: record for record in audit["limbs"]}
    rings = {record["id"]: record for record in guide["rings"]}
    selections = {}
    claimed = set()
    for limb, endpoints in LIMBS.items():
        record = records[limb]
        start, start_radius = ring_geometry(rings[endpoints[0]])
        end, end_radius = ring_geometry(rings[endpoints[1]])
        end_fraction = float(record["end_fraction"])
        end = start + (end - start) * end_fraction
        end_radius = start_radius + (end_radius - start_radius) * end_fraction
        direction = end - start
        length = direction.length
        axis = direction.normalized()
        lower = float(settings["end_inset"]) / length
        upper = 1.0 - lower
        radius_scale = float(record["radius_scale"])
        selected = set()
        for polygon in mesh.polygons:
            centroid = face_centroid(mesh, polygon)
            progress = (centroid - start).dot(axis) / length
            if not lower <= progress <= upper:
                continue
            centerline = start + direction * progress
            radius = start_radius + (end_radius - start_radius) * progress
            if (centroid - centerline).length <= radius * radius_scale:
                selected.add(polygon.index)
        repair = fill_small_selection_holes(
            mesh, selected, int(settings["fill_small_boundary_max_edges"])
        )
        if len(selected) != int(record["selected_faces"]):
            raise RuntimeError("Reproduced selection count drifted for {0}".format(limb))
        if repair != record["small_component_repair"]:
            raise RuntimeError("Reproduced small-component repair drifted for {0}".format(limb))
        if claimed & selected:
            raise RuntimeError("Audited limb selections overlap")
        claimed |= selected
        selections[limb] = selected
    return selections


def authority_tree(obj: bpy.types.Object) -> BVHTree:
    vertices, triangles = evaluated_triangles(obj)
    return BVHTree.FromPolygons(vertices.tolist(), triangles.tolist(), all_triangles=True)


def ordered_boundary_cycles(
    edges: set[bmesh.types.BMEdge],
) -> list[list[bmesh.types.BMVert]]:
    adjacency: dict[bmesh.types.BMVert, set[bmesh.types.BMVert]] = {}
    for edge in edges:
        first, second = edge.verts
        adjacency.setdefault(first, set()).add(second)
        adjacency.setdefault(second, set()).add(first)
    if any(len(neighbors) != 2 for neighbors in adjacency.values()):
        raise RuntimeError("Audited surgery boundary is not degree two")
    remaining = set(adjacency)
    cycles = []
    while remaining:
        start = min(remaining, key=lambda vertex: vertex.index)
        cycle = [start]
        previous = None
        current = start
        while True:
            choices = [neighbor for neighbor in adjacency[current] if neighbor is not previous]
            following = choices[0]
            if following is start:
                break
            if following in cycle:
                raise RuntimeError("Boundary traversal encountered a premature cycle")
            cycle.append(following)
            previous, current = current, following
        remaining -= set(cycle)
        cycles.append(cycle)
    return cycles


def basis(axis: Vector) -> tuple[Vector, Vector]:
    first = Vector((0.0, 1.0, 0.0))
    if abs(axis.dot(first)) > 0.95:
        first = Vector((1.0, 0.0, 0.0))
    first = (first - axis * axis.dot(first)).normalized()
    return first, axis.cross(first).normalized()


def orient_cycle(
    cycle: list[bmesh.types.BMVert], axis: Vector
) -> list[bmesh.types.BMVert]:
    center = sum((vertex.co for vertex in cycle), Vector((0.0, 0.0, 0.0))) / len(cycle)
    first, second = basis(axis)
    points = [vertex.co - center for vertex in cycle]
    signed_area = sum(
        points[index].dot(first) * points[(index + 1) % len(points)].dot(second)
        - points[index].dot(second) * points[(index + 1) % len(points)].dot(first)
        for index in range(len(points))
    )
    if signed_area < 0.0:
        cycle = list(reversed(cycle))
    start_index = min(
        range(len(cycle)),
        key=lambda index: abs(
            math.atan2(
                (cycle[index].co - center).dot(second),
                (cycle[index].co - center).dot(first),
            )
        ),
    )
    return cycle[start_index:] + cycle[:start_index]


def resample_cycle(
    cycle: list[bmesh.types.BMVert], count: int
) -> list[Vector]:
    """Sample an audited boundary by arc length without inventing its silhouette."""
    points = [vertex.co.copy() for vertex in cycle]
    lengths = [
        (points[(index + 1) % len(points)] - point).length
        for index, point in enumerate(points)
    ]
    perimeter = sum(lengths)
    if perimeter <= 0.0:
        raise RuntimeError("Cannot resample a zero-length boundary cycle")
    samples = []
    edge_index = 0
    edge_start = 0.0
    for sample_index in range(count):
        target = perimeter * sample_index / count
        while edge_index + 1 < len(points) and target > edge_start + lengths[edge_index]:
            edge_start += lengths[edge_index]
            edge_index += 1
        edge_length = lengths[edge_index]
        fraction = 0.0 if edge_length == 0.0 else (target - edge_start) / edge_length
        samples.append(
            points[edge_index].lerp(points[(edge_index + 1) % len(points)], fraction)
        )
    return samples


def connect_cycles(
    bm: bmesh.types.BMesh,
    first: list[bmesh.types.BMVert],
    second: list[bmesh.types.BMVert],
) -> list[bmesh.types.BMFace]:
    faces = []
    count_first = len(first)
    count_second = len(second)
    if count_first >= count_second:
        second_index = 0
        for first_index in range(count_first):
            next_second = round((first_index + 1) * count_second / count_first)
            a0 = first[first_index]
            a1 = first[(first_index + 1) % count_first]
            if next_second > second_index:
                b0 = second[second_index % count_second]
                b1 = second[next_second % count_second]
                faces.append(bm.faces.new((a0, a1, b1, b0)))
                second_index = next_second
            else:
                faces.append(bm.faces.new((a0, a1, second[second_index % count_second])))
    else:
        first_index = 0
        for second_index in range(count_second):
            next_first = round((second_index + 1) * count_first / count_second)
            b0 = second[second_index]
            b1 = second[(second_index + 1) % count_second]
            if next_first > first_index:
                a0 = first[first_index % count_first]
                a1 = first[next_first % count_first]
                faces.append(bm.faces.new((a0, a1, b1, b0)))
                first_index = next_first
            else:
                faces.append(bm.faces.new((first[first_index % count_first], b1, b0)))
    return faces


def bridge_one_band(
    bm: bmesh.types.BMesh,
    selected: set[bmesh.types.BMFace],
    cuts: int,
    tree: BVHTree,
    limb_record: dict,
    radial_filter_window: int,
    boundary_support_fraction: float,
) -> dict[str, int]:
    boundary = {
        edge
        for face in selected
        for edge in face.edges
        if len(edge.link_faces) == 2 and sum(linked in selected for linked in edge.link_faces) == 1
    }
    if not boundary:
        raise RuntimeError("Audited limb band has no boundary edges")
    cycles = ordered_boundary_cycles(boundary)
    if len(cycles) != 2:
        raise RuntimeError("Audited limb band no longer has exactly two cycles")
    start = Vector(limb_record["start_center"])
    end = Vector(limb_record["end_center"])
    direction = end - start
    axis = direction.normalized()
    length_squared = direction.length_squared
    cycle_centers = [
        sum((vertex.co for vertex in cycle), Vector((0.0, 0.0, 0.0))) / len(cycle)
        for cycle in cycles
    ]
    if (cycle_centers[0] - start).length > (cycle_centers[1] - start).length:
        cycles.reverse()
        cycle_centers.reverse()
    top = orient_cycle(cycles[0], axis)
    bottom = orient_cycle(cycles[1], axis)
    top_progress = max(0.0, min(1.0, (cycle_centers[0] - start).dot(direction) / length_squared))
    bottom_progress = max(0.0, min(1.0, (cycle_centers[1] - start).dot(direction) / length_squared))
    if top_progress > bottom_progress:
        top, bottom = bottom, top
        top_progress, bottom_progress = bottom_progress, top_progress
    bmesh.ops.delete(bm, geom=list(selected), context="FACES_KEEP_BOUNDARY")
    ring_size = max(len(top), len(bottom))
    top_contour = resample_cycle(top, ring_size)
    bottom_contour = resample_cycle(bottom, ring_size)
    rings = []
    projection_failures = 0
    maximum_radial_adjustment = 0.0
    row_fractions = [row / (cuts + 1) for row in range(1, cuts + 1)]
    if cuts >= 2:
        row_fractions[0] = boundary_support_fraction
        row_fractions[-1] = 1.0 - boundary_support_fraction
    for row_fraction in row_fractions:
        projected_locations = []
        projection_adjustments = []
        for index in range(ring_size):
            contour_target = top_contour[index].lerp(bottom_contour[index], row_fraction)
            location, _normal, _face, distance = tree.find_nearest(contour_target)
            if location is None:
                projection_failures += 1
                continue
            projected_locations.append(location)
            projection_adjustments.append(distance)
        half_window = radial_filter_window // 2
        filtered_locations = []
        for index, location in enumerate(projected_locations):
            neighbors = [
                projected_locations[(index + offset) % ring_size]
                for offset in range(-half_window, half_window + 1)
            ]
            filtered_locations.append(
                Vector(
                    tuple(
                        statistics.median(point[axis_index] for point in neighbors)
                        for axis_index in range(3)
                    )
                ).lerp(location, 0.75)
            )
        maximum_radial_adjustment = max(
            maximum_radial_adjustment,
            max(projection_adjustments),
        )
        ring = [bm.verts.new(location) for location in filtered_locations]
        rings.append(ring)
    if projection_failures:
        raise RuntimeError("Authority projection missed {0} new vertices".format(projection_failures))
    created_faces = connect_cycles(bm, top, rings[0])
    for first_ring, second_ring in zip(rings, rings[1:]):
        created_faces.extend(connect_cycles(bm, first_ring, second_ring))
    created_faces.extend(connect_cycles(bm, rings[-1], bottom))
    return {
        "removed_faces": len(selected),
        "boundary_edges": len(boundary),
        "top_boundary_vertices": len(top),
        "bottom_boundary_vertices": len(bottom),
        "projected_ring_count": cuts,
        "vertices_per_projected_ring": ring_size,
        "new_vertices_projected": cuts * ring_size,
        "created_faces": len(created_faces),
        "maximum_radial_filter_adjustment_m": maximum_radial_adjustment,
    }


def main() -> int:
    args = parse_args()
    paths = [
        args.source.resolve(),
        args.authority.resolve(),
        args.guide_report.resolve(),
        args.band_audit.resolve(),
        args.output_blend.resolve(),
        args.review_glb.resolve(),
        args.report.resolve(),
    ]
    source, authority_path, guide_path, audit_path, output, review_glb, report_path = paths
    if any(path.exists() for path in (output, review_glb, report_path)):
        raise RuntimeError("Limb-band challenger refuses to overwrite evidence")
    if args.radial_filter_window < 1 or args.radial_filter_window % 2 == 0:
        raise RuntimeError("Radial filter window must be a positive odd integer")
    if not 0.0 < args.boundary_support_fraction < 0.5:
        raise RuntimeError("Boundary support fraction must be between zero and one half")
    guide = json.loads(guide_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("status") != "mechanical_pass":
        raise RuntimeError("Limb-band challenger requires a passing immutable audit")
    if audit["source"]["sha256"] != sha256_file(source):
        raise RuntimeError("Band audit is not bound to the candidate source")
    if audit["guide_report"]["sha256"] != sha256_file(guide_path):
        raise RuntimeError("Band audit is not bound to the guide report")
    if guide["source"]["sha256"] != sha256_file(authority_path):
        raise RuntimeError("Guide report is not bound to the AI authority")

    bpy.ops.wm.open_mainfile(filepath=str(source))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError("Limb-band challenger requires exactly one source mesh")
    candidate = meshes[0]
    candidate.name = "GEO_RAC_LimbBandChallenger"
    selections = selections_from_audit(candidate.data, guide, audit)
    authority = load_single_mesh(authority_path, "SRC_RAC_ApprovedAI_Cleanup")
    tree = authority_tree(authority)
    source_topology = topology(candidate)

    bm = bmesh.new()
    records = []
    audit_records = {record["id"]: record for record in audit["limbs"]}
    try:
        bm.from_mesh(candidate.data)
        bm.faces.ensure_lookup_table()
        selection_faces = {
            limb: {bm.faces[index] for index in selected}
            for limb, selected in selections.items()
        }
        for limb, selected in selection_faces.items():
            cuts = args.arm_cuts if limb.endswith("arm") else args.leg_cuts
            record = bridge_one_band(
                bm,
                selected,
                cuts,
                tree,
                audit_records[limb],
                args.radial_filter_window,
                args.boundary_support_fraction,
            )
            record["id"] = limb
            records.append(record)
        augmentations = augment_pairing_to_contract(bm, 0.80)
        loose = [vertex for vertex in bm.verts if not vertex.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context="VERTS")
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.normal_update()
        bm.to_mesh(candidate.data)
    finally:
        bm.free()
    candidate.data.validate(verbose=True)
    candidate.data.update(calc_edges=True)
    for polygon in candidate.data.polygons:
        polygon.use_smooth = True
    candidate_topology = topology(candidate)
    deviation = symmetric_deviation(authority, candidate)
    finite = all(
        math.isfinite(value) for vertex in candidate.data.vertices for value in vertex.co
    )
    failures = []
    if candidate_topology["vertices"] > 15_000:
        failures.append("vertex budget exceeded")
    if candidate_topology["triangles"] > 20_000:
        failures.append("triangle budget exceeded")
    if candidate_topology["quad_fraction"] < 0.80:
        failures.append("quad fraction is below the articulated contract")
    if candidate_topology["boundary_edges"] or candidate_topology["nonmanifold_edges"]:
        failures.append("candidate is not closed two-manifold")
    if deviation["p99_m"] > 0.005 or deviation["max_m"] > 0.020:
        failures.append("candidate exceeds surface-deviation contract")
    if not finite:
        failures.append("candidate contains non-finite coordinates")

    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    candidate.select_set(True)
    bpy.context.view_layer.objects.active = candidate
    bpy.ops.export_scene.gltf(
        filepath=str(review_glb), export_format="GLB", use_selection=True, export_materials="NONE"
    )
    bpy.data.objects.remove(authority, do_unlink=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    report = {
        "schema": "reference-asset-compiler.limb-band-retopology-candidate.v1",
        "status": "mechanical_pass" if not failures else "rejected",
        "purpose": "Controlled projected deformation bands stitched into a fidelity-preserving downstream AI/QEM surface.",
        "source": {"path": str(source), "sha256": sha256_file(source), "topology": source_topology},
        "authority": {"path": str(authority_path), "sha256": sha256_file(authority_path)},
        "guide_report": {"path": str(guide_path), "sha256": sha256_file(guide_path)},
        "band_audit": {"path": str(audit_path), "sha256": sha256_file(audit_path)},
        "settings": {
            "arm_cuts": args.arm_cuts,
            "leg_cuts": args.leg_cuts,
            "radial_filter_window": args.radial_filter_window,
            "boundary_support_fraction": args.boundary_support_fraction,
        },
        "limbs": records,
        "bounded_post_stitch_augmentations": augmentations,
        "output": {
            "path": str(output),
            "sha256": sha256_file(output),
            "review_glb": str(review_glb),
            "review_glb_sha256": sha256_file(review_glb),
            **candidate_topology,
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
        "RAC_LIMB_BAND_CHALLENGER_{0} {1}".format(
            "OK" if not failures else "REJECTED", report_path
        )
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
