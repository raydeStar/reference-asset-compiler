"""Re-cut the Raider's part labels along smooth lines on the dense acquired mesh.

The labels from refine_labels.py are per face, so every part outline runs along the dense mesh's triangle edges: a
4 mm zig-zag, which the reductions after it (build_parts.py, prep_production.py) collapsed into the saw-tooth edges
and spikes on the straps and plates. Here each vertex takes each part's share of the face area around it, the shares
are diffused over the surface (ITERS rounds of averaging with the neighbours, which keeps them summing to one), and
every triangle whose corners lead with different parts is split where the leading shares are equal. Outlines then
cross triangles freely and are smooth at about the diffusion radius, and neighbouring parts share the same cut, so
no cracks open between them. A strip narrower than about that radius thins or goes; the report lists every part's
face area before and after.

Last, any island of a part smaller than MIN_ISLAND (1 cm^2 at this scale) takes the label around it: the diffused
cut left a dozen such scraps, which became 8-vertex shells. First, every piece of hair or beard cut off from the
head takes the label that surrounds it. The segmentation left a
478-triangle hair patch on the jacket's upper back; build_parts.py puts the face under hair, and place_head.py drops
the body's head parts, so that patch became a hole in the back of the jacket (the "dark notch" behind the collar).

  $B -b --factory-startup --python recut_labels.py -- <dense.glb> <face-labels.npy> <part-names.json> <out-dir> [iters]
writes <out-dir>/dense-recut.glb, face-labels.npy (one per recut face, for build_parts.py) and recut-report.json
"""
import json
import sys
from pathlib import Path

import bpy
import numpy as np

ITERS = 10
MIN_ISLAND = 1e-4                   # face area (dense mesh units, about m^2) below which a part's island is a scrap
CLAMP = 0.02                        # crossing points stay this far (edge fraction) from a corner: no slivers

a = sys.argv[sys.argv.index('--') + 1:]
src, labp, names, out = a[0], a[1], json.load(open(a[2])), Path(a[3])
iters = int(a[4]) if len(a) > 4 else ITERS
out.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
ob = next(o for o in bpy.context.scene.objects if o.type == 'MESH')
me = ob.data
me.transform(ob.matrix_world)
V = np.array([v.co[:] for v in me.vertices])
F = np.array([p.vertices[:] for p in me.polygons], np.int64)
L = np.load(labp).astype(np.int64)
if len(L) != len(F) or F.shape[1] != 3:
    raise SystemExit(f'{len(F)} faces (triangles expected) but {len(L)} labels')
nv, nl = len(V), len(names)
area = 0.5 * np.linalg.norm(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]), axis=1)

# face pairs across shared edges
E2 = np.sort(F[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2), 1)
key = E2[:, 0] * nv + E2[:, 1]
fid = np.repeat(np.arange(len(F)), 3)
order = np.argsort(key, kind='stable')
same = key[order][1:] == key[order][:-1]
fa, fb = fid[order][:-1][same], fid[order][1:][same]
stray = {}
for name in ('hair', 'beard'):
    part = names.index(name)
    sel = np.flatnonzero(L == part)
    parent = {int(f): int(f) for f in sel}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    inside = (L[fa] == part) & (L[fb] == part)
    for x, y in zip(fa[inside], fb[inside]):
        parent[find(int(x))] = find(int(y))
    root = np.array([find(int(f)) for f in sel])
    roots, counts = np.unique(root, return_counts=True)
    head = roots[counts.argmax()]
    for r in roots[roots != head]:
        piece = sel[root == r]
        mask = np.zeros(len(F), bool)
        mask[piece] = True
        rim = np.concatenate([L[fb[mask[fa] & ~mask[fb]]], L[fa[mask[fb] & ~mask[fa]]]])
        if len(rim):
            new = int(np.bincount(rim, minlength=nl).argmax())
            L[piece] = new
            stray.setdefault(name, []).append({'faces': len(piece), 'became': names[new]})

# each vertex's share of each part, by the area of its faces
S = np.zeros((nv, nl))
for k in range(3):
    for part in range(nl):
        sel = L == part
        S[:, part] += np.bincount(F[sel, k], weights=area[sel], minlength=nv)
S /= np.maximum(S.sum(1, keepdims=True), 1e-20)
E = np.unique(np.sort(F[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2), 1), axis=0)
deg = np.bincount(E.ravel(), minlength=nv).astype(float)
for _ in range(iters):
    acc = np.empty_like(S)
    for part in range(nl):
        acc[:, part] = (np.bincount(E[:, 0], weights=S[E[:, 1], part], minlength=nv)
                        + np.bincount(E[:, 1], weights=S[E[:, 0], part], minlength=nv))
    S = 0.5 * S + 0.5 * acc / np.maximum(deg, 1)[:, None]
A = S.argmax(1)

