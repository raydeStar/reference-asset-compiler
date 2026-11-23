"""Repaint the upper-lid skin a blink uncovers, so a shut eye is lid skin and not a smear of painted lashes.

Used by game_review_single_mesh.py (recipe closed_lids.clear); importable on its own inside Blender.

A head painted by projection from reference views carries the reference's dark lashes and liner on the lid margin. With
the eye open that skin is folded into the lid crease and almost invisible; the closure morphs unfold it across the eye,
and the paint stretches into a dark smear (Remora V9, 2026-11-07). The skin that does this is found from the mesh, not
by hand: every skin triangle whose area grows when the closure morphs are at 1, or that faces the viewer far more shut
than open (it slides down edge-on and turns to face the camera). Those texels are refilled from the
nearby skin that does not move (dark texels such as brows and liner wings are not used as a source), except a thin band
at the lid margin, which keeps a dark lash line along the bottom of the shut lid. The open eye is unchanged apart from
skin that is folded away; the lash cards are not touched.
"""
from __future__ import annotations

import numpy as np
from mathutils.kdtree import KDTree

DEFAULTS = {"morphs": ["eye-left-closure", "eye-right-closure"], "stretch": [1.3, 2.5], "seen_open": [0.35, 0.7],
            "lash_band_m": [0.0006, 0.0016], "moving_m": 0.0003, "forward": [0.0, -1.0, 0.0]}
"""stretch: a triangle that grows this much (area, shut over open) is repainted, fully at the upper value. seen_open:
a triangle whose front-facing area open is below this fraction of its front-facing area shut is repainted (it slides
down edge-on and only faces the camera once the lid shuts). lash_band_m: distance from the lid margin kept as painted,
blending to repainted at the upper value. forward: the head's facing direction in the mesh (Blender's -Y)."""


