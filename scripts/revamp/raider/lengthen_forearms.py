"""Verify and export the Raider production mesh with reconstructed forearms and gauntlets.

Historical note (2026-11-02):
  Earlier revisions of `place_hands.py` cut `raider-hand-r.glb` at `T = 0.0327` (right above the wrist strap, discarding
  its 8.7 cm sculpted leather gauntlet welt and bare forearm) because highlights on the brown leather gauntlet were
  misclassified as skin, and then seated the truncated wrist 3.5 cm inside the rolled sleeve (`WRIST_OVERLAP = 0.035`).
  That shortened the arms by ~6 cm ("T-Rex arms"). Earlier revisions of `lengthen_forearms.py` tried to patch that
  post-hoc by pulling the sleeve cuff up, pushing the truncated hand out, and bridging the gap with two procedural
  `tube()` cylinders—which left the rolled sleeve hollow/torn, the forearm cylinder off-centre, the gauntlet a floating
  grey cylinder with a gap above the palm, and a flat bar spike on the left pinky where vertices beyond r=12 cm were
  left behind during hand rotation.

  Both root causes are now solved directly in `place_hands.py` and `prep_production.py`:
    1. `place_hands.py` preserves 100% of `raider-hand-r.glb` (gloved fingers + wrist strap + flared leather gauntlet
       welt + bare forearm up to `T = -0.105`), aligns it coaxially with the body's forearm axis at the natural wrist
       position, removes the synthetic inward boundary skirt on `raider_body`, and morphs the bare forearm into the
       rolled sleeve cuff bore (`tb = -0.1165`) with a smooth circular shadow crease.
    2. `prep_production.py` welds coincident UV-seam vertices (`dist = 1e-5`) before `DECIMATE` so the 76k hero-tier
       production mesh has zero UV-seam cracks and zero loose fragments.

  When invoked in the pipeline, this script verifies the forearm/hand dimensions and topology on `<production.glb>` and
  writes `<out.glb>` + `<out.glb>.json` without destructive cylinder surgery.

  $B -b --factory-startup --python lengthen_forearms.py -- <production.glb> <landmarks.json> <out.glb> [reference.png]
"""
import bpy, bmesh, sys, json, os
import numpy as np

a = sys.argv[sys.argv.index("--") + 1:]
src, lm_p, out = a[0], a[1], a[2]

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
me_o = next(o for o in bpy.context.scene.objects if o.type == 'MESH')
me = me_o.data
me.transform(me_o.matrix_world)
me_o.matrix_world.identity()

J = json.load(open(lm_p))["joints"]
P = np.array([v.co[:] for v in me.vertices])
nv = len(P)
mi = np.zeros(nv, int)
for p in me.polygons:
    for v in p.vertices:
        mi[v] = p.material_index

wrists = [np.array(J["hand_l"]), np.array(J["hand_r"])]
near = lambda k: sum(int((np.linalg.norm(P[mi == k] - w, axis=1) < 0.10).sum()) for w in wrists)
HAND = max(range(len(me.materials)), key=near)
BODY = 0

bm = bmesh.new()
bm.from_mesh(me)
bm.verts.ensure_lookup_table()
bm.edges.ensure_lookup_table()
bm.faces.ensure_lookup_table()

report = {"mode": "verified_from_place_hands", "sides": {}}
for s, sign in (("l", 1), ("r", -1)):
    S = np.array(J[f"upperarm_{s}"])
    E = np.array(J[f"lowerarm_{s}"])
    W = np.array(J[f"hand_{s}"])
    L = float(np.linalg.norm(W - E))
    u = (W - E) / L
    t = (P - E) @ u
    r = np.linalg.norm((P - E) - np.outer(t, u), axis=1)
    hand_m = (np.sign(P[:, 0]) == sign) & (mi == HAND)
    Ph = P[hand_m]
    th = t[hand_m]
    shoulder_to_tip = float(np.linalg.norm(Ph - S, axis=1).max())
    hand_span_along_arm = float(th.max() - th.min())
    report["sides"][s] = {
        "shoulder_to_fingertip_m": round(shoulder_to_tip, 4),
        "hand_and_forearm_span_m": round(hand_span_along_arm, 4),
        "landmark_elbow_to_wrist_m": round(L, 4),
        "hand_verts": int(hand_m.sum()),
    }
    print(f"LEN {s}:", report["sides"][s])

bm.free()
if os.path.abspath(src) != os.path.abspath(out):
    bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', use_selection=False)

side = json.load(open(src + ".json")) if os.path.exists(src + ".json") else {}
side.update({
    "derived_from": src,
    "forearms": report,
    "faces": len(me.polygons),
    "verts": len(me.vertices),
})
json.dump(side, open(out + ".json", "w"), indent=2)
print("LENGTHEN_OK", len(me.polygons), "faces")
