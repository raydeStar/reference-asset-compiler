"""Seat the teeth under the lips and let the tongue ride the jaw, measured from the face's own morphs.

Used by game_review_single_mesh.py (recipe mouth.fit); importable on its own inside Blender.

A template head refitted to a picture keeps the template's teeth where they were. Remora's upper incisor edge ended
4.5 mm above the line where her lips meet: with the mouth open the upper teeth stayed hidden behind the lip and only
the lower row showed, and the tongue, which no morph moved with the jaw, hung at the top of the opening (V10). This:

1. splits the teeth into upper and lower by the jaw morph (the lower row moves with it);
2. finds the lip line at the mouth's centre from the same morph (the upper lip stays, the lower lip drops);
3. moves every tooth and the tongue by one vertical offset so the upper incisor edge sits `show_m` below that line
   (the basis and every key move together, so every morph keeps its delta);
4. gives the tongue the lower teeth's mean motion in every key that moves them (`tongue_follow` of it);
5. counts teeth and tongue vertices that can be seen past the skin with the mouth at rest (front and both
   three-quarters), before and after, and refuses the fit (mesh untouched) if more than `rest_tolerance` of them newly
   show: closed lips must hide them.
   The same count with the jaw open is reported; more showing there is the point.
"""
from __future__ import annotations

import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

DEFAULTS = {"jaw_morph": "mouth-open", "show_m": 0.001, "tongue_follow": 0.85, "max_shift_m": 0.008,
            "teeth": "teeth", "tongue": "tongue", "rest_tolerance": 0.01}
"""rest_tolerance: the share of teeth/tongue vertex sightings (three views) that may newly show past the lips at rest.
Remora's fit added 18 of 14,000, back teeth glimpsed through the mouth corners at the three-quarter angle; nothing
showed in the renders."""


def _coords(block, n):
    out = np.empty(n * 3)
    block.data.foreach_get('co', out)
    return out.reshape(-1, 3)


def _visible(me, co, skin_faces, verts, centre, where=None):
    """How many of `verts` can be seen past the skin from the front and both three-quarters (rays from 70 cm)."""
    polys = [list(me.polygons[f].vertices) for f in skin_faces]
    bvh = BVHTree.FromPolygons([Vector(c) for c in co], polys)
    seen = 0
    for eye in ((0.0, -0.7, 0.04), (0.4, -0.58, 0.04), (-0.4, -0.58, 0.04)):      # forward is -Y
        cam = Vector(centre) + Vector(eye)
        for v in verts:
            to = Vector(co[v]) - cam
            hit = bvh.ray_cast(cam, to.normalized(), to.length - 0.0005)
            if hit[0] is None:
                seen += 1
                if where is not None:
                    where.append([round(float(x), 4) for x in co[v]])
    return seen


def fit_mouth(obj, skin_materials, settings=None):
    s = {**DEFAULTS, **(settings or {})}
    me = obj.data
    keys = me.shape_keys.key_blocks if me.shape_keys else {}
    if s["jaw_morph"] not in keys:
        return {"fitted": False, "reason": f"no {s['jaw_morph']} morph"}
    n = len(me.vertices)
    mats = [m.name if m else '' for m in me.materials]
    parts = {"teeth": set(), "tongue": set(), "skin": set()}
    skin_faces = []
    for p in me.polygons:
        name = mats[p.material_index]
        if s["teeth"].lower() in name.lower():
            parts["teeth"].update(p.vertices)
        elif s["tongue"].lower() in name.lower():
            parts["tongue"].update(p.vertices)
        elif name in skin_materials:
            parts["skin"].update(p.vertices)
            skin_faces.append(p.index)
    if not parts["teeth"]:
        return {"fitted": False, "reason": "no teeth"}
    teeth, tongue, skin = (np.array(sorted(parts[k]), int) for k in ("teeth", "tongue", "skin"))
    basis = _coords(keys[0], n)
    jaw = _coords(keys[s["jaw_morph"]], n) - basis
    moved = np.linalg.norm(jaw, axis=1)
    lower = teeth[moved[teeth] >= 0.25 * moved[teeth].max()]
    upper = teeth[moved[teeth] < 0.25 * moved[teeth].max()]

    def front_edge(vs, lowest):
        c = vs[np.abs(basis[vs, 0]) < 0.006]
        c = c[basis[c, 1] < np.percentile(basis[c, 1], 10)]      # forward is -Y
        return float(basis[c, 2].min() if lowest else basis[c, 2].max())

    edge_upper, edge_lower = front_edge(upper, True), front_edge(lower, False)
    lip = skin[(np.abs(basis[skin, 0]) < 0.004) & (np.abs(basis[skin, 2] - edge_upper) < 0.02)
               & (basis[skin, 1] < basis[upper, 1].min())]
    top = moved[lip].max()
    still, dropped = lip[moved[lip] < 0.15 * top], lip[moved[lip] > 0.6 * top]
    if not len(still) or not len(dropped):
        return {"fitted": False, "reason": "no lip line found from the jaw morph"}
    upper_lip_low = float(basis[still, 2].min())
    lower_lip_high = float(basis[dropped, 2].max())
    lip_line = 0.5 * (upper_lip_low + lower_lip_high)
    shift = float(np.clip(lip_line - s["show_m"] - edge_upper, -s["max_shift_m"], s["max_shift_m"]))

    rigid = np.concatenate([teeth, tongue])
    open_co = basis + jaw
    centre = basis[teeth].mean(0)
    before = {"rest": _visible(me, basis, skin_faces, rigid, centre),
              "jaw_open": _visible(me, open_co, skin_faces, rigid, centre)}
    original = {kb.name: _coords(kb, n) for kb in keys}
    offset = np.zeros((n, 3))
    offset[rigid, 2] = shift
    followed = {}
    for kb in keys:
        co = _coords(kb, n)
        if kb.name != keys[0].name and len(tongue):
            delta = co - basis
            lower_mean = delta[lower].mean(0)
            if np.linalg.norm(lower_mean) > 0.002:
                co[tongue] = basis[tongue] + s["tongue_follow"] * lower_mean
                followed[kb.name] = round(float(np.linalg.norm(lower_mean)) * 1000, 1)
        kb.data.foreach_set('co', (co + offset).ravel())
    new_basis = basis + offset
    me.vertices.foreach_set('co', new_basis.ravel())
    me.update()
    new_open = _coords(keys[s["jaw_morph"]], n)
    shown = []
    after = {"rest": _visible(me, new_basis, skin_faces, rigid, centre, shown),
             "jaw_open": _visible(me, new_open, skin_faces, rigid, centre)}
    report = {
        "fitted": True, "settings": s, "upper_incisal_edge_z": round(edge_upper, 4),
        "lower_incisal_edge_z": round(edge_lower, 4), "upper_lip_low_z": round(upper_lip_low, 4),
        "lower_lip_high_z": round(lower_lip_high, 4), "lip_line_z": round(lip_line, 4),
        "shift_mm": round(shift * 1000, 2), "tongue_follows_mm": followed,
        "visible_before": before, "visible_after": after,
        "shown_at_rest_after": shown[:40],
    }
    if after["rest"] > before["rest"] + s["rest_tolerance"] * 3 * len(rigid):
        for kb in keys:      # refused: the mesh goes back exactly as it was
            kb.data.foreach_set('co', original[kb.name].ravel())
        me.vertices.foreach_set('co', original[keys[0].name].ravel())
        me.update()
        report["fitted"] = False
        report["reason"] = "with the fit, teeth or tongue show past closed lips"
    return report
