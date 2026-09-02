"""Create a geometry-locked UV/OBJ transport for AI existing-mesh painting.

This stage changes UV coordinates only.  The approved retopology BLEND remains
the geometry authority; the triangulated OBJ is a transport derivative for
Hunyuan3D-Paint, which cannot consume BLEND directly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from collections import Counter

import bpy
from mathutils.kdtree import KDTree


def parse_args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output_blend", type=Path)
    parser.add_argument("output_obj", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--angle-degrees", type=float, default=66.0)
    parser.add_argument("--margin", type=float, default=0.006)
    parser.add_argument("--maximum-delta-m", type=float, default=1.0e-6)
    return parser.parse_args(values)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def mesh_object() -> bpy.types.Object:
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError(
            "UV preparation requires exactly one approved mesh; found {0}".format(
                len(meshes)
            )
        )
    return meshes[0]


def snapshot(obj: bpy.types.Object) -> dict[str, object]:
    mesh = obj.data
    mesh.calc_loop_triangles()
    degenerate_triangles = sum(
        1 for triangle in mesh.loop_triangles if triangle.area <= 1.0e-12
    )
    triangle_keys = Counter(
        tuple(sorted(int(index) for index in triangle.vertices))
        for triangle in mesh.loop_triangles
    )
    duplicate_triangles = sum(count - 1 for count in triangle_keys.values() if count > 1)
    return {
        "vertices": len(mesh.vertices),
        "polygons": len(mesh.polygons),
        "triangles": len(mesh.loop_triangles),
        "degenerate_triangles": degenerate_triangles,
        "duplicate_triangles": duplicate_triangles,
        "positions": [obj.matrix_world @ vertex.co for vertex in mesh.vertices],
        "polygon_indices": [tuple(poly.vertices) for poly in mesh.polygons],
    }


def uv_metrics(obj: bpy.types.Object) -> dict[str, object]:
    layer = obj.data.uv_layers.active
    if layer is None:
        return {"complete": False}
    values = [tuple(float(value) for value in loop.uv) for loop in layer.data]
    finite = bool(values) and all(math.isfinite(value) for pair in values for value in pair)
    nondegenerate = 0
    uv_area = 0.0
    for polygon in obj.data.polygons:
        points = [layer.data[index].uv for index in polygon.loop_indices]
        area = 0.0
        for index in range(1, len(points) - 1):
            a, b, c = points[0], points[index], points[index + 1]
            area += abs(
                (b.x - a.x) * (c.y - a.y) - (c.x - a.x) * (b.y - a.y)
            ) * 0.5
        uv_area += area
        if area > 1.0e-12:
            nondegenerate += 1
    return {
        "layer": layer.name,
        "complete": finite and len(values) == len(obj.data.loops),
        "loops": len(values),
        "minimum": min((min(pair) for pair in values), default=None),
        "maximum": max((max(pair) for pair in values), default=None),
        "nondegenerate_polygon_fraction": nondegenerate / max(1, len(obj.data.polygons)),
        "summed_uv_area": uv_area,
    }


def one_way_max(source, target) -> float:
    tree = KDTree(len(target))
    for index, point in enumerate(target):
        tree.insert(point, index)
    tree.balance()
    maximum = 0.0
    for point in source:
        _nearest, _index, distance = tree.find(point)
        maximum = max(maximum, float(distance))
    return maximum


def public(value: dict[str, object]) -> dict[str, object]:
    return {
        key: item
        for key, item in value.items()
        if key not in {"positions", "polygon_indices"}
    }


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    output_blend = args.output_blend.resolve()
    output_obj = args.output_obj.resolve()
    report_path = args.report.resolve()
    if source.suffix.lower() != ".blend" or not source.is_file():
        raise RuntimeError("UV preparation requires the approved BLEND authority")
    if output_obj.suffix.lower() != ".obj":
        raise RuntimeError("Texture transport output must be OBJ")
    if any(path.exists() for path in (output_blend, output_obj, report_path)):
        raise RuntimeError("UV preparation refuses to overwrite evidence")

    bpy.ops.wm.open_mainfile(filepath=str(source))
    obj = mesh_object()
    before = snapshot(obj)
    while obj.data.uv_layers:
        obj.data.uv_layers.remove(obj.data.uv_layers[0])
    obj.data.uv_layers.new(name="UV_RAC_AI_Paint")
    if not obj.data.materials:
        material = bpy.data.materials.new("M_RAC_AI_Paint")
        material.diffuse_color = (0.5, 0.5, 0.5, 1.0)
        obj.data.materials.append(material)

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(
        angle_limit=math.radians(args.angle_degrees),
        island_margin=args.margin,
        area_weight=0.0,
        correct_aspect=True,
        scale_to_bounds=False,
    )
    bpy.ops.object.mode_set(mode="OBJECT")
    after = snapshot(obj)
    metrics = uv_metrics(obj)
    failures: list[str] = []
    if before["vertices"] != after["vertices"]:
        failures.append("UV preparation changed vertex count")
    if before["polygon_indices"] != after["polygon_indices"]:
        failures.append("UV preparation changed polygon topology")
    coordinate_delta = one_way_max(before["positions"], after["positions"])
    if coordinate_delta > args.maximum_delta_m:
        failures.append("UV preparation moved the approved surface")
    if not metrics["complete"]:
        failures.append("UV layout is incomplete or non-finite")
    if metrics.get("minimum") is None or float(metrics["minimum"]) < -1.0e-6:
        failures.append("UV layout falls below zero")
    if metrics.get("maximum") is None or float(metrics["maximum"]) > 1.0 + 1.0e-6:
        failures.append("UV layout exceeds one")
    if float(metrics.get("nondegenerate_polygon_fraction", 0.0)) < 0.999:
        failures.append("UV layout contains degenerate polygons")
    if failures:
        raise RuntimeError("; ".join(failures))

    output_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    bpy.ops.wm.obj_export(
        filepath=str(output_obj),
        export_selected_objects=True,
        export_materials=True,
        export_uv=True,
        export_normals=True,
        export_triangulated_mesh=True,
        forward_axis="NEGATIVE_Z",
        up_axis="Y",
    )

    # Reimport the transport and prove that triangulation/serialization did not
    # move the accepted surface or change the runtime triangle count.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.wm.obj_import(filepath=str(output_obj))
    transported_obj = mesh_object()
    transported = snapshot(transported_obj)
    transport_metrics = uv_metrics(transported_obj)
    forward = one_way_max(after["positions"], transported["positions"])
    reverse = one_way_max(transported["positions"], after["positions"])
    transport_delta = max(forward, reverse)
    triangles_removed = int(after["triangles"]) - int(transported["triangles"])
    if triangles_removed < 0:
        failures.append("OBJ transport added triangles")
    elif triangles_removed > (
        int(after["degenerate_triangles"]) + int(after["duplicate_triangles"])
    ):
        failures.append("OBJ transport removed unique nondegenerate triangles")
    if transport_delta > args.maximum_delta_m:
        failures.append("OBJ transport moved the approved surface")
    if not transport_metrics["complete"]:
        failures.append("OBJ transport lost the UV layout")

    report = {
        "schema": "reference-asset-compiler.texture-uv-transport.v1",
        "status": "passed" if not failures else "rejected",
        "source": {"path": str(source), "sha256": sha256(source), **public(before)},
        "uv_authority": {
            "path": str(output_blend),
            "sha256": sha256(output_blend),
            **public(after),
            "uv": metrics,
            "maximum_geometry_delta_m": coordinate_delta,
        },
        "transport": {
            "path": str(output_obj),
            "sha256": sha256(output_obj),
            **public(transported),
            "uv": transport_metrics,
            "maximum_symmetric_vertex_delta_m": transport_delta,
            "triangles_removed_as_redundant": triangles_removed,
        },
        "settings": {
            "method": "Blender Smart Project",
            "angle_degrees": args.angle_degrees,
            "margin": args.margin,
            "triangulated_transport_only": True,
        },
        "failures": failures,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if failures:
        print("RAC_TEXTURE_UV_TRANSPORT_REJECTED {0}".format("; ".join(failures)))
        return 1
    print(
        "RAC_TEXTURE_UV_TRANSPORT_OK triangles={0} delta_m={1:.9f}".format(
            transported["triangles"], transport_delta
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
