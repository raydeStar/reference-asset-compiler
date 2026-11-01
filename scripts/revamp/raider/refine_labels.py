"""Clean the Raider's part labels on the dense acquired mesh: head/collar regrowth along creases,
belt band round the back, knee-pad cap, small-island cleanup. Writes parts-v2/face-labels.npy."""
import bpy, sys, json, math, heapq
from collections import deque
import numpy as np
sys.stdout.reconfigure(line_buffering=True)
a = sys.argv[sys.argv.index("--") + 1:]
src, labp, names, out = a[0], a[1], json.load(open(a[2])), a[3]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
ob = next(o for o in bpy.context.scene.objects if o.type == 'MESH')
me = ob.data; me.transform(ob.matrix_world)
V = np.array([v.co[:] for v in me.vertices]); F = np.array([p.vertices[:] for p in me.polygons], np.int64)
nF = len(F); C = V[F].mean(1); N = np.array([p.normal[:] for p in me.polygons])
L = np.load(labp).astype(np.int32); L0 = L.copy(); ID = {n: i for i, n in enumerate(names)}
FRONT = np.array([0.0, -1.0, 0.0])

# face adjacency over shared edges (CSR)
E = np.sort(F[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2), 1); key = E[:, 0] * len(V) + E[:, 1]
fid = np.repeat(np.arange(nF), 3); o = np.argsort(key, kind="stable"); ks, fs = key[o], fid[o]
same = ks[1:] == ks[:-1]; pa, pb = fs[:-1][same], fs[1:][same]
rows = np.concatenate([pa, pb]); cols = np.concatenate([pb, pa]); o = np.argsort(rows, kind="stable")
cols = cols[o]; indptr = np.concatenate([[0], np.cumsum(np.bincount(rows, minlength=nF))])
nbr = lambda f: cols[indptr[f]:indptr[f + 1]]
print("ADJ", nF, len(pa))

def grow(region, seeds, allow=None):
    """Crease-aware multi-source growth inside region; concave creases cost 25x. seeds: {face: label}."""
    dist = {f: 0.0 for f in seeds}; heap = [(0.0, f) for f in seeds]; lab = dict(seeds); heapq.heapify(heap)
    while heap:
        d, f = heapq.heappop(heap)
        if d > dist[f]: continue
        for g in nbr(f):
            if not region[g]: continue
            if allow is not None and not allow(lab[f], g): continue
            cosang = min(1.0, max(-1.0, float(N[f] @ N[g]))); ang = math.acos(cosang)
            dv = C[g] - C[f]; concave = float(dv @ N[f]) > 0
            nd = d + float(np.linalg.norm(dv)) * (1.0 + (25.0 * ang if concave else 2.0 * ang))
            if nd < dist.get(g, np.inf): dist[g] = nd; lab[g] = lab[f]; heapq.heappush(heap, (nd, g))
    return lab

# 1. head and collar: relabel hair/face/beard/skin/jacket above the shoulders by growth from sure seeds
phi = np.degrees(np.arctan2(C[:, 0], -(C[:, 1] + 0.03)))
headish = (C[:, 2] > 0.66) & (np.abs(C[:, 0]) < 0.14)
soft = np.isin(L, [ID[n] for n in ("hair", "face", "beard", "skin", "jacket")])
region = headish & soft
seeds = {}
for f in np.nonzero(region & (C[:, 2] > 0.95))[0]: seeds[f] = ID["hair"]
for f in np.nonzero(region & (np.abs(phi) > 150) & (C[:, 2] > 0.86))[0]: seeds[f] = ID["hair"]
for f in np.nonzero(region & (np.abs(phi) < 70) & (C[:, 2] > 0.80) & (C[:, 2] < 0.88) & (N @ FRONT > 0.2) & (L == ID["face"]))[0]: seeds[f] = ID["face"]
for f in np.nonzero(region & (L == ID["beard"]) & (N @ FRONT > 0.4))[0]: seeds[f] = ID["beard"]
for f in np.nonzero(region & (C[:, 2] < 0.70) & (L == ID["jacket"]))[0]: seeds[f] = ID["jacket"]
# the beard covers jaw, chin and moustache, rising toward the sideburns; never the nose or cheekbones
beard_top = lambda p: 0.795 if p < 40 else 0.795 + 0.035 * min(1.0, (p - 40) / 45)
beard_ok = lambda l, g: l != ID["beard"] or (C[g, 2] < beard_top(abs(phi[g])) and abs(phi[g]) < 95)
lab = grow(region, seeds, beard_ok)
for f, l in lab.items(): L[f] = l
L[region & (L == ID["skin"])] = ID["face"]
print("HEAD regrown", int((L != L0)[region].sum()), "of", int(region.sum()))

