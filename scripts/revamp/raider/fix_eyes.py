"""Seat the eyeballs behind the eyelids: radius from the lid opening, front of the eye level with the lid rim."""
import bpy
import bmesh
import sys
import os
import numpy as np
from mathutils import Vector
sys.stdout.reconfigure(line_buffering=True)
out = sys.argv[sys.argv.index("--") + 1:][0]
head = bpy.data.objects["head"]
me = head.data
CO = np.array([v.co[:] for v in me.vertices])
bm = bmesh.new()
bm.from_mesh(me)
# MakeHuman's lids close over the socket (no hole), so seat a real-size eyeball by depth: its front sits
# level with the skin just inside the lid opening
SCALE = 1.1939
R = 0.0120 * SCALE
for side in ("l", "r"):
    eo = bpy.data.objects[f"eye_{side}"]
    c = np.array(eo.location)
    d = np.linalg.norm(CO[:, [0, 2]] - c[[0, 2]], axis=1)
    inner = CO[d < 0.008]
    front_y = float(np.percentile(inner[:, 1], 30)) + 0.001
    centre = np.array([c[0], front_y + R, c[2]])
    em = eo.data
    bb = bmesh.new()
    bmesh.ops.create_uvsphere(bb, u_segments=32, v_segments=20, radius=R)
    for f in bb.faces:
        f.smooth = True
        f.material_index = 1 if f.calc_center_median().y < -R * 0.82 else 0
    bb.to_mesh(em)
    bb.free()
    eo.location = Vector(centre)
    print("EYE", side, "r", round(R, 4), "front_y", round(front_y, 4), "centre", centre.round(4))
w = bpy.context.scene.world or bpy.data.worlds.new("w")
bpy.context.scene.world = w
w.color = (0.3, 0.3, 0.32)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "raider-head-v1.blend"))
print("EYES_DONE")
