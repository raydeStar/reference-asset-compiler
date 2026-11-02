"""Mouth repair on the rigged Raider, written as a versioned derivative.

Mark found the speaking mouth weird: "the teeth aren't in place". Measured on the mouth-open shape:
  - MPFB refits the CC0 teeth to the face's helper teeth for each shape, and the helper's open-mouth shape bends
    the arches: the side teeth of both rows swing into the gap and the front teeth stay apart, so an open mouth
    shows side teeth round a dark hole.
  - The upper incisors' edges sat above the lip line, so the upper lip hid them whenever the mouth opened.

Here the teeth are rigid: the upper row stays with the skull and the lower row and tongue follow the chin as one
solid piece (the rigid motion that best fits the chin and lower lip in each face shape). Teeth and tongue drop so
the upper incisors' edges sit just under the lip line.

  $B -b <rigged.blend> --python fix_mouth.py -- <out_blend> <out_fbx>
"""
import bpy, bmesh, sys
import numpy as np
from mathutils import Matrix, Vector
a = sys.argv[sys.argv.index("--") + 1:]; out_blend, out_fbx = a[0], a[1]
sc = bpy.context.scene
face, teeth, tongue = (bpy.data.objects[n] for n in ("face", "teeth", "tongue"))
EDGE_UNDER_LIP = 0.003                           # upper incisor edge this far under the lip line
def world(o, key): M = o.matrix_world; return np.array([(M @ d.co)[:] for d in key.data])
def put(o, key, P):
    Mi = o.matrix_world.inverted()
    for d, p in zip(key.data, P): d.co = Mi @ Vector(p)
fk = face.data.shape_keys.key_blocks; F0 = world(face, fk[0])
# lip line: at the front midline, where the open-mouth shape's downward pull jumps (the upper lip and philtrum
# move little, the lower lip a lot); taken between the two front vertices either side of the largest jump
dz_open = world(face, fk["mouth-open"])[:, 2] - F0[:, 2]
mid = np.nonzero((np.abs(F0[:, 0]) < 0.006) & (F0[:, 1] < -0.105) & (np.abs(F0[:, 2] - 1.62) < 0.04))[0]
mid = mid[np.argsort(F0[mid, 2])]
j = int(np.argmax(dz_open[mid][1:] - dz_open[mid][:-1]))     # z ascending: the pull weakens most sharply here
lip_line = 0.5 * (F0[mid[j], 2] + F0[mid[j + 1], 2])
# teeth pieces: each tooth is its own piece; the gums are one piece holding both arches
bm = bmesh.new(); bm.from_mesh(teeth.data); bm.verts.ensure_lookup_table()
tk = teeth.data.shape_keys.key_blocks; T0 = world(teeth, tk[0])
comp = -np.ones(len(T0), int); n = 0
for v in bm.verts:
    if comp[v.index] >= 0: continue
    st = [v]; comp[v.index] = n
    while st:
        u = st.pop()
        for e in u.link_edges:
            w = e.other_vert(u)
            if comp[w.index] < 0: comp[w.index] = n; st.append(w)
    n += 1
bm.free()
sizes = np.bincount(comp); gum = int(np.argmax(sizes))
cz = np.array([T0[comp == c, 2].mean() for c in range(n)])
tooth = [c for c in range(n) if c != gum]
split = np.median(cz[tooth])
# each tooth's row comes from the original open-mouth refit, which drops the lower row and leaves the upper (by
# centre height alone, the long front teeth landed in the wrong row): split at the widest gap in that drop
T_open = world(teeth, tk["mouth-open"])
drop_c = {c: float((T0[comp == c, 2] - T_open[comp == c, 2]).mean()) for c in tooth}
order = sorted(tooth, key=lambda c: drop_c[c]); gaps = [drop_c[order[i + 1]] - drop_c[order[i]] for i in range(len(order) - 1)]
cut = int(np.argmax(gaps)) + 1
upper_c, lower_c = order[:cut], order[cut:]
print("MOUTH tooth drop in the original refit, mm: upper", round(max(drop_c[c] for c in upper_c) * 1000, 1),
      "max; lower", round(min(drop_c[c] for c in lower_c) * 1000, 1), "min")