# the crossing point on every edge whose ends lead with different parts
lead = A[F]
mixed = ~((lead[:, 0] == lead[:, 1]) & (lead[:, 1] == lead[:, 2]))
cut = E[A[E[:, 0]] != A[E[:, 1]]]
u, w = cut[:, 0], cut[:, 1]
fu = S[u, A[u]] - S[u, A[w]]
fw = S[w, A[u]] - S[w, A[w]]
t = np.clip(fu / np.maximum(fu - fw, 1e-20), CLAMP, 1 - CLAMP)
cross = V[u] + t[:, None] * (V[w] - V[u])
point = {(int(x), int(y)): nv + i for i, (x, y) in enumerate(cut)}
newV = [V, cross]
nxt = nv + len(cut)


def p(x, y):
    return point[(x, y) if x < y else (y, x)]


faces, labels = [F[~mixed]], [L[~mixed]]
extra_f, extra_l, centres = [], [], []
for f in np.flatnonzero(mixed):
    v0, v1, v2 = (int(x) for x in F[f])
    a0, a1, a2 = (int(x) for x in A[F[f]])
    if a0 != a1 and a1 != a2 and a0 != a2:
        p01, p12, p20 = p(v0, v1), p(v1, v2), p(v2, v0)
        c = nxt
        nxt += 1
        centres.append((cross[p01 - nv] + cross[p12 - nv] + cross[p20 - nv]) / 3)
        extra_f += [(v0, p01, c), (v0, c, p20), (v1, p12, c), (v1, c, p01), (v2, p20, c), (v2, c, p12)]
        extra_l += [a0, a0, a1, a1, a2, a2]
        continue
    # one corner leads with a part of its own: rotate it first, keeping the winding
    if a0 == a1:
        i, j, k = v2, v0, v1
    elif a1 == a2:
        i, j, k = v0, v1, v2
    else:
        i, j, k = v1, v2, v0
    pij, pik = p(i, j), p(i, k)
    extra_f += [(i, pij, pik), (pij, j, k), (pij, k, pik)]
    extra_l += [int(A[i]), int(A[j]), int(A[j])]
if centres:
    newV.append(np.array(centres))
P = np.concatenate(newV)
NF = np.concatenate(faces + [np.array(extra_f, np.int64).reshape(-1, 3)])
NL = np.concatenate(labels + [np.array(extra_l, np.int64)])
narea = 0.5 * np.linalg.norm(np.cross(P[NF[:, 1]] - P[NF[:, 0]], P[NF[:, 2]] - P[NF[:, 0]]), axis=1)

# scraps: islands of a part under MIN_ISLAND take the label most of their border shares
E3 = np.sort(NF[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2), 1)
key3 = E3[:, 0] * len(P) + E3[:, 1]
fid3 = np.repeat(np.arange(len(NF)), 3)
order3 = np.argsort(key3, kind='stable')
same3 = key3[order3][1:] == key3[order3][:-1]
ga, gb = fid3[order3][:-1][same3], fid3[order3][1:][same3]
parent = np.arange(len(NF))


def root(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


for x, y in zip(ga[NL[ga] == NL[gb]], gb[NL[ga] == NL[gb]]):
    rx, ry = root(int(x)), root(int(y))
    if rx != ry:
        parent[rx] = ry
roots = np.array([root(i) for i in range(len(NF))])
island_area = np.bincount(roots, weights=narea, minlength=len(NF))
scrap = island_area[roots] < MIN_ISLAND
scraps = 0
for r in np.unique(roots[scrap]):
    piece = roots == r
    border = np.concatenate([NL[gb[piece[ga] & ~piece[gb]]], NL[ga[piece[gb] & ~piece[ga]]]])
    if len(border):
        NL[piece] = np.bincount(border, minlength=nl).argmax()
        scraps += 1

m = bpy.data.meshes.new('dense_recut')
m.from_pydata(P.tolist(), [], NF.tolist())
m.update()
for poly in m.polygons:
    poly.use_smooth = True          # shared vertices survive the glTF round trip only on a smooth mesh
o = bpy.data.objects.new('dense_recut', m)
bpy.context.scene.collection.objects.link(o)
for x in bpy.context.scene.objects:
    x.select_set(x == o)
bpy.ops.export_scene.gltf(filepath=str(out / 'dense-recut.glb'), export_format='GLB', use_selection=True,
                          export_materials='NONE', export_texcoords=False)
np.save(out / 'face-labels.npy', NL.astype(np.int32))
report = {'source': src, 'labels': labp, 'iters': iters, 'stray_head_pieces': stray, 'scraps_relabelled': scraps,
          'faces_before': len(F), 'faces_after': len(NF),
          'faces_split': int(mixed.sum()), 'three_part_faces': len(centres),
          'area_before': {n: round(float(area[L == i].sum()), 5) for i, n in enumerate(names) if (L == i).any()},
          'area_after': {n: round(float(narea[NL == i].sum()), 5) for i, n in enumerate(names) if (NL == i).any()}}
(out / 'recut-report.json').write_text(json.dumps(report, indent=1))
print('RECUT_OK', {k: v for k, v in report.items() if not k.startswith('area')})
