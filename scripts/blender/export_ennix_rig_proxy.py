"""Export a separate body/head skinning proxy without altering the facial authority."""
import sys
from pathlib import Path

import bpy


def main():
    source, out = (Path(x).resolve() for x in sys.argv[sys.argv.index("--") + 1:][:2])
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(source))
    bpy.ops.object.select_all(action="DESELECT")
    body = bpy.data.objects["Ennix_Outfit_And_Hands"]
    head = bpy.data.objects["Ennix_head"]
    head.shape_key_clear()
    head.modifiers.clear()
    body.select_set(True)
    head.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.join()
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    body.name = "Ennix_Skinning_Proxy"
    bpy.ops.export_scene.fbx(filepath=str(out), use_selection=True, object_types={"MESH"},
                             add_leaf_bones=False, bake_anim=False, axis_forward="-Y", axis_up="Z",
                             path_mode="COPY", embed_textures=True)
    print("The fitting dummy is ready; the original face remains safely upstairs, sir.")


if __name__ == "__main__":
    main()
