"""Audit removable limb bands on a fidelity-safe AI-derived retopology."""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reduce_quadriflow import sha256_file, topology  # noqa: E402


LIMBS = {
    "right_arm": ("right_upper_arm_support", "right_wrist"),
    "left_arm": ("left_upper_arm_support", "left_wrist"),
    "right_leg": ("right_upper_thigh_support", "right_ankle"),
    "left_leg": ("left_upper_thigh_support", "left_ankle"),
}


def parse_args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("guide_report", type=Path)
    parser.add_argument("output_blend", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--radius-scale", type=float, default=1.20)
    parser.add_argument("--arm-radius-scale", type=float)
    parser.add_argument("--leg-radius-scale", type=float)
    parser.add_argument("--arm-end-fraction", type=float, default=1.0)
    parser.add_argument("--leg-end-fraction", type=float, default=1.0)
    parser.add_argument("--fill-small-boundary-max-edges", type=int, default=0)
    parser.add_argument("--end-inset", type=float, default=0.025)
    return parser.parse_args(values)


def material(name: str, color: tuple[float, float, float, float]):
    value = bpy.data.materials.new(name)
    value.diffuse_color = color
    value.use_nodes = True
    bsdf = value.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = 0.55
    return value


def ring_geometry(record: dict) -> tuple[Vector, float]:
    positions = [Vector(hit["position"]) for hit in record["hits"][:-1]]
    center = sum(positions, Vector((0.0, 0.0, 0.0))) / len(positions)
    axis = Vector(record["axis"]).normalized()
    radius = sum(((position - center) - axis * (position - center).dot(axis)).length for position in positions) / len(positions)
    return center, radius


def face_centroid(mesh: bpy.types.Mesh, polygon: bpy.types.MeshPolygon) -> Vector:
    return sum((mesh.vertices[index].co for index in polygon.vertices), Vector((0.0, 0.0, 0.0))) / len(polygon.vertices)


def boundary_components(
    mesh: bpy.types.Mesh, selected: set[int]
) -> list[dict[str, int | bool]]:
    edge_faces: dict[tuple[int, int], list[int]] = defaultdict(list)
    for polygon in mesh.polygons:
        vertices = list(polygon.vertices)
        for index, first in enumerate(vertices):
            second = vertices[(index + 1) % len(vertices)]
            edge_faces[tuple(sorted((first, second)))].append(polygon.index)
    boundaries = {
        edge
        for edge, faces in edge_faces.items()
        if len(faces) == 2 and sum(face in selected for face in faces) == 1
    }
    adjacency: dict[int, set[int]] = defaultdict(set)
    for first, second in boundaries:
        adjacency[first].add(second)
        adjacency[second].add(first)
    remaining = set(adjacency)
    records = []
    while remaining:
        seed = next(iter(remaining))
        queue = deque([seed])
        component = set()
        while queue:
            vertex = queue.popleft()
            if vertex in component:
                continue
            component.add(vertex)
            queue.extend(adjacency[vertex] - component)
        remaining -= component
        edges = sum(len(adjacency[vertex] & component) for vertex in component) // 2
        records.append(
            {
                "vertices": len(component),
                "edges": edges,
                "closed_degree_two": all(len(adjacency[vertex]) == 2 for vertex in component),
            }
        )
    return sorted(records, key=lambda record: int(record["vertices"]), reverse=True)


def fill_small_selection_holes(
    mesh: bpy.types.Mesh, selected: set[int], maximum_edges: int
) -> dict[str, int]:
    if maximum_edges <= 0:
        return {"added": 0, "removed": 0}
    edge_faces: dict[tuple[int, int], list[int]] = defaultdict(list)
    for polygon in mesh.polygons:
        vertices = list(polygon.vertices)
        for index, first in enumerate(vertices):
            second = vertices[(index + 1) % len(vertices)]
            edge_faces[tuple(sorted((first, second)))].append(polygon.index)
    boundary_edges = {
        edge
        for edge, faces in edge_faces.items()
        if len(faces) == 2 and sum(face in selected for face in faces) == 1
    }
    adjacency: dict[int, set[int]] = defaultdict(set)
    for first, second in boundary_edges:
        adjacency[first].add(second)
        adjacency[second].add(first)
    remaining = set(adjacency)
    added: set[int] = set()
    removed: set[int] = set()
    while remaining:
        seed = next(iter(remaining))
        queue = deque([seed])
        component = set()
        while queue:
            vertex = queue.popleft()
            if vertex in component:
                continue
            component.add(vertex)
            queue.extend(adjacency[vertex] - component)
        remaining -= component
        component_edges = {
            edge for edge in boundary_edges if edge[0] in component and edge[1] in component
        }
        if len(component_edges) > maximum_edges:
            continue
        selected_side = set()
        unselected_side = set()
        for edge in component_edges:
            selected_side.update(face for face in edge_faces[edge] if face in selected)
            unselected_side.update(face for face in edge_faces[edge] if face not in selected)
        if len(selected_side) <= len(unselected_side):
            removed.update(selected_side)
        else:
            added.update(unselected_side)
    selected.difference_update(removed)
    selected.update(added)
    return {"added": len(added), "removed": len(removed)}


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    guide_path = args.guide_report.resolve()
    output = args.output_blend.resolve()
    report_path = args.report.resolve()
    if output.exists() or report_path.exists():
        raise RuntimeError("Limb-band audit refuses to overwrite evidence")
    guide = json.loads(guide_path.read_text(encoding="utf-8"))
    bpy.ops.wm.open_mainfile(filepath=str(source))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError("Limb-band audit requires exactly one mesh")
    obj = meshes[0]
    mesh = obj.data
    rings = {record["id"]: record for record in guide["rings"]}

    palette = [
        (0.55, 0.57, 0.61, 1.0),
        (0.95, 0.12, 0.06, 1.0),
        (0.05, 0.35, 1.0, 1.0),
        (1.0, 0.48, 0.03, 1.0),
        (0.06, 0.72, 0.25, 1.0),
    ]
    mesh.materials.clear()
    for index, color in enumerate(palette):
        mesh.materials.append(material("AUDIT_LimbBand_{0}".format(index), color))
    for polygon in mesh.polygons:
        polygon.material_index = 0

    claimed: set[int] = set()
    records = []
    for material_index, (limb, endpoints) in enumerate(LIMBS.items(), start=1):
        radius_scale = args.radius_scale
        if limb.endswith("arm") and args.arm_radius_scale is not None:
            radius_scale = args.arm_radius_scale
        if limb.endswith("leg") and args.leg_radius_scale is not None:
            radius_scale = args.leg_radius_scale
        start, start_radius = ring_geometry(rings[endpoints[0]])
        end, end_radius = ring_geometry(rings[endpoints[1]])
        end_fraction = (
            args.arm_end_fraction if limb.endswith("arm") else args.leg_end_fraction
        )
        end = start + (end - start) * end_fraction
        end_radius = start_radius + (end_radius - start_radius) * end_fraction
        direction = end - start
        length = direction.length
        axis = direction.normalized()
        lower = args.end_inset / length
        upper = 1.0 - lower
        selected = set()
        for polygon in mesh.polygons:
            centroid = face_centroid(mesh, polygon)
            relative = centroid - start
            progress = relative.dot(axis) / length
            if not lower <= progress <= upper:
                continue
            centerline = start + direction * progress
            radius = start_radius + (end_radius - start_radius) * progress
            if (centroid - centerline).length <= radius * radius_scale:
                selected.add(polygon.index)
        small_component_repair = fill_small_selection_holes(
            mesh, selected, args.fill_small_boundary_max_edges
        )
        overlap = selected & claimed
        if overlap:
            raise RuntimeError("Limb selections overlap by {0} faces".format(len(overlap)))
        claimed |= selected
        for face_index in selected:
            mesh.polygons[face_index].material_index = material_index
        components = boundary_components(mesh, selected)
        records.append(
            {
                "id": limb,
                "start_ring": endpoints[0],
                "end_ring": endpoints[1],
                "start_center": list(start),
                "end_center": list(end),
                "start_radius_m": start_radius,
                "end_radius_m": end_radius,
                "radius_scale": radius_scale,
                "end_fraction": end_fraction,
                "selected_faces": len(selected),
                "small_component_repair": small_component_repair,
                "boundary_components": components,
                "eligible_for_surgery": len(components) == 2 and all(
                    bool(component["closed_degree_two"]) for component in components
                ),
            }
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    report = {
        "schema": "reference-asset-compiler.limb-band-surgery-audit.v1",
        "status": "mechanical_pass" if all(record["eligible_for_surgery"] for record in records) else "rejected",
        "purpose": "Preview controlled limb bands on downstream AI-derived topology; no image reconstruction and no topology mutation.",
        "source": {"path": str(source), "sha256": sha256_file(source), "topology": topology(obj)},
        "guide_report": {"path": str(guide_path), "sha256": sha256_file(guide_path)},
        "settings": {
            "radius_scale": args.radius_scale,
            "arm_radius_scale": args.arm_radius_scale,
            "leg_radius_scale": args.leg_radius_scale,
            "arm_end_fraction": args.arm_end_fraction,
            "leg_end_fraction": args.leg_end_fraction,
            "end_inset": args.end_inset,
            "fill_small_boundary_max_edges": args.fill_small_boundary_max_edges,
        },
        "limbs": records,
        "selected_faces_total": len(claimed),
        "requires_visual_review": True,
        "topology_mutated": False,
        "production_grade": False,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("RAC_LIMB_BAND_AUDIT_{0} {1}".format("OK" if report["status"] == "mechanical_pass" else "REJECTED", report_path))
    return 0 if report["status"] == "mechanical_pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
