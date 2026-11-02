"""Replace the template finger joints in a humanoid landmark file with joints measured from the hand mesh.

derive_humanoid_landmarks.py transplants Manny's finger layout onto the measured forearm. That is fine for a
mitten, and wrong for a hand whose fingers really are modeled: on CH-03 Raider's acquired gloves (2026-11-01)
the template chains missed the fingers and a fist crumpled them into shards. Here each hand is measured:

* the hand is the mesh beyond the wrist joint, toward hand_end;
* along the wrist-to-hand_end axis, the lowest threshold at which four pieces stand apart gives the fingers
  down to their webs, and the piece that first breaks away from the palm near the wrist is the thumb; the
  fingers are ordered index to pinky away from the thumb;
* along each finger's own centreline the knuckle sits a third of the free length behind the web, and the middle
  and last joints at 45% and 75% from knuckle to tip; metacarpals start just past the wrist.

Bones the measurement cannot place keep the template. The output is a new landmark file bound to the same
mesh; pass it to run_rig_candidate.ps1 -Landmarks.

Usage:
  blender -b --factory-startup --python measure_finger_landmarks.py -- <mesh.glb|fbx> <landmarks.json> <out.json>
"""
import sys, json, hashlib
import numpy as np
import bpy

a = [x for x in sys.argv[sys.argv.index("--") + 1:] if not x.startswith("--")]; mesh_p, lm_p, out_p = a
lm = json.load(open(lm_p)); J = {k: np.array(v, float) for k, v in lm["joints"].items()}
bpy.ops.wm.read_factory_settings(use_empty=True)
if mesh_p.lower().endswith((".glb", ".gltf")): bpy.ops.import_scene.gltf(filepath=mesh_p)
else: bpy.ops.import_scene.fbx(filepath=mesh_p)
V, E = [], []; off = 0
for o in bpy.context.scene.objects:
    if o.type != 'MESH': continue
    me = o.data; co = np.array([(o.matrix_world @ v.co)[:] for v in me.vertices])
    V.append(co); E.append(np.array([e.vertices[:] for e in me.edges], np.int64) + off); off += len(co)
V = np.concatenate(V); E = np.concatenate(E)
# painted meshes are split at UV seams; weld coincident vertices so connectivity is the surface's own
_, canon = np.unique(np.round(V, 5), axis=0, return_inverse=True); canon = canon.ravel()
first = np.full(canon.max() + 1, -1, np.int64)
for i, c in enumerate(canon):
    if first[c] < 0: first[c] = i
E = first[canon[E]]; E = E[E[:, 0] != E[:, 1]]

def components(mask):
    idx = np.nonzero(mask)[0]; remap = -np.ones(len(V), np.int64); remap[idx] = np.arange(len(idx))
    ee = E[mask[E[:, 0]] & mask[E[:, 1]]]; parent = np.arange(len(idx))
    def find(x):
        while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for u, w in remap[ee]:
        ru, rw = find(u), find(w)
        if ru != rw: parent[ru] = rw
    roots = np.array([find(i) for i in range(len(idx))])
    return [idx[roots == r] for r in np.unique(roots)]

