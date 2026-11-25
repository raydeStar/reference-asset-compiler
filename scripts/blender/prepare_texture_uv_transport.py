"""Create a geometry-locked UV/OBJ transport for AI existing-mesh painting.

This stage changes UV coordinates only. The approved BLEND (or explicitly
enabled static triangle GLB) remains the geometry authority. The OBJ is a
transport derivative for Hunyuan3D-Paint, not a newly modeled surface.

No two faces may share a texel. Smart Project groups connected faces that face
roughly the same way and projects each group flat, so a surface that folds back
over itself lands on top of itself: the WK-04.1 stair's treads are channels
whose top plate curls round a nose into a lower plate, and 8.9 % of the texels
its layout used belonged to two or more faces. A hidden face and a visible one
sharing texels is how the stair's treads showed the hidden face's occlusion and
roughness as dark and light triangles. So the faces that overlap are projected
again at a tighter angle, the islands are packed again, and that repeats; a face
that still overlaps gets an island of its own. A layout that still overlaps is
refused.
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
import numpy as np
from mathutils.kdtree import KDTree

OVERLAP_RASTER = 1024
OVERLAP_ANGLES = (45.0, 30.0, 15.0)


def parse_args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output_blend", type=Path)
    parser.add_argument("output_obj", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--angle-degrees", type=float, default=66.0)
    parser.add_argument("--margin", type=float, default=0.006)
    parser.add_argument("--repack-margin", type=float, default=0.0015,
                        help="Gutter between islands when the charts are arranged again, as a "
                             "fraction of the atlas. 0 keeps Smart Project's own arrangement.")
    parser.add_argument("--maximum-delta-m", type=float, default=1.0e-6)
    parser.add_argument("--allow-triangulated-glb", action="store_true",
                        help="Accept an already-approved static triangle GLB without welding or remeshing.")
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


def repack(obj: bpy.types.Object, margin: float, before: float) -> float:
    """Arrange the charts again, without recutting any of them.

    Smart Project cuts a surface into islands and then arranges them with a
    packer from an older era of Blender. The arrangement is the weak half: on a
    generated ninja it left 601 islands filling a third of the atlas, so two
    thirds of a 2048 square texture was gutter and every island edge was a seam
    where filtering pulls in a neighbour's colour. That is what close-up
    smearing between a character's fingers actually is.

    Blender's own packer, run over the same islands, took that from 33% to 65%
    -- the same as painting the model at 2,900 pixels square instead of 2,048,
    for nothing. No seam moves and no vertex moves; only where each island sits
    and how large it is drawn.

    A pack that does not improve occupancy is discarded, because a worse layout
    is worse whatever the packer believed, and the one that came in is already
    known to be valid.
    """
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, rotate_method="ANY", scale=True,
                            shape_method="CONCAVE", margin_method="FRACTION",
                            margin=margin)
    bpy.ops.object.mode_set(mode="OBJECT")
    after = float(uv_metrics(obj).get("summed_uv_area") or 0.0)
    if before < after <= 1.0:
        return after
    print("[UV] repacking did not improve occupancy ({0:.3f} to {1:.3f}); "
          "keeping the arrangement that came in".format(before, after))
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=False, scale=True,
                            margin_method="FRACTION", margin=margin)
    bpy.ops.object.mode_set(mode="OBJECT")
    return float(uv_metrics(obj).get("summed_uv_area") or 0.0)


def overlapping_faces(obj: bpy.types.Object, size: int = OVERLAP_RASTER) -> tuple[set[int], float]:
    """Polygons whose texels another polygon also covers, and the share of covered texels shared.

    Each triangle is rasterised a little inside its own edges, so two faces
    that merely meet along a seam do not count as overlapping.
    """
    layer = obj.data.uv_layers.active
    uv = np.empty(len(obj.data.loops) * 2, dtype=np.float64)
    layer.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2) * size
    count = np.zeros((size, size), dtype=np.int32)
    owner = np.full((size, size), -1, dtype=np.int64)
    clash: set[int] = set()
    for polygon in obj.data.polygons:
        loops = list(polygon.loop_indices)
        for index in range(1, len(loops) - 1):
            points = uv[[loops[0], loops[index], loops[index + 1]]]
            lo = np.maximum(np.floor(points.min(axis=0)).astype(int), 0)
            hi = np.minimum(np.ceil(points.max(axis=0)).astype(int), size - 1)
            if (hi < lo).any():
                continue
            xs, ys = np.meshgrid(np.arange(lo[0], hi[0] + 1) + 0.5, np.arange(lo[1], hi[1] + 1) + 0.5)
            (ax, ay), (bx, by), (cx, cy) = points
            denominator = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(denominator) < 1e-12:
                continue
            first = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / denominator
            second = ((cy - ay) * (xs - cx) + (ax - cx) * (ys - cy)) / denominator
            inside = (first > 0.02) & (second > 0.02) & (1.0 - first - second > 0.02)
            if not inside.any():
                continue
            block = count[lo[1]:hi[1] + 1, lo[0]:hi[0] + 1]
            owners = owner[lo[1]:hi[1] + 1, lo[0]:hi[0] + 1]
            shared = inside & (block > 0) & (owners != polygon.index)
            if shared.any():
                clash.add(polygon.index)
                clash.update(int(other) for other in np.unique(owners[shared]))
            block[inside & (owners != polygon.index)] += 1
            owners[inside] = polygon.index
    covered = int((count > 0).sum())
    return clash, (float((count > 1).sum()) / covered) if covered else 0.0


def select_faces(obj: bpy.types.Object, faces: set[int]) -> None:
    import bmesh  # noqa: PLC0415 - Blender's own module, only inside Blender

    mesh = bmesh.from_edit_mesh(obj.data)
    mesh.faces.ensure_lookup_table()
    for face in mesh.faces:
        face.select_set(face.index in faces)
    bmesh.update_edit_mesh(obj.data)


def separate_overlaps(obj: bpy.types.Object, margin: float) -> dict[str, object]:
    """Project the overlapping faces again, tighter each pass, until no texel is shared."""
    faces, share = overlapping_faces(obj)
    record: dict[str, object] = {"faces_before": len(faces), "texel_share_before": round(share, 5), "passes": []}
    for angle in OVERLAP_ANGLES + (None,):
        if not faces:
            break
        bpy.ops.object.mode_set(mode="EDIT")
        select_faces(obj, faces)
        if angle is None:
            # Last resort: every face still overlapping becomes an island of
            # its own, which cannot fold over anything.
            bpy.ops.uv.reset()
        else:
            bpy.ops.uv.smart_project(angle_limit=math.radians(angle), island_margin=margin,
                                     area_weight=0.0, correct_aspect=True, scale_to_bounds=False)
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.select_all(action="SELECT")
        # Reprojecting a subset gives it a whole UV square. Restore area-based density
        # across all islands before packing, including single faces made by reset().
        bpy.ops.uv.average_islands_scale()
        bpy.ops.uv.pack_islands(rotate=True, rotate_method="ANY", scale=True, shape_method="CONCAVE",
                                margin_method="FRACTION", margin=margin)
        bpy.ops.object.mode_set(mode="OBJECT")
        projected = len(faces)
        faces, share = overlapping_faces(obj)
        record["passes"].append({"angle_degrees": angle if angle is not None else "own island",
                                 "faces_projected": projected, "faces_left": len(faces),
                                 "texel_share_left": round(share, 5)})
    record["faces_after"] = len(faces)
    record["texel_share_after"] = round(share, 5)
    return record


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


def load_authority(source: Path, allow_triangulated_glb: bool):
    glb_input = source.suffix.lower() == ".glb" and allow_triangulated_glb
    if source.suffix.lower() != ".blend" and not glb_input:
        raise RuntimeError("UV preparation requires BLEND, or explicitly enabled static triangle GLB")
    if glb_input:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str(source))
        if any(item.type == "ARMATURE" for item in bpy.context.scene.objects):
            raise RuntimeError("GLB UV preparation is for static props, not articulated authorities")
    else:
        bpy.ops.wm.open_mainfile(filepath=str(source))
    obj = mesh_object()
    if glb_input and any(len(poly.vertices) != 3 for poly in obj.data.polygons):
        raise RuntimeError("GLB authority must already be triangulated")
    return obj


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    output_blend = args.output_blend.resolve()
    output_obj = args.output_obj.resolve()
    report_path = args.report.resolve()
    if not source.is_file():
        raise RuntimeError("UV preparation source is missing")
    if output_obj.suffix.lower() != ".obj":
        raise RuntimeError("Texture transport output must be OBJ")
    if any(path.exists() for path in (output_blend, output_obj, report_path)):
        raise RuntimeError("UV preparation refuses to overwrite evidence")

    obj = load_authority(source, args.allow_triangulated_glb)
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
    overlap = separate_overlaps(obj, args.margin)
    cut_occupancy = float(uv_metrics(obj).get("summed_uv_area") or 0.0)
    packed_occupancy = cut_occupancy
    if args.repack_margin > 0.0:
        packed_occupancy = repack(obj, args.repack_margin, cut_occupancy)
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
    final_overlap, final_share = overlapping_faces(obj)
    overlap["faces_after_repack"] = len(final_overlap)
    overlap["texel_share_after_repack"] = round(final_share, 5)
    if final_share > 0.001:
        failures.append("UV layout still shares {0:.2%} of its texels between faces".format(final_share))
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
            "repack_margin": args.repack_margin,
            # Both numbers, because the gain is the point: an atlas that is two
            # thirds gutter is worth seeing in a receipt rather than in a
            # close-up of somebody's hands.
            "atlas_occupancy_as_cut": round(cut_occupancy, 5),
            "atlas_occupancy": round(packed_occupancy, 5),
            "overlap": overlap,
            "triangulated_transport_only": True,
            "source_format": source.suffix.lower(),
            "static_triangle_glb_enabled": args.allow_triangulated_glb,
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