# 2. belt band: the strip behind the pouches runs right round the waist. Band faces that touch the
# belt, buckle or pouches become belt; band pieces on the arms touch none of them and stay.
lo, hi = 0.206, 0.266
band = (C[:, 2] > lo) & (C[:, 2] < hi) & (np.abs(C[:, 0]) < 0.33) & np.isin(L, [ID["jacket"], ID["trousers"]])
gear = np.isin(L, [ID["belt"], ID["buckle"], ID["pouch"]])
seen = np.zeros(nF, bool); nb_ = 0
for s0 in np.nonzero(band)[0]:
    if seen[s0]: continue
    piece = [s0]; seen[s0] = True; q = [s0]; touch = False
    while q:
        f = q.pop()
        for g in nbr(f):
            if gear[g]: touch = True
            if band[g] and not seen[g]: seen[g] = True; piece.append(g); q.append(g)
    if touch and len(piece) > 30: L[piece] = ID["belt"]; nb_ += len(piece)
print("BELT band added", nb_)

# 3. knee pads end at the top of the pad
kp = (L == ID["kneepad"]) & (C[:, 2] > -0.25); L[kp] = ID["trousers"]; print("KNEEPAD capped", int(kp.sum()))

# 3b. pouches: the boxes standing proud of the belt are pouches all round; pouch spill above the belt is jacket
tphi = np.degrees(np.arctan2(C[:, 0], -(C[:, 1] - 0.01))); rad = np.hypot(C[:, 0], C[:, 1] - 0.01)
bins = np.clip(((tphi + 180) // 15).astype(int), 0, 23); r_belt = np.full(24, np.nan)
for b in range(24):
    m = (L == ID["belt"]) & (bins == b)
    if m.sum() > 20: r_belt[b] = np.median(rad[m])
ok = ~np.isnan(r_belt); r_belt = np.interp(np.arange(24), np.nonzero(ok)[0], r_belt[ok], period=24)
proud = (C[:, 2] > 0.13) & (C[:, 2] < 0.31) & (np.abs(C[:, 0]) < 0.33) & (rad > r_belt[bins] + 0.012) \
        & np.isin(L, [ID["jacket"], ID["belt"]])
L[proud] = ID["pouch"]; spill = (L == ID["pouch"]) & (C[:, 2] > 0.315); L[spill] = ID["jacket"]
print("POUCH proud", int(proud.sum()), "spill", int(spill.sum()))
# 3c. knee pads sit on the front of each knee, not round the outside of the thigh
for side in (-1, 1):
    leg = (np.sign(C[:, 0]) == side) & (C[:, 2] > -0.45) & (C[:, 2] < -0.18) & np.isin(L, [ID["trousers"], ID["kneepad"]])
    cx, cy = C[leg, 0].mean(), C[leg, 1].mean()
    lphi = np.degrees(np.arctan2(C[:, 0] - cx, -(C[:, 1] - cy)))
    wrap = leg & (L == ID["kneepad"]) & (np.abs(lphi) > 60); L[wrap] = ID["trousers"]
    print("KNEEPAD side", side, "wrap removed", int(wrap.sum()))

# 4. islands: components under 250 faces take their neighbours' majority label
def components(L):
    comp = np.full(nF, -1, np.int64); sizes = []
    for s in range(nF):
        if comp[s] >= 0: continue
        cid = len(sizes); comp[s] = cid; q = [s]; n = 0
        while q:
            f = q.pop(); n += 1
            for g in nbr(f):
                if comp[g] < 0 and L[g] == L[f]: comp[g] = cid; q.append(g)
        sizes.append(n)
    return comp, np.array(sizes)
for it in range(3):
    comp, sizes = components(L); small = sizes < 250; fix = np.nonzero(small[comp])[0]
    if not len(fix): break
    votes = {}
    for f in fix:
        for g in nbr(f):
            if comp[g] != comp[f]: votes.setdefault(comp[f], []).append(L[g])
    for f in fix:
        v = votes.get(comp[f])
        if v: L[f] = np.bincount(v).argmax()
    print("ISLANDS pass", it, "components", len(sizes), "small", int(small.sum()), "faces", len(fix))
comp, sizes = components(L)
per = {names[i]: int(len(np.unique(comp[L == i]))) for i in range(len(names)) if (L == i).any()}
counts = {names[i]: int((L == i).sum()) for i in range(len(names)) if (L == i).any()}
print("PIECES", json.dumps(per)); print("COUNTS", json.dumps(counts))
np.save(out + "/face-labels.npy", L)
json.dump({"counts": counts, "pieces": per, "changed": int((L != L0).sum())}, open(out + "/labels-v2.json", "w"), indent=2)
print("LABELS_DONE changed", int((L != L0).sum()))
