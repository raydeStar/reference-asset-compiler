import bpy, sys, math, numpy as np
from mathutils import Vector, Euler
a = sys.argv[sys.argv.index("--") + 1:]; src, out = a[0], a[1]
bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.gltf(filepath=src)
obs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
V = np.concatenate([np.array([(o.matrix_world @ v.co)[:] for v in o.data.vertices]) for o in obs])
for o in obs: o.data.materials.clear()
print("BBOX", V.min(0).round(3), V.max(0).round(3))
sc = bpy.context.scene; sc.render.engine = 'BLENDER_WORKBENCH'; sh = sc.display.shading
sh.light = 'MATCAP'; sh.color_type = 'SINGLE'; sh.single_color = (0.8, 0.8, 0.8); sh.show_cavity = True
sc.render.resolution_x = sc.render.resolution_y = 700
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); sc.collection.objects.link(cam); sc.camera = cam; cam.data.type = 'ORTHO'
ext = V.max(0) - V.min(0); ctr = (V.max(0) + V.min(0)) / 2
# glTF from hy3d: y up in file -> z up in Blender, front is -y
cam.data.ortho_scale = float(max(ext[0], ext[2])) * 1.05
for nm, ang in (("front", 0), ("three-quarter", 35), ("side", 90), ("back", 180)):
    d = Vector((0, -1, 0)); d.rotate(Euler((0, 0, math.radians(ang))))
    cam.location = Vector(ctr) + d * 5; cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = f"{out}-{nm}.png"; bpy.ops.render.render(write_still=True)
# face close-up: top 45% of the bounds
cam.data.ortho_scale = float(ext[2]) * 0.42; fc = Vector((ctr[0], ctr[1], V[:, 2].max() - ext[2] * 0.33))
for nm, ang in (("face-front", 0), ("face-34", 35)):
    d = Vector((0, -1, 0)); d.rotate(Euler((0, 0, math.radians(ang))))
    cam.location = fc + d * 5; cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = f"{out}-{nm}.png"; bpy.ops.render.render(write_still=True)
