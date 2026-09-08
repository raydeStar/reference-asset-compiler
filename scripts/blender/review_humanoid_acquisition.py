"""Close-up evidence of acquired geometry only; never edits its vertices."""
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_turnaround import mesh_bounds, setup_world, add_key_lights, place_camera


def main():
    source, destination = map(Path, sys.argv[sys.argv.index("--") + 1:])
    if destination.exists():
        raise RuntimeError("Close-up evidence already exists; choose a new revision")
    destination.mkdir(parents=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.gltf(filepath=str(source.resolve()))
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    low, high = mesh_bounds(meshes)
    size = high - low
    center = (low + high) / 2
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 24
    scene.render.resolution_x = scene.render.resolution_y = 1024
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = -2
    setup_world()
    add_key_lights(center, size.z * .5)
    mat = bpy.data.materials.new("NeutralAcquisitionClay")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (.25, .29, .32, 1)
    bsdf.inputs["Roughness"].default_value = .8
    scene.view_layers[0].material_override = mat
    # These are framing ratios only. No mesh, pose or topology is modified.
    views = [
        ("face-front", Vector((center.x, center.y, low.z + size.z * .91)), size.z * .24, 0),
        ("face-three-quarter", Vector((center.x, center.y, low.z + size.z * .91)), size.z * .24, 40),
        ("hand-left", Vector((low.x + size.x * .065, center.y, low.z + size.z * .465)), size.z * .19, 0),
        ("hand-right", Vector((high.x - size.x * .065, center.y, low.z + size.z * .465)), size.z * .19, 0),
    ]
    for name, aim, extent, angle in views:
        place_camera(aim, extent, angle)
        scene.render.filepath = str((destination / (name + ".png")).resolve())
        bpy.ops.render.render(write_still=True)
    (destination / "framing.json").write_text(json.dumps({"source": str(source.resolve()),
        "bounds": [list(low), list(high)], "geometry_edited": False,
        "views": [row[0] for row in views]}, indent=2))
    print("ACQUISITION_CLOSEUPS_READY -- fingers receive their own cross-examination.")


if __name__ == "__main__":
    main()
