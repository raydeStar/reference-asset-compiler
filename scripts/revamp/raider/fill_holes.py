"""Close small holes in the Raider's body shell on the production mesh.

The head placement left a slit about 16 cm wide in the jacket's back below the collar (the face's neck showed
through it, a skin-coloured crescent). Open boundary loops of the body material that are short (under MAX_LOOP
metres round) and lie inside the given box are filled; each new face takes UVs from an affine fit of the loop's
own UVs to its positions on the loop's best-fit plane, so it samples the surrounding paint. Within RIM of a filled
loop, texels the painter shaded as the slit's dark rim, or painted as skin, take the jacket's local colour.

  $B -b --factory-startup --python fill_holes.py -- <in.glb> <out.glb>
"""
import bpy
import bmesh
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from skin_tone import hsv  # noqa: E402
from uv_raster import fill_polygon  # noqa: E402

a = sys.argv[sys.argv.index("--") + 1:]
src, out = a[0], a[1]
MAX_LOOP = 0.45
RIM = 0.06          # the painter shaded the slit's rim and a shadow arc; faces this close to a filled loop are repainted
BOX = ((-0.10, 0.10, 1.40), (0.10, 0.25, 1.55))     # the centre of the back below the collar (m; -Y is front)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
ob = next(o for o in bpy.context.scene.objects if o.type == 'MESH')
me = ob.data
me.transform(ob.matrix_world)
ob.matrix_world.identity()
bm = bmesh.new()
bm.from_mesh(me)
uvl = bm.loops.layers.uv.active
boundary = [e for e in bm.edges if e.is_boundary and e.link_faces[0].material_index == 0]
seen, loops = set(), []
for e in boundary:
    if e.index in seen:
        continue
    loop, stack = [], [e]
    seen.add(e.index)
    while stack:
        x = stack.pop()
        loop.append(x)
        for v in x.verts:
            for y in v.link_edges:
                if y.is_boundary and y.index not in seen and y.link_faces[0].material_index == 0:
                    seen.add(y.index)
                    stack.append(y)
    loops.append(loop)
lo, hi = np.array(BOX[0]), np.array(BOX[1])
filled, rim_faces, patch_faces = [], set(), set()
for loop in loops:
    vs = list({v for e in loop for v in e.verts})
    P = np.array([v.co[:] for v in vs])
    length = sum(e.calc_length() for e in loop)
    c = P.mean(0)
    if length > MAX_LOOP or not (np.all(c > lo) and np.all(c < hi)):
        continue
    # every loop vertex's UV, from the boundary face's corner at that vertex
    uv = np.array([next(lp[uvl].uv[:] for f in v.link_faces for lp in f.loops if lp.vert is v) for v in vs])
    _, _, Vt = np.linalg.svd(P - c)
    plane = (P - c) @ Vt[:2].T
    A = np.c_[plane, np.ones(len(vs))]
    coef, *_ = np.linalg.lstsq(A, uv, rcond=None)
    res = bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=loop)
    new_faces = [g for g in res["geom"] if isinstance(g, bmesh.types.BMFace)]
    for f in new_faces:
        f.material_index = 0
        f.smooth = True
        for lp in f.loops:
            q = (np.array(lp.vert.co[:]) - c) @ Vt[:2].T
            lp[uvl].uv = tuple(np.r_[q, 1.0] @ coef)
    # face the patch the way the shell around it faces (only the new faces are touched)
    new_set = set(new_faces)
    around = [f for v in vs for f in v.link_faces if f not in new_set]
    if around:
        shell_n = np.mean(np.array([tuple(f.normal) for f in around], float), axis=0)
    else:                       # nothing around it: face away from the body's vertical axis
        shell_n = np.array([c[0], c[1], 0.0])
    for f in new_faces:
        f.normal_update()
        if float(np.dot(np.array(tuple(f.normal), float), shell_n)) < 0:
            f.normal_flip()
    patch_faces |= set(new_faces)
    rim_faces |= {f for f in bm.faces if f.material_index == 0 and
                  np.min(np.linalg.norm(P - np.array(f.calc_center_median()[:]), axis=1)) < RIM}
    filled.append({"centre": c.round(3).tolist(), "loop_m": round(length, 3), "verts": len(vs), "faces": len(new_faces)})
    print("FILLED", filled[-1])
# the rim: texels much darker than the surrounding jacket (the painted shadow of the slit) or skin-coloured (the neck
# painted through it) take the jacket's local colour
node = next(n for n in me.materials[0].node_tree.nodes if n.type == 'TEX_IMAGE' and n.image
            and any(lk.to_socket.name == "Base Color" for lk in n.outputs[0].links))
W, H = node.image.size
px = np.empty(W * H * 4, np.float32)
node.image.pixels.foreach_get(px)
px = px.reshape(H, W, 4)
rim = np.zeros((H, W), bool)
rim_faces = {f for f in rim_faces if f.is_valid}      # a later fill can replace faces an earlier loop collected
for f in rim_faces:
    m = np.zeros((H, W), bool)
    fill_polygon(m, [(lp[uvl].uv[0] * W, lp[uvl].uv[1] * H) for lp in f.loops])
    if not m.any():
        continue
    if f not in patch_faces:
        # jacket faces and the slit's near-black painted shadow only: straps, plates and pouches round it (leather
        # is brighter than 0.15) keep their paint
        fh, fs, fv = hsv(px[m][:, :3])
        teal = ((fh > 150) & (fh < 230) & (fs > 0.25)).mean()
        if not (teal > 0.5 or (fv < 0.15).mean() > 0.5):
            continue
    rim |= m
repainted = 0
if rim.any():
    rgb = px[rim][:, :3]
    h, sat, val = hsv(rgb)
    teal = (h > 150) & (h < 230) & (sat > 0.25)
    jacket = np.median(rgb[teal], axis=0) if teal.any() else np.median(rgb, axis=0)
    # inside these jacket faces anything not teal is the painted slit: its shadow arc, its grey rim, the skin seen
    # through it
    bad = ~teal
    rgb[bad] = jacket
    px[rim, :3] = rgb
    repainted = int(bad.sum())
    img = bpy.data.images.new(node.image.name + "-rim", W, H, alpha=False)
    img.pixels.foreach_set(px.ravel())
    path = f"{os.path.splitext(out)[0]}-{node.image.name}-rim.png"
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    node.image = bpy.data.images.load(path)      # a loaded file is what the exporter embeds
print("RIM faces", len(rim_faces), "texels repainted", repainted)
bm.to_mesh(me)
bm.free()
bpy.ops.export_scene.gltf(filepath=out, export_format='GLB')
side = json.load(open(src + ".json")) if os.path.exists(src + ".json") else {}
side.update({"holes_filled": filled})
json.dump(side, open(out + ".json", "w"), indent=2)
print("FILL_HOLES_OK", len(filled))
