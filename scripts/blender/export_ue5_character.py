"""Export a rigged character blend as a centimetre FBX for Unreal's legacy FBX importer.

blender -b <character_UE5.blend> --python export_ue5_character.py -- <out.fbx>

Meshes and the armature (named ``root``, which becomes the root bone) are
scaled to centimetres in a throwaway session; weights, UVs and shape keys
travel unchanged. These settings are the ones fit_ue5_manny_rig.py's bone
axes were measured against (Blender bone axes map to UE as diag(1, -1, 1)),
so keep them in step. A provenance JSON lands beside the FBX.
"""
import hashlib
import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

output = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
output.parent.mkdir(parents=True, exist_ok=True)
objects = [obj for obj in bpy.context.scene.objects if obj.type in {"MESH", "ARMATURE"}]
for obj in bpy.context.scene.objects:
    obj.select_set(obj in objects)
bpy.context.view_layer.objects.active = next(obj for obj in objects if obj.type == "ARMATURE")
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
for obj in objects:
    if obj.type == "MESH":
        obj.data.transform(Matrix.Scale(100.0, 4), shape_keys=True)
    else:
        obj.data.transform(Matrix.Scale(100.0, 4))
        obj.animation_data_clear()
    obj.location *= 100.0
bpy.context.scene.unit_settings.system = "METRIC"
bpy.context.scene.unit_settings.scale_length = 0.01
bpy.context.view_layer.update()
for obj in bpy.context.scene.objects:
    obj.select_set(obj in objects)
bpy.ops.export_scene.fbx(
    filepath=str(output), use_selection=True, object_types={"ARMATURE", "MESH"},
    path_mode="RELATIVE", embed_textures=False, bake_anim=False, use_mesh_modifiers=False,
    apply_scale_options="FBX_SCALE_ALL", apply_unit_scale=True,
    global_scale=1.0, axis_forward="-Y", axis_up="Z", add_leaf_bones=False, mesh_smooth_type="FACE",
)
output.with_suffix(".json").write_text(json.dumps({
    "blender": bpy.app.version_string,
    "input": bpy.data.filepath,
    "input_sha256": hashlib.sha256(Path(bpy.data.filepath).read_bytes()).hexdigest(),
    "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    "bounds_cm": {obj.name: [[min((obj.matrix_world @ Vector(c))[i] for c in obj.bound_box),
                              max((obj.matrix_world @ Vector(c))[i] for c in obj.bound_box)] for i in range(3)]
                  for obj in objects if obj.type == "MESH"},
}, indent=2))
print("UE5 FBX written:", output)
