"""Render UV coordinates as colour (R=u, G=v) for a framed body region.

Lets a pixel in a render be traced back to an exact atlas coordinate, which
turns "why is there a face on this trouser leg" from a guess into a lookup.

Usage:
  blender -b --factory-startup --python scripts/blender/render_uv_debug.py \
      -- <asset.fbx> <out.png> <bone> <radius_m> [angle]
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:]
    asset_path, out_path = Path(argv[0]), Path(argv[1])
    bone_name = argv[2]
    radius = float(argv[3])
    angle_deg = float(argv[4]) if len(argv) > 4 else 0.0

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(asset_path))

    armature = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    bone = armature.data.bones.get(bone_name)
    if bone is None:
        print("[UVDEBUG] FAILED: no bone {0}".format(bone_name))
        return 1
    centre = armature.matrix_world @ bone.head_local

    mat = bpy.data.materials.new("UVDebug")
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    emit = tree.nodes.new("ShaderNodeEmission")
    uvmap = tree.nodes.new("ShaderNodeUVMap")
    tree.links.new(uvmap.outputs["UV"], emit.inputs["Color"])
    tree.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    bpy.context.scene.view_layers[0].material_override = mat

    scene = bpy.context.scene
    engines = scene.render.bl_rna.properties["engine"].enum_items.keys()
    for candidate in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"):
        if candidate in engines:
            scene.render.engine = candidate
            break
    scene.render.resolution_x = 1000
    scene.render.resolution_y = 1000
    scene.render.image_settings.file_format = "PNG"
    # Raw, not Filmic: the pixel value must survive as the literal UV.
    scene.view_settings.view_transform = "Raw"
    scene.render.film_transparent = True

    cam_data = bpy.data.cameras.new("UVCam")
    cam_data.lens = 85.0
    cam = bpy.data.objects.new("UVCam", cam_data)
    bpy.context.collection.objects.link(cam)
    fov = 2.0 * math.atan(0.5 * cam_data.sensor_width / cam_data.lens)
    distance = (radius * 2.4) / (2.0 * math.tan(fov * 0.5))
    angle = math.radians(angle_deg)
    cam.location = centre + Vector(
        (math.sin(angle) * distance, -math.cos(angle) * distance, radius * 0.2)
    )
    cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam

    out_path.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(out_path)
    bpy.ops.render.render(write_still=True)
    print("[UVDEBUG] {0}  camera at {1}, framing {2:.3f} m around {3}".format(
        out_path, [round(v, 3) for v in cam.location], radius * 2.4, bone_name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
