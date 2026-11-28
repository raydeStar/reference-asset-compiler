"""Straight-on orthographic face render for the landmark detector, plus the camera it used.

  scan: $B -b --factory-startup --python face_front.py -- scan <assembled.glb> <out.png>
  mh:   $B -b --python face_front.py -- mh <unused> <out.png>        (needs MPFB; saves <out>.blend)

Writes <out>.json: camera centre, ortho scale, resolution and view direction, so 2D landmarks can be traced
back onto the surface. The scan face renders as unlit paint, MakeHuman's as clay.
"""
import bpy
import sys
import json
import numpy as np
from mathutils import Vector
a = sys.argv[sys.argv.index("--") + 1:]
mode, src, out = a[0], a[1], a[2]
RES = 1024
if mode == "scan":
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=src)
    head = next(o for o in bpy.context.scene.objects if o.type == 'MESH' and o.name.startswith("raider_head"))
    for o in bpy.context.scene.objects:
        if o.type == 'MESH' and o is not head:
            o.hide_render = True
    for m in head.data.materials:
        nt = m.node_tree
        img = next((n for n in nt.nodes if n.type == 'TEX_IMAGE' and any(lk.to_socket.name == "Base Color" for lk in n.outputs[0].links)), None)
        em = nt.nodes.new("ShaderNodeEmission")
        outn = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL')
        nt.links.new(img.outputs[0], em.inputs[0])
        nt.links.new(em.outputs[0], outn.inputs[0])
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE'
    sc.view_settings.view_transform = 'Standard'
    w = bpy.data.worlds.new("w")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (1, 1, 1, 1)
else:
    from bl_ext.user_default.mpfb.services.humanservice import HumanService
    from bl_ext.user_default.mpfb.services.targetservice import TargetService
    macro = {"gender": 1.0, "age": 0.5, "muscle": 0.7, "weight": 0.5, "proportions": 0.5, "height": 0.5, "cupsize": 0.5,
             "firmness": 0.5, "race": {"asian": 0.0, "caucasian": 1.0, "african": 0.0}}
    head = HumanService.create_human(macro_detail_dict=macro)
    TargetService.bake_targets(head)
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_WORKBENCH'
    sh = sc.display.shading
    sh.light = 'STUDIO'
    sh.color_type = 'SINGLE'
    sh.single_color = (0.85, 0.7, 0.6)
    sh.show_cavity = True
    sc.world = bpy.data.worlds.new("w")
    sc.world.color = (1, 1, 1)
    bpy.ops.wm.save_as_mainfile(filepath=out[:-4] + ".blend")
dg = bpy.context.evaluated_depsgraph_get()
ev = head.evaluated_get(dg)
V = np.array([(head.matrix_world @ v.co)[:] for v in ev.data.vertices])
if mode == "mh":
    gi = head.vertex_groups["body"].index
    body = [v.index for v in head.data.vertices if any(g.group == gi and g.weight > 0.5 for g in v.groups)]
    V = V[body]
    top = V[:, 2].max()
    V = V[V[:, 2] > top - 0.28]   # the head, not the whole body
zr = np.ptp(V[:, 2])
top = V[:, 2].max()
face = V[V[:, 2] > top - 0.85 * zr] if mode == "scan" else V
c = Vector(((face[:, 0].min() + face[:, 0].max()) / 2, 0, top - 0.42 * (zr if mode == "mh" else min(zr, 0.30 * 1.0 if zr > 0.6 else zr))))
if mode == "scan":
    hz = V[V[:, 2] > top - 0.55 * zr]
    c = Vector(((hz[:, 0].min() + hz[:, 0].max()) / 2, 0, top - 0.34 * zr))
size = float(np.ptp(V[V[:, 2] > c.z - 0.3 * zr][:, 0])) * 1.45 if mode == "scan" else 0.30
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.type = 'ORTHO'
cam.data.ortho_scale = size
d = Vector((0, -1, 0))
cam.location = c + d * 5
cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
sc.render.resolution_x = sc.render.resolution_y = RES
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
json.dump({"centre": list(c), "ortho_scale": size, "resolution": RES, "view": [0, 1, 0]}, open(out[:-4] + ".json", "w"), indent=2)
print("FACE_FRONT", mode, out, round(size, 3))