report = {}
for side in ("l", "r"):
    W, HE = J["hand_" + side], J["hand_end_" + side]; ax = (HE - W) / np.linalg.norm(HE - W)
    rel = V - W; t = rel @ ax; radial = np.linalg.norm(rel - np.outer(t, ax), axis=1)
    hand = (t > -0.01) & (t < 0.30) & (radial < 0.13) & (np.linalg.norm(rel, axis=1) < 0.30)
    # only the hand's own mesh: other pieces near the wrist (a cuff strap, a sleeve edge) are not fingers
    base = max(components(hand), key=len); hand = np.zeros(len(V), bool); hand[base] = True
    L = t[hand].max()
    # Fingers: the lowest threshold at which four pieces stand apart, i.e. each finger down to its web.
    # Thumb: it branches off near the wrist, so it is the piece that first breaks away from the palm at a low
    # threshold (it is gone again by the time the fingers part). Scanning from the tip inward kept only
    # fingertips; asking for five pieces at once never happens on a real hand.
    def pieces(f):
        cs = sorted([c for c in components(hand & (t > f * L)) if len(c) > 40], key=len, reverse=True)
        if "--debug" in sys.argv: print("DBG", side, round(float(f), 2), [len(c) for c in cs][:6])
        return cs
    fingers = thumb_piece = None; f_fingers = f_thumb = None
    for f in np.linspace(0.02, 0.9, 45):
        cs = pieces(f)
        if thumb_piece is None and len(cs) >= 2: thumb_piece, f_thumb = cs[1], f
        if len(cs) >= 4: fingers, f_fingers = cs[:4], f; break
    if fingers is None or thumb_piece is None:
        report[side] = "fingers not separable; template kept"; continue
    def chain(c, back):
        P = V[c]; tip = P[np.argmax(np.linalg.norm(P - W, axis=1))]
        tt = (P - W) @ ax; web = P[tt < np.percentile(tt, 8)].mean(0)
        d = (tip - web) / np.linalg.norm(tip - web); F = np.linalg.norm(tip - web)
        knuckle = web - d * back * F
        def at(fr):
            q = knuckle + (tip - knuckle) * fr; s_ = P[np.abs((P - q) @ d) < 0.006]
            return s_.mean(0) if len(s_) > 5 else q
        return {"01": knuckle, "02": at(0.45), "03": at(0.75), "tip": tip, "dir": d}
    # a finger's knuckle sits about a third of its free length behind the web
    chains = [chain(c, 0.35) for c in fingers]
    th = chain(thumb_piece, 0.25)
    # Order across the palm. The width direction comes from the four fingers' mid points themselves (the thumb
    # points out of the palm, so "toward the thumb" is mostly depth); the thumb only picks which end is index.
    mids = np.array([chains[i]["02"] for i in range(4)]); mc = mids.mean(0)
    wdir = np.linalg.eigh(np.cov((mids - mc).T))[1][:, -1]
    if (th["01"] - mc) @ wdir < 0: wdir = -wdir
    order = sorted(range(4), key=lambda i: -float((mids[i] - mc) @ wdir))
    names = dict(zip(order, ("index", "middle", "ring", "pinky")))
    for i, n in names.items():
        ch = chains[i]
        J[f"{n}_metacarpal_{side}"] = W + (ch["01"] - W) * 0.15
        J[f"{n}_01_{side}"] = ch["01"]; J[f"{n}_02_{side}"] = ch["02"]; J[f"{n}_03_{side}"] = ch["03"]
        J[f"{n}_tip_{side}"] = ch["tip"]
    # the thumb's first bone starts near the wrist, a third of the way from the wrist to its knuckle
    J["thumb_01_" + side] = W + (th["01"] - W) * 0.35
    J["thumb_02_" + side] = th["01"]; J["thumb_03_" + side] = th["03"]; J["thumb_tip_" + side] = th["tip"]
    f = f_fingers
    lean = {names[i]: round(float(np.degrees(np.arccos(np.clip(chains[i]["dir"] @ ax, -1, 1)))), 1) for i in range(4)}
    lean["thumb"] = round(float(np.degrees(np.arccos(np.clip(th["dir"] @ ax, -1, 1)))), 1)
    lengths = {names[i]: round(float(np.linalg.norm(chains[i]["tip"] - chains[i]["01"])), 3) for i in range(4)}
    lengths["thumb"] = round(float(np.linalg.norm(th["tip"] - th["01"])), 3)
    report[side] = {"finger_threshold": float(f_fingers), "thumb_threshold": float(f_thumb), "lean_deg": lean,
                    "finger_lengths_m": lengths}
lm["joints"] = {k: v.tolist() for k, v in J.items()}
lm["method"] = lm.get("method", "") + " Finger joints measured from the hand mesh by measure_finger_landmarks.py."
lm["finger_measurement"] = report
lm["source_landmarks_sha256"] = hashlib.sha256(open(lm_p, "rb").read()).hexdigest()
lm["overlay_sha256"] = None
json.dump(lm, open(out_p, "w"), indent=2)
print("FINGERS", json.dumps(report))
