"""Flat material-ID render: one saturated colour per material slot, no lighting.

Slot misassignment is invisible under a texture and obvious here. Prints the
colour legend so a pixel can be named.

Usage:
  blender -b --factory-startup --python scripts/blender/render_matid.py \
      -- <asset.fbx> <out.png> [bone] [radius_m] [angle]
"""

from __future__ import annotations

import colorsys
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def mesh_bounds(meshes):
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for obj in meshes:
        mw = obj.matrix_world
        for v in obj.data.vertices:
            w = mw @ v.co
            for i in range(3):
                lo[i] = min(lo[i], w[i])
                hi[i] = max(hi[i], w[i])
    return lo, hi


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:]
    asset_path, out_path = Path(argv[0]), Path(argv[1])
    bone_name = argv[2] if len(argv) > 2 else None
    radius = float(argv[3]) if len(argv) > 3 else None
    angle_deg = float(argv[4]) if len(argv) > 4 else 0.0

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(asset_path))
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]

    materials = []
    for obj in meshes:
        for slot in obj.material_slots:
            if slot.material is not None and slot.material not in materials:
                materials.append(slot.material)

    for index, mat in enumerate(materials):
        hue = index / max(len(materials), 1)
        rgb = colorsys.hsv_to_rgb(hue, 0.95, 1.0)
        mat.use_nodes = True
        tree = mat.node_tree
        tree.nodes.clear()
        out = tree.nodes.new("ShaderNodeOutputMaterial")
        emit = tree.nodes.new("ShaderNodeEmission")
        emit.inputs["Color"].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
        tree.links.new(emit.outputs["Emission"], out.inputs["Surface"])
        print("[MATID] {0:<40} rgb=({1:.2f}, {2:.2f}, {3:.2f})".format(
            mat.name, rgb[0], rgb[1], rgb[2]))

    if bone_name and radius:
        armature = next(o for o in bpy.data.objects if o.type == "ARMATURE")
        bone = armature.data.bones.get(bone_name)
        centre = armature.matrix_world @ bone.head_local
        frame = radius * 2.4
    else:
        lo, hi = mesh_bounds(meshes)
        centre = (lo + hi) * 0.5
        frame = max(hi - lo) * 1.25

    scene = bpy.context.scene
    engines = scene.render.bl_rna.properties["engine"].enum_items.keys()
    for candidate in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"):
        if candidate in engines:
            scene.render.engine = candidate
            break
    scene.render.resolution_x = 1000
    scene.render.resolution_y = 1000
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "Standard"
    scene.render.film_transparent = True

    cam_data = bpy.data.cameras.new("MatIdCam")
    cam_data.lens = 85.0
    cam = bpy.data.objects.new("MatIdCam", cam_data)
    bpy.context.collection.objects.link(cam)
    fov = 2.0 * math.atan(0.5 * cam_data.sensor_width / cam_data.lens)
    distance = frame / (2.0 * math.tan(fov * 0.5))
    angle = math.radians(angle_deg)
    cam.location = centre + Vector(
        (math.sin(angle) * distance, -math.cos(angle) * distance, 0.0)
    )
    cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam

    out_path.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(out_path)
    bpy.ops.render.render(write_still=True)
    print("[MATID] {0}".format(out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
