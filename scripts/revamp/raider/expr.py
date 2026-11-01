import bpy, sys, os, math
from mathutils import Vector, Euler
out = sys.argv[sys.argv.index("--") + 1:][0]; sc = bpy.context.scene
for o in sc.objects:
    if o.type == 'MESH': o.hide_render = o.name not in ("head", "eye_l", "eye_r", "hair", "jacket", "strap", "plate")
sh = sc.display.shading; sc.render.engine = 'BLENDER_WORKBENCH'; sh.light = 'STUDIO'; sh.color_type = 'MATERIAL'; sh.show_cavity = True
sh.show_object_outline = False
cam = bpy.data.objects.get("cam") or bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
if cam.name not in sc.collection.objects: sc.collection.objects.link(cam)
sc.camera = cam; cam.data.type = 'ORTHO'; cam.data.ortho_scale = 0.24; sc.render.resolution_x = sc.render.resolution_y = 500
d = Vector((0, -1, 0)); d.rotate(Euler((0, 0, math.radians(20)))); c = Vector((0, -0.05, 0.835))
cam.location = c + d * 5; cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
hk = bpy.data.objects["head"].data.shape_keys.key_blocks
EXPR = {"rest": {}, "open": {"mouth-open": 1.0}, "smile": {"mouth-corner-puller": 1.0, "eye-left-slit": 0.3, "eye-right-slit": 0.3},
        "oo": {"mouth-pursing": 1.0, "mouth-protusion": 0.6}, "blink": {"eye-left-closure": 1.0, "eye-right-closure": 1.0},
        "brows": {"eyebrows-left-inner-up": 1.0, "eyebrows-right-inner-up": 1.0, "mouth-depression": 0.6}}
for nm, ws in EXPR.items():
    for kb in hk[1:]: kb.value = ws.get(kb.name, 0.0)
    sc.render.filepath = os.path.join(out, f"head-expr-{nm}.png"); bpy.ops.render.render(write_still=True)
print("EXPR_DONE")
