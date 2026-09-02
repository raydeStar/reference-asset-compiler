"""Export triangle UVs tagged with the body region that owns them.

Written as a compact .npz so a plain Python pass can rasterise a region map in
UV space without needing Blender. That map is what makes it possible to say
"this patch of atlas belongs to a thigh" and act on it.

Usage:
  blender -b --factory-startup --python scripts/blender/export_uv_regions.py \
      -- <asset.fbx> <out.npz>
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import bpy
import numpy as np

REGIONS = ["head", "torso", "arm", "hand", "leg", "foot", "other"]


def region_for_bone(name):
    if not name:
        return "other"
    base = name.lower()
    for token, region in (
        ("thumb", "hand"), ("index", "hand"), ("middle", "hand"),
        ("ring", "hand"), ("pinky", "hand"), ("hand", "hand"),
        ("upperarm", "arm"), ("lowerarm", "arm"), ("clavicle", "arm"),
        ("thigh", "leg"), ("calf", "leg"),
        ("ball", "foot"), ("foot", "foot"),
        ("spine", "torso"), ("pelvis", "torso"),
        ("neck", "head"), ("head", "head"),
    ):
        if token in base:
            return region
    return "other"


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:]
    asset_path, out_path = Path(argv[0]), Path(argv[1])

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(asset_path))

    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    armatures = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if not meshes:
        print("[UVREGION] FAILED: need a mesh")
        return 1
    # The armature is only ever used to label each triangle with the body
    # region that drives it. A static prop has no bones, so every triangle
    # takes the "other" label and the rest of the map -- UVs, materials,
    # centres, normals, areas -- is exactly as useful as it is for a character.
    # The texture gate reads all of those; it reads regions only to report
    # density per region.
    bone_names = ({b.name for b in armatures[0].data.bones} if armatures
                  else set())

    tri_uv = []
    tri_region = []
    tri_material = []
    tri_centre = []
    tri_normal = []
    tri_area = []
    material_names = []

    for obj in meshes:
        me = obj.data
        me.calc_loop_triangles()
        uv_layer = me.uv_layers.active
        if uv_layer is None:
            continue
        group_name = {g.index: g.name for g in obj.vertex_groups}

        vert_region = np.empty(len(me.vertices), dtype=np.int8)
        for i, v in enumerate(me.vertices):
            best_weight = 0.0
            best = None
            for g in v.groups:
                name = group_name.get(g.group)
                if name in bone_names and g.weight > best_weight:
                    best_weight = g.weight
                    best = name
            vert_region[i] = REGIONS.index(region_for_bone(best))

        base = len(material_names)
        material_names.extend(
            [m.name if m else "None" for m in me.materials] or ["None"]
        )

        for tri in me.loop_triangles:
            uvs = [uv_layer.data[loop].uv for loop in tri.loops]
            tri_uv.append([[uvs[0][0], uvs[0][1]],
                           [uvs[1][0], uvs[1][1]],
                           [uvs[2][0], uvs[2][1]]])
            counts = Counter(int(vert_region[i]) for i in tri.vertices)
            tri_region.append(counts.most_common(1)[0][0])
            tri_material.append(base + tri.material_index)
            centre = obj.matrix_world @ tri.center
            tri_centre.append([centre.x, centre.y, centre.z])
            normal = (obj.matrix_world.to_3x3() @ tri.normal).normalized()
            tri_normal.append([normal.x, normal.y, normal.z])
            tri_area.append(tri.area)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        str(out_path),
        uv=np.asarray(tri_uv, dtype=np.float32),
        region=np.asarray(tri_region, dtype=np.int8),
        material=np.asarray(tri_material, dtype=np.int32),
        centre=np.asarray(tri_centre, dtype=np.float32),
        normal=np.asarray(tri_normal, dtype=np.float32),
        area=np.asarray(tri_area, dtype=np.float32),
        region_names=np.asarray(REGIONS),
        material_names=np.asarray(material_names),
    )
    print("[UVREGION] {0} triangles -> {1}".format(len(tri_uv), out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
