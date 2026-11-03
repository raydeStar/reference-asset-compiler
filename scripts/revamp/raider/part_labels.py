"""Part labels and loose shells on the rigged Raider body, shared by rigid_parts.py and plate_check.py.

The body paint mesh carries a part label per face (part_uv_mask.py) and shares its UV atlas with the production
mesh, so the labels are rasterized into the atlas and read back at each rigged face's UV centre. Hand and head faces
(their own materials) are labelled 'hand' and 'head'.
"""
import json
from collections import Counter

import numpy as np

from uv_raster import fill_polygon

SIZE = 1024


def face_labels(me, obj_path, parts_path, names_path):
    """Each polygon's part name, read through the shared body atlas."""
    names = json.load(open(names_path))['parts']
    labels = np.load(parts_path)
    vt, faces = [], []
    for line in open(obj_path, encoding='utf-8', errors='ignore'):
        if line.startswith('vt '):
            vt.append([float(x) for x in line.split()[1:3]])
        elif line.startswith('f '):
            faces.append([int(c.split('/')[1]) - 1 for c in line.split()[1:]])
    if len(faces) != len(labels):
        raise SystemExit(f'paint mesh has {len(faces)} faces but {len(labels)} part labels')
    vt = np.array(vt) * SIZE
    atlas = np.full((SIZE, SIZE), -1, np.int16)
    for f, label in zip(faces, labels):
        pts = vt[f]
        x0, y0 = np.maximum(np.floor(pts.min(0)).astype(int), 0)
        x1, y1 = np.minimum(np.ceil(pts.max(0)).astype(int), SIZE - 1)
        if x1 < x0 or y1 < y0:
            continue
        sub = np.zeros((y1 - y0 + 1, x1 - x0 + 1), bool)
        fill_polygon(sub, pts - [x0, y0])
        atlas[y0:y1 + 1, x0:x1 + 1][sub] = label
    uv = me.uv_layers.active.data
    mats = [m.name for m in me.materials]
    out = []
    for p in me.polygons:
        mat = mats[p.material_index]
        if mat != 'painted':
            out.append('hand' if mat == 'Material.001' else 'head')
            continue
        c = np.mean([uv[i].uv[:] for i in p.loop_indices], 0) * SIZE
        x, y = np.clip(c.astype(int), 0, SIZE - 1)
        label = atlas[y, x]
        if label < 0:  # a UV centre in a gutter: the commonest label close by
            win = atlas[max(y - 4, 0):y + 5, max(x - 4, 0):x + 5]
            near = win[win >= 0]
            label = Counter(near.tolist()).most_common(1)[0][0] if len(near) else -1
        out.append(names[label] if label >= 0 else '')
    return out


def shells(me):
    """Loose pieces as (vertex indices, polygon indices), largest first."""
    parent = np.arange(len(me.vertices))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for e in me.edges:
        a, b = find(e.vertices[0]), find(e.vertices[1])
        if a != b:
            parent[a] = b
    root = np.array([find(i) for i in range(len(parent))])
    polys = {}
    for p in me.polygons:
        polys.setdefault(root[p.vertices[0]], []).append(p.index)
    return sorted(((np.flatnonzero(root == r), np.array(f)) for r, f in polys.items()), key=lambda s: -len(s[0]))


def shell_label(labels, polys):
    return Counter(labels[i] for i in polys).most_common(1)[0][0]