def _smoothstep(x, lo, hi):
    t = np.clip((x - lo) / (hi - lo), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _box(a, r):
    """Box blur of an HxWxC array along both axes (edges clamped)."""
    for axis in (0, 1):
        pad = [(0, 0)] * a.ndim
        pad[axis] = (r + 1, r)
        c = np.cumsum(np.pad(a, pad, mode='edge'), axis=axis)
        hi = np.take(c, np.arange(2 * r + 1, c.shape[axis]), axis=axis)
        lo = np.take(c, np.arange(0, c.shape[axis] - 2 * r - 1), axis=axis)
        a = (hi - lo) / (2 * r + 1)
    return a


def _blur(a, sigma):
    r = max(1, int(round(sigma * 0.9)))      # three box passes ~ a gaussian of this sigma
    for _ in range(3):
        a = _box(a, r)
    return a


def _raster(tris_uv, tris_w, shape, box):
    """Per-texel weight of triangles (uv corners, per-corner weight), max over overlaps, inside box (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = box
    out = np.zeros((y1 - y0, x1 - x0))
    h, w = shape
    for uv, wt in zip(tris_uv, tris_w):
        p = uv * [w, h] - [x0, y0] - 0.5
        lo = np.floor(p.min(0)).astype(int)
        hi = np.ceil(p.max(0)).astype(int) + 1
        lo = np.maximum(lo, 0)
        hi = np.minimum(hi, [x1 - x0, y1 - y0])
        if (hi <= lo).any():
            continue
        xs, ys = np.meshgrid(np.arange(lo[0], hi[0]), np.arange(lo[1], hi[1]))
        a, b, c = p
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-12:
            continue
        l1 = ((b[1] - c[1]) * (xs - c[0]) + (c[0] - b[0]) * (ys - c[1])) / den
        l2 = ((c[1] - a[1]) * (xs - c[0]) + (a[0] - c[0]) * (ys - c[1])) / den
        l3 = 1 - l1 - l2
        inside = (l1 >= -0.02) & (l2 >= -0.02) & (l3 >= -0.02)      # a hair over the edge: no seams between tris
        val = np.clip(l1 * wt[0] + l2 * wt[1] + l3 * wt[2], 0, 1)
        sub = out[lo[1]:hi[1], lo[0]:hi[0]]
        np.maximum(sub, np.where(inside, val, 0.0), out=sub)
    return out


def clear_closed_lids(obj, skin_materials, settings=None):
    """Repaint obj's skin image where the closure morphs uncover painted lid margin. Returns a report (no-op report
    when the morphs or the skin image are missing)."""
    s = {**DEFAULTS, **(settings or {})}
    me = obj.data
    keys = me.shape_keys.key_blocks if me.shape_keys else {}
    morphs = [m for m in s["morphs"] if m in keys]
    if not morphs:
        return {"cleared": False, "reason": f"no closure morphs {s['morphs']} on the mesh"}
    n = len(me.vertices)
    basis = np.empty(n * 3)
    keys[0].data.foreach_get('co', basis)
    basis = basis.reshape(-1, 3)
    shut = basis.copy()
    for name in morphs:
        k = np.empty(n * 3)
        keys[name].data.foreach_get('co', k)
        shut += k.reshape(-1, 3) - basis
    moved = np.linalg.norm(shut - basis, axis=1)

    mats = [m.name if m else '' for m in me.materials]
    skin_idx = {i for i, m in enumerate(mats) if m in skin_materials}
    me.calc_loop_triangles()
    tri_v = np.array([t.vertices[:] for t in me.loop_triangles])
    tri_l = np.array([t.loops[:] for t in me.loop_triangles])
    tri_m = np.array([t.material_index for t in me.loop_triangles])
    uv = np.empty(len(me.loops) * 2)
    me.uv_layers.active.data.foreach_get('uv', uv)
    uv = uv.reshape(-1, 2)

    def area(co):
        a, b, c = co[tri_v[:, 0]], co[tri_v[:, 1]], co[tri_v[:, 2]]
        return 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)

    stretch = area(shut) / np.maximum(area(basis), 1e-14)

    def facing(co):      # area seen from the front (0 when the triangle faces away)
        a, b, c = co[tri_v[:, 0]], co[tri_v[:, 1]], co[tri_v[:, 2]]
        return np.maximum(0.5 * np.cross(b - a, c - a) @ np.asarray(s["forward"], float), 0.0)

    seen_open = facing(basis) / np.maximum(facing(shut), 1e-14)
    tri_weight = np.maximum(_smoothstep(stretch, *s["stretch"]), 1 - _smoothstep(seen_open, *s["seen_open"]))
    tri_weight = np.where(facing(shut) > 0, tri_weight, _smoothstep(stretch, *s["stretch"]))
    on_skin = np.isin(tri_m, list(skin_idx))
    lid = on_skin & (moved[tri_v].max(1) > s["moving_m"])
    if not lid.any():
        return {"cleared": False, "reason": "the closure morphs move no skin"}

    # per-vertex repaint weight (mean of its lid triangles) and distance to the lid margin
    v_sum, v_cnt = np.zeros(n), np.zeros(n)
    for t in np.nonzero(lid)[0]:
        v_sum[tri_v[t]] += tri_weight[t]
        v_cnt[tri_v[t]] += 1
    v_tri = np.where(v_cnt > 0, v_sum / np.maximum(v_cnt, 1), 0.0)
    # the lid margin: moving skin where the lash cards root (the skin runs on into the socket, so it is no boundary);
    # a head without lash cards falls back to the skin that travels furthest
    lid_v = np.unique(tri_v[lid])
    lash_idx = [i for i, m in enumerate(mats) if 'lash' in m.lower()]
    lash_v = np.unique(tri_v[np.isin(tri_m, lash_idx)]) if lash_idx else np.array([], int)
    margin = []
    if len(lash_v):
        skin_kd = KDTree(len(lid_v))
        for v in lid_v:
            skin_kd.insert(basis[v], v)
        skin_kd.balance()
        for v in lash_v:
            for _, idx, d in skin_kd.find_range(basis[v], 0.001):
                if d < 0.001 and moved[idx] > 2 * s["moving_m"]:
                    margin.append(idx)
    margin_from = "lash roots"
    if len(set(margin)) < 6:
        margin = list(lid_v[moved[lid_v] >= 0.85 * moved[lid_v].max()])
        margin_from = "furthest-moving skin"
    margin = sorted(set(margin))
    kd = KDTree(len(margin))
    for v in margin:
        kd.insert(basis[v], v)
    kd.balance()
    dist = np.full(n, 1.0)
    for v in lid_v:
        dist[v] = kd.find(basis[v])[2]
    v_weight = v_tri * _smoothstep(dist, *s["lash_band_m"])

    # the skin image (behind the Base Color of the first skin material)
    image = None
    for i in sorted(skin_idx):
        tree = me.materials[i].node_tree
        bsdf = next((nd for nd in tree.nodes if nd.type == 'BSDF_PRINCIPLED'), None)
        if bsdf is None or not bsdf.inputs['Base Color'].is_linked:
            continue
        node = bsdf.inputs['Base Color'].links[0].from_node
        while node.type != 'TEX_IMAGE':
            linked = [inp for inp in node.inputs if inp.is_linked]
            if not linked:
                break
            node = linked[0].links[0].from_node
        if node.type == 'TEX_IMAGE' and node.image:
            image = node.image
            break
    if image is None:
        return {"cleared": False, "reason": "no skin base colour image"}
    w, h = image.size
    px = np.empty(w * h * 4, dtype=np.float32)
    image.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)

    # sources: skin that does not move, within 2.5 cm of the lid (3D), off the dark marks
    centre_kd = KDTree(len(lid_v))
    for v in lid_v:
        centre_kd.insert(basis[v], v)
    centre_kd.balance()
    centroid = basis[tri_v].mean(1)
    lo, hi = basis[lid_v].min(0) - 0.025, basis[lid_v].max(0) + 0.025
    candidates = (on_skin & (moved[tri_v].max(1) < s["moving_m"] * 0.5)
                  & np.all((centroid > lo) & (centroid < hi), axis=1))
    near = np.zeros(len(tri_v), bool)
    for t in np.nonzero(candidates)[0]:
        near[t] = centre_kd.find(centroid[t])[2] < 0.025
    paint = lid & (v_weight[tri_v].max(1) > 0)
    corners = uv[tri_l[paint]]      # sources beyond the reach of the widest blur do not matter
    pad = 160
    x0 = max(int(corners[:, 0].min() * w) - pad, 0)
    x1 = min(int(corners[:, 0].max() * w) + pad, w)
    y0 = max(int(corners[:, 1].min() * h) - pad, 0)
    y1 = min(int(corners[:, 1].max() * h) + pad, h)
    box = (x0, y0, x1, y1)
    weight = _raster(uv[tri_l[paint]], v_weight[tri_v[paint]], (h, w), box)
    source = _raster(uv[tri_l[near]], np.ones((int(near.sum()), 3)), (h, w), box) > 0.5
    region = px[y0:y1, x0:x1, :3].astype(np.float64)
    lum = region @ [0.2126, 0.7152, 0.0722]
    if source.any():
        source &= lum > 0.6 * np.median(lum[source])
    if not source.any():
        return {"cleared": False, "reason": "no unmoving lid skin to sample"}
    # normalised convolution, coarse to fine: each scale fills what the finer one could not reach
    fill = np.zeros_like(region)
    confidence = np.zeros(region.shape[:2])
    for sigma in (6, 16, 40, 100):
        num = _blur(region * source[..., None], sigma)
        den = _blur(source[..., None].astype(np.float64), sigma)[..., 0]
        ok = den > 0.02
        est = np.where(ok[..., None], num / np.maximum(den, 1e-6)[..., None], 0.0)
        take = (1 - confidence) * np.clip(den / 0.2, 0, 1)
        fill += take[..., None] * est
        confidence += take
    fill /= np.maximum(confidence, 1e-6)[..., None]
    out = region * (1 - weight[..., None]) + fill * weight[..., None]
    before = px[y0:y1, x0:x1, :3].copy()
    px[y0:y1, x0:x1, :3] = out
    image.pixels.foreach_set(px.ravel())
    image.update()
    image.pack()
    if s.get("debug_npz"):
        np.savez(s["debug_npz"], before=before, after=out, weight=weight, source=source, box=np.array(box))
    changed = weight > 0.01
    return {
        "cleared": True, "image": image.name, "image_size": [w, h], "box_px": list(box), "morphs": morphs,
        "settings": s, "lid_triangles": int(lid.sum()), "repainted_triangles": int(paint.sum()),
        "margin_vertices": len(margin), "margin_from": margin_from, "source_texels": int(source.sum()), "texels_changed": int(changed.sum()),
        "max_stretch": round(float(stretch[lid].max()), 2),
        "mean_luminance_change": round(float(((out - before) @ [0.2126, 0.7152, 0.0722])[changed].mean()), 4)
        if changed.any() else 0.0,
    }
