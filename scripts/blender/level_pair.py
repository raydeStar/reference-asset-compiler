"""Level a generated model and its own simplified exports with one transform.

Pixal3D keeps the reference picture's camera tilt, so its meshes come out
leaning. Levelling each file on its own would tilt the dense mesh and the game
mesh by slightly different amounts, and a normal bake from one onto the other
would then miss by millimetres everywhere. The transform is worked out once,
from the first (dense) mesh, and applied to every file:

- principal axes become X (the length), Y (the breadth) and Z (up, the open
  side of a boat or bowl up: the wider end of the short axis);
- `--up` says which principal axis is up: the shortest (the default: a boat,
  a bench, a crate), the longest (a lantern, a ladder, a column standing), or
  the middle one (a wall panel or a sign standing on its edge). `--flip` turns
  the result upside down when the fixed views show it standing on its head;
- the model's longest principal axis is scaled to the size asked for, or with
  `--height` its height, the way a size given as a landmark on a person means;
- the model is centred on X and Y and stood on the floor (lowest point at 0).

Each mesh is welded where its export split vertices along texture seams, its
materials and UVs are dropped (the game mesh is unwrapped and painted
afterwards), and it is saved as a .blend, which `uv-unwrap` and `bake-shape`
open directly. A JSON report records the transform and each file's extent.

Usage:
  blender -b --factory-startup --python scripts/blender/level_pair.py -- \\
      <length m> <report.json> <dense.glb> <dense.blend> [<low.glb> <low.blend>]... \\
      [--up shortest|middle|longest] [--flip] [--height]
"""

from __future__ import annotations

import json
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix


def load(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=path)
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError("{0} holds no mesh".format(path))
    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    before = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=max(obj.dimensions) * 1e-6)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    for other in [item for item in bpy.data.objects if item.type != "MESH"]:
        bpy.data.objects.remove(other, do_unlink=True)
    obj.data.materials.clear()
    while obj.data.uv_layers:
        obj.data.uv_layers.remove(obj.data.uv_layers[0])
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    return obj, before - len(obj.data.vertices)


UP_AXIS = {"shortest": (0, 1, 2), "middle": (0, 2, 1), "longest": (1, 2, 0)}
"""For each choice of up, which principal axes (longest first) become X, Y and Z."""


def levelling_transform(points, length, up="shortest", flip=False, by_height=False):
    """Principal axes to X/Y/Z, open side up, longest axis (or the height) to `length`, centred, on the floor."""
    centre = points.mean(axis=0)
    _, _, rows = np.linalg.svd(points - centre, full_matrices=False)
    axes = rows[list(UP_AXIS[up])].copy()
    if np.linalg.det(axes) < 0:
        axes[2] *= -1
    local = (points - centre) @ axes.T
    height = local[:, 2]
    low, high = np.percentile(height, 5), np.percentile(height, 95)
    if np.ptp(local[height < low, 1]) > np.ptp(local[height > high, 1]):
        axes[2] *= -1
        axes[1] *= -1
    if flip:
        axes[2] *= -1
        axes[1] *= -1
    rotate = np.eye(4)
    rotate[:3, :3] = axes
    shift = np.eye(4)
    shift[:3, 3] = -centre
    turned = (np.c_[points, np.ones(len(points))] @ (rotate @ shift).T)[:, :3]
    scale = length / np.ptp(turned[:, 2 if by_height else UP_AXIS[up].index(0)])
    turned *= scale
    place = np.eye(4)
    place[:3, 3] = [-(turned[:, 0].min() + turned[:, 0].max()) / 2,
                    -(turned[:, 1].min() + turned[:, 1].max()) / 2, -turned[:, 2].min()]
    size = np.eye(4) * scale
    size[3, 3] = 1.0
    return place @ size @ rotate @ shift


def main(argv) -> int:
    argv = list(argv)
    up, flip, by_height = "shortest", False, False
    if "--height" in argv:
        argv.remove("--height")
        by_height = True
    if "--flip" in argv:
        argv.remove("--flip")
        flip = True
    if "--up" in argv:
        at = argv.index("--up")
        up = argv[at + 1] if at + 1 < len(argv) else ""
        del argv[at:at + 2]
        if up not in UP_AXIS:
            print("[LEVEL] FAILED: --up is shortest, middle or longest")
            return 1
    length, report_path = float(argv[0]), argv[1]
    pairs = list(zip(argv[2::2], argv[3::2]))
    if not pairs:
        print("[LEVEL] FAILED: expected <length> <report.json> <dense.glb> <dense.blend> [...]")
        return 1
    transform, records = None, []
    for source, output in pairs:
        obj, welded = load(source)
        points = np.array([vertex.co for vertex in obj.data.vertices], dtype=np.float64)
        if transform is None:
            transform = levelling_transform(points, length, up, flip, by_height)
        obj.data.transform(Matrix(transform.tolist()))
        obj.data.update()
        obj.name = "GEO_" + bpy.path.display_name_from_filepath(output)
        bpy.ops.wm.save_as_mainfile(filepath=output)
        levelled = np.array([vertex.co for vertex in obj.data.vertices])
        records.append({"source": source, "output": output, "seam_copies_welded": int(welded),
                        "triangles": int(sum(len(p.vertices) - 2 for p in obj.data.polygons)),
                        "min_m": levelled.min(axis=0).round(4).tolist(),
                        "max_m": levelled.max(axis=0).round(4).tolist()})
        print("[LEVEL] {0}: {1} triangles, {2} seam copies welded".format(
            output, records[-1]["triangles"], welded))
    with open(report_path, "w", encoding="utf-8") as stream:
        json.dump({"schema": "reference-asset-compiler.level-pair.v1", "length_m": length, "size_is": "height" if by_height else "longest side", "up": up, "flip": flip,
                   "transform": np.round(transform, 8).tolist(), "files": records}, stream, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []))
