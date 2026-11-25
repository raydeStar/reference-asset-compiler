"""Bake a dense mesh's shape onto a painted game mesh, under the relief it already has.

A generator such as Pixal3D gives a million-triangle mesh whose bolts, plank
seams and strap edges are real geometry. The game mesh is a simplification of
the same model, painted on its own UVs. This bakes the dense surface onto the
game mesh as a tangent-space normal map (Cycles, selected to active, on the
CPU), at the size of the normal map the material already carries, or of its
base colour when it has none. Where the material already has a normal map (the
relief `bake-detail` raised from the paint), the two are combined with
reoriented normal mapping: the relief is turned onto the dense normal, not
added to it, so the paint's grain rides on the geometry's bevels.

The two meshes must be the same model in the same place: `level_pair.py`
levels them with one transform. They are refused if their bounding boxes'
centres differ by more than a centimetre or their diagonals by more than two.

A ray starts on the cage, `--cage` out from the game mesh, and takes the first
dense surface it meets going in. Pixal3D's dense meshes carry stray thin sheets
a few millimetres off the real surface (the WK-04.1 stair had one 4-40 mm under
its top landing). Where such a sheet lies inside the cage, the ray meets its
back first and bakes a normal pointing into the surface, which renders black:
a crescent where the sheet curves through the cage. A longer ray cannot help,
because the ray starts beyond the sheet. So the bake runs again from closer
cages (`--fallback-cages`), and each texel keeps the first result, from the
outermost cage in, that faces out of the surface. A texel that faces in from
every cage (mostly along sharp edges, where a ray strikes the next face) is
left flat: it gets no shape, but the relief still rides on it.

Usage:
  blender -b --factory-startup --python scripts/blender/bake_dense_shape.py -- \\
      <painted.glb> <output.glb> <report.json> --dense <dense.blend|dense.glb> \\
      [--cage 0.008] [--fallback-cages 0.003,0.001] [--max-ray 0.02]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

import bpy
import numpy as np
from mathutils import Vector

TAG = "[SHAPE]"
# A baked tangent-space normal whose z is below this points into the surface,
# or so nearly along it that it is a ray that struck the next face, not shape.
FACING_OUT = 0.05


def sha256(path):
    with open(path, "rb") as stream:
        return hashlib.sha256(stream.read()).hexdigest()


def box(obj):
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    low = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
    high = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
    return low, high


def reoriented(base, detail):
    """Reoriented normal mapping of two tangent-space normals in [-1, 1]."""
    t = base.copy()
    t[..., 2] += 1.0
    u = detail.copy()
    u[..., :2] *= -1.0
    out = t * (np.sum(t * u, axis=-1, keepdims=True) / np.maximum(t[..., 2:3], 1e-4)) - u
    return out / np.maximum(np.linalg.norm(out, axis=-1, keepdims=True), 1e-6)


def main(argv) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("output")
    parser.add_argument("report")
    parser.add_argument("--dense", required=True)
    parser.add_argument("--cage", type=float, default=0.008,
                        help="How far out the rays start, in metres; above the reduction's deviation")
    parser.add_argument("--fallback-cages", default="0.003,0.001",
                        help="Closer cages, in metres, comma-separated, for texels the first cage bakes "
                             "facing in; 'none' for one bake")
    parser.add_argument("--max-ray", type=float, default=0.02, help="How far a ray may travel, in metres")
    args = parser.parse_args(argv)
    started = time.time()
    cages = [args.cage]
    if args.fallback_cages.strip().lower() not in ("", "none"):
        cages += [float(value) for value in args.fallback_cages.split(",") if value.strip()]
    if any(cage <= 0 for cage in cages) or cages != sorted(cages, reverse=True):
        print("{0} FAILED: cages must be positive and each fallback closer than the one before: {1}".format(
            TAG, cages))
        return 1

    if args.dense.lower().endswith(".blend"):
        bpy.ops.wm.open_mainfile(filepath=args.dense)
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=args.dense)
    dense = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    if len(dense) != 1:
        print("{0} FAILED: the dense file should hold one mesh, it holds {1}".format(TAG, len(dense)))
        return 1
    dense = dense[0]
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=args.source)
    painted = [obj for obj in bpy.data.objects if obj not in before and obj.type == "MESH"]
    if len(painted) != 1 or len(painted[0].material_slots) != 1:
        print("{0} FAILED: the painted model should be one mesh with one material".format(TAG))
        return 1
    painted = painted[0]

    dense_low, dense_high = box(dense)
    low, high = box(painted)
    offset = ((dense_low + dense_high) / 2 - (low + high) / 2).length
    diagonal_gap = abs((dense_high - dense_low).length - (high - low).length)
    if offset > 0.01 or diagonal_gap > 0.02:
        print("{0} FAILED: the dense mesh and the painted one are not the same model in the same place "
              "(centres {1:.4f} m apart, diagonals {2:.4f} m apart). Level them together with "
              "level_pair.py".format(TAG, offset, diagonal_gap))
        return 1

    material = painted.material_slots[0].material
    tree = material.node_tree
    principled = next(node for node in tree.nodes if node.type == "BSDF_PRINCIPLED")
    normal_map = next((node for node in tree.nodes if node.type == "NORMAL_MAP"), None)
    relief_node = None
    if normal_map is not None and normal_map.inputs["Color"].links:
        relief_node = normal_map.inputs["Color"].links[0].from_node
    if relief_node is not None and relief_node.image is not None:
        width, height = relief_node.image.size
    else:
        colour = principled.inputs["Base Color"].links
        if not colour or colour[0].from_node.type != "TEX_IMAGE":
            print("{0} FAILED: the painted model has neither a normal map nor a base colour image to "
                  "size the bake by".format(TAG))
            return 1
        width, height = colour[0].from_node.image.size

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 1
    baked = bpy.data.images.new("dense_shape", width, height, alpha=False, float_buffer=True)
    baked.colorspace_settings.name = "Non-Color"
    target = tree.nodes.new("ShaderNodeTexImage")
    target.image = baked
    tree.nodes.active = target
    bpy.ops.object.select_all(action="DESELECT")
    dense.select_set(True)
    painted.select_set(True)
    bpy.context.view_layer.objects.active = painted
    shape = None
    unsettled = np.ones((height, width), dtype=bool)
    texels_by_cage = {}
    for cage in cages:
        if not unsettled.any():
            texels_by_cage["{0:g}".format(cage)] = 0
            continue
        # Cleared first: a bake leaves texels it does not reach as they were.
        baked.pixels.foreach_set(np.zeros(width * height * 4, dtype=np.float32))
        bpy.ops.object.bake(type="NORMAL", use_selected_to_active=True, cage_extrusion=cage,
                            max_ray_distance=args.max_ray, margin=16, normal_space="TANGENT")
        buffer = np.empty(width * height * 4, dtype=np.float32)
        baked.pixels.foreach_get(buffer)
        this = buffer.reshape(height, width, 4)[..., :3] * 2.0 - 1.0
        if shape is None:
            shape = this.copy()
        taken = unsettled & (this[..., 2] >= FACING_OUT)
        shape[taken] = this[taken]
        unsettled &= ~taken
        texels_by_cage["{0:g}".format(cage)] = int(taken.sum())
    texels_flat = int(unsettled.sum())
    shape[unsettled] = (0.0, 0.0, 1.0)
    pixels = np.ones((height, width, 4), dtype=np.float32)
    pixels[..., :3] = shape * 0.5 + 0.5
    baked.pixels.foreach_set(pixels.reshape(-1))
    baked.update()
    bake_seconds = time.time() - started

    if relief_node is not None and relief_node.image is not None:
        relief = np.asarray(relief_node.image.pixels[:], dtype=np.float32).reshape(height, width, 4)[..., :3]
        combined = reoriented(shape, relief * 2.0 - 1.0)
        mode = "the dense shape, with the existing relief turned onto it (reoriented normal mapping)"
    else:
        combined = shape / np.maximum(np.linalg.norm(shape, axis=-1, keepdims=True), 1e-6)
        mode = "the dense shape alone; the material had no normal map"
    pixels = np.ones((height, width, 4), dtype=np.float32)
    pixels[..., :3] = combined * 0.5 + 0.5
    result = bpy.data.images.new("normal", width, height, alpha=False, float_buffer=False)
    result.colorspace_settings.name = "Non-Color"
    result.pixels = pixels.reshape(-1).tolist()
    result.update()

    # Written to a file and reloaded before export: a generated image packs the
    # pattern it was created with, not what was put in its buffer.
    beside = os.path.splitext(args.output)[0] + "-maps"
    os.makedirs(beside, exist_ok=True)
    for image, name in ((baked, "dense_shape"), (result, "normal")):
        image.filepath_raw = os.path.join(beside, name + ".png")
        image.file_format = "PNG"
        image.save()
    result.source = "FILE"
    result.filepath = os.path.join(beside, "normal.png")
    result.reload()
    if relief_node is None:
        relief_node = tree.nodes.new("ShaderNodeTexImage")
        if normal_map is None:
            normal_map = tree.nodes.new("ShaderNodeNormalMap")
        tree.links.new(relief_node.outputs["Color"], normal_map.inputs["Color"])
        tree.links.new(normal_map.outputs["Normal"], principled.inputs["Normal"])
    relief_node.image = result
    tree.nodes.remove(target)
    bpy.data.objects.remove(dense, do_unlink=True)

    bpy.ops.object.select_all(action="DESELECT")
    painted.select_set(True)
    bpy.ops.export_scene.gltf(filepath=args.output, export_format="GLB", export_yup=True, export_apply=True,
                              use_selection=True, export_animations=False, export_cameras=False,
                              export_lights=False)
    tilt = np.degrees(np.arccos(np.clip(combined[..., 2], -1.0, 1.0)))
    report = {
        "schema": "reference-asset-compiler.dense-shape.v1",
        "source": args.source, "source_sha256": sha256(args.source),
        "dense": args.dense, "dense_sha256": sha256(args.dense),
        "output": args.output, "output_sha256": sha256(args.output),
        "size": [width, height], "cage_m": args.cage, "max_ray_m": args.max_ray,
        "cages_m": cages, "texels_by_cage": texels_by_cage, "texels_flat": texels_flat,
        "texels_flat_share": round(texels_flat / float(width * height), 5),
        "centre_offset_m": round(offset, 5), "diagonal_gap_m": round(diagonal_gap, 5),
        "normal": mode,
        "tilt_degrees_p50_p90": np.percentile(tilt, [50, 90]).round(2).tolist(),
        "bake_seconds": round(bake_seconds, 1), "seconds": round(time.time() - started, 1),
        "geometry_unchanged": True, "uvs_unchanged": True,
        "requires_fixed_view_review": True, "production_grade": False,
    }
    with open(args.report, "w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
    print("{0} baked the dense shape at {1}x{2} onto {3}".format(TAG, width, height, args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []))