front = sorted(upper_c, key=lambda c: T0[comp == c, 1].mean())[:4]          # the four most forward upper teeth
edge = min(T0[comp == c, 2].min() for c in front)
upper = np.isin(comp, upper_c) | ((comp == gum) & (T0[:, 2] >= split))
lower = ~upper
drop = (lip_line - EDGE_UNDER_LIP) - edge
# the gum piece joins the two arches at the back; those faces would stretch into strips as the jaw opens
bm = bmesh.new(); bm.from_mesh(teeth.data)
bridge = [f for f in bm.faces if len({bool(upper[v.index]) for v in f.verts}) > 1]
bmesh.ops.delete(bm, geom=bridge, context='FACES_ONLY'); bm.to_mesh(teeth.data); bm.free()
print("MOUTH gum faces joining the arches removed:", len(bridge))
print(f"MOUTH lip line {lip_line:.4f}, upper incisor edge {edge:.4f}, drop {drop * 1000:.1f} mm; "
      f"teeth upper {len(upper_c)} lower {len(lower_c)}")
shift = np.array([0, 0, drop])
def kabsch(A, B):   # rigid motion taking A onto B
    ca, cb = A.mean(0), B.mean(0); H = (A - ca).T @ (B - cb); U, _, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T)); R = Vt.T @ np.diag([1, 1, d]) @ U.T
    return R, cb - R @ ca
chin = (np.abs(F0[:, 0]) < 0.025) & (F0[:, 2] < lip_line - 0.003) & (F0[:, 2] > lip_line - 0.05) & (F0[:, 1] < -0.09)
Tg0 = world(tongue, tongue.data.shape_keys.key_blocks[0])
base_t = T0 + shift; base_g = Tg0 + shift
put(teeth, tk[0], base_t); put(tongue, tongue.data.shape_keys.key_blocks[0], base_g)
# MakeHuman's open-mouth shape also pulls the upper lip's edge down (about 1 cm at full open), which would bury the
# upper teeth; the upper row follows that edge down (never up) so the incisors keep showing just under it
uplip = (np.abs(F0[:, 0]) < 0.015) & (F0[:, 1] < -0.105) & (F0[:, 2] > lip_line) & (F0[:, 2] < lip_line + 0.006)
for o, base in ((teeth, base_t), (tongue, base_g)):
    for k in o.data.shape_keys.key_blocks[1:]:
        if k.name not in fk: put(o, k, base); continue
        R, t = kabsch(F0[chin], world(face, fk[k.name])[chin])
        moved = base @ R.T + t
        lip_dz = min(0.0, float((world(face, fk[k.name])[uplip, 2] - F0[uplip, 2]).mean()))
        P = moved if o is tongue else np.where(lower[:, None], moved, base + np.array([0, 0, lip_dz]))
        if o is teeth: print(f"JAW {k.name}: upper teeth follow the upper lip down {-lip_dz * 1000:.1f} mm")
        put(o, k, P)
        print(f"JAW {o.name}/{k.name}: lower jaw turns {np.degrees(np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1))):.1f} deg, "
              f"lowest point drops {(base[:, 2].min() - moved[:, 2].min()) * 1000:.1f} mm")
eyes = bpy.data.objects.get("eyes")   # the eyes carried a stray mouth-open refit; they stay put
if eyes and eyes.data.shape_keys:
    ek = eyes.data.shape_keys.key_blocks
    for k in ek[1:]:
        for d, b in zip(k.data, ek[0].data): d.co = b.co
bpy.ops.wm.save_as_mainfile(filepath=out_blend)
arm = next(o for o in sc.objects if o.type == 'ARMATURE')
for o in sc.objects: o.select_set(o.type in ('ARMATURE', 'MESH'))
bpy.context.view_layer.objects.active = arm
bpy.ops.export_scene.fbx(filepath=out_fbx, use_selection=True, object_types={'ARMATURE', 'MESH'}, apply_scale_options="FBX_SCALE_ALL",
                         axis_forward="-Y", axis_up="Z", global_scale=1.0, apply_unit_scale=True, bake_anim=False,
                         add_leaf_bones=False, primary_bone_axis="Y", secondary_bone_axis="X", mesh_smooth_type="FACE",
                         use_armature_deform_only=False, path_mode="COPY", embed_textures=True, use_mesh_modifiers=False)
print("MOUTH_OK")
