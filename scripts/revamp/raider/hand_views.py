"""Close-ups of both hands on the assembled character, painted (EEVEE) and as clay (matcap), from the back of the
hand, the palm side, the thumb side and below, so finger separation and paint can be judged before rigging."""
import bpy, sys, math
import numpy as np
from mathutils import Vector
a = sys.argv[sys.argv.index("--") + 1:]; src, out = a[0], a[1]
bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.gltf(filepath=src)
sc = bpy.context.scene
obs = [o for o in sc.objects if o.type == 'MESH']
V = np.concatenate([np.array([(o.matrix_world @ v.co)[:] for v in o.data.vertices]) for o in obs])
zmin, zmax = V[:, 2].min(), V[:, 2].max(); H = zmax - zmin
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.type = 'ORTHO'; cam.data.ortho_scale = 0.13 * H
sc.render.resolution_x = sc.render.resolution_y = 600
sun = bpy.data.objects.new("s", bpy.data.lights.new("s", 'SUN')); sun.data.energy = 3; sc.collection.objects.link(sun)
sun.rotation_euler = (math.radians(50), 0, math.radians(-30))
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True; w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.3, 0.3, 0.32, 1)
sc.view_settings.view_transform = 'Standard'
for side, sgn in (("right", -1), ("left", 1)):
    # the hand is the far end of the arm on that side: the lowest-z cluster beyond the hip line
    arm = V[(np.sign(V[:, 0]) == sgn) & (np.abs(V[:, 0]) > 0.75 * np.abs(V[:, 0]).max())]
    c = Vector(arm.mean(0).tolist())
    out_dir = Vector((sgn, 0, 0))
    views = {"back": Vector((0, 1, 0)), "palm": Vector((0, -1, 0)), "thumb": Vector((-sgn * 0.0, -1, 0)).normalized(),
             "outer": out_dir, "below": Vector((0, 0, -1))}
    views = {"front": Vector((0, -1, 0)), "back": Vector((0, 1, 0)), "outer": out_dir, "inner": -out_dir, "below": Vector((0.001, 0, -1))}
    for mode in ("paint", "clay"):
        if mode == "paint":
            sc.render.engine = 'BLENDER_EEVEE'
        else:
            sc.render.engine = 'BLENDER_WORKBENCH'; sh = sc.display.shading
            sh.light = 'MATCAP'; sh.color_type = 'SINGLE'; sh.single_color = (0.8, 0.8, 0.8); sh.show_cavity = True
        for nm, d in views.items():
            cam.location = c + d.normalized() * 3
            cam.rotation_euler = (-d).to_track_quat('-Z', 'Y' if abs(d.z) < 0.9 else 'X').to_euler()
            sc.render.filepath = f"{out}/hand-{side}-{mode}-{nm}.png"; bpy.ops.render.render(write_still=True)
    print("HAND", side, [round(x, 3) for x in c])
