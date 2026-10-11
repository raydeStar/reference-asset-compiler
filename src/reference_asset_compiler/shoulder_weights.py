"""Keep a T-pose scan's arm weights on the arm (pure numpy; blender/refine_shoulder_weights.py applies it).

Weights solved on a scanned T-pose (voxel heat, nearest proxy) let the upper arm
reach well into the torso: on character-02 its influence ran to 2 cm from the
breastbone and down the chest and back. Lowered or swinging, the arm then drags
the coat's chest into the armpit (crumpled lapels) and swings the coat's side
panel with it (Astra's "armhole intersections"). This moves that weight back:

- inboard: a vertex's upper-arm weight (the upperarm bone and its twists) fades
  from all of it outboard of the shoulder joint + `outboard_m` to none inboard
  of the joint - `inboard_m` (smoothstep across x), and what it loses goes to the
  clavicle, which carries the shoulder, from `clavicle_from_m` off the midline
  (all of it by the joint - `inboard_m`); nearer the breastbone it goes to the
  spine, so the chest stays with the shirt under it when the clavicle drops;
- under the arm: below the armpit (the lowest point of the sleeve just outboard
  of the shoulder) less `under_armpit_m`, a vertex keeps no upper-arm weight
  (smoothstep over `armpit_blend_m`), and what it loses goes to the spine bone it
  already follows most (else `spine_fallback`): the torso under the arm stays
  the torso.

Weights stay normalized and capped at `max_influences` per vertex.

smooth_across_layers then evens the torso's weights across its layers: a
scanned outfit's lapel lies millimetres over its shirt but took its weights
separately, and with the clavicle dropped (as the game's animations drop it)
the lapel's underside swung through the shirt.
"""

from __future__ import annotations

import numpy as np

ARM_BONES = ("upperarm_{s}", "upperarm_twist_01_{s}", "upperarm_twist_02_{s}")
SPINES = ("spine_05", "spine_04", "spine_03", "spine_02", "spine_01")


def _smooth(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def armpit_height(positions, shoulder, side_sign, near=(0.08, 0.12), reach=0.25):
    """The lowest point of the sleeve 8-12 cm outboard of the shoulder joint (within `reach` below it)."""
    d = side_sign * (positions[:, 0] - shoulder[0])
    sel = (d > near[0]) & (d < near[1]) & (positions[:, 2] > shoulder[2] - reach)
    return float(positions[sel, 2].min()) if sel.any() else None


def refine(weights, bones, positions, shoulders, inboard_m=0.03, outboard_m=0.07, under_armpit_m=0.05,
           armpit_blend_m=0.05, clavicle_from_m=0.08, max_influences=4, spine_fallback="spine_04"):
    """weights (n, b), bones (b names), positions (n, 3) rest, shoulders {"l": xyz, "r": xyz} (upperarm heads).

    Returns (new weights, report)."""
    w = np.array(weights, float)
    index = {name: i for i, name in enumerate(bones)}
    report = {"armpit_z": {}, "moved_to_clavicle": 0.0, "moved_to_spine": 0.0}
    spine_cols = [index[s] for s in SPINES if s in index]
    for side, sign in (("l", 1.0), ("r", -1.0)):
        if side not in shoulders or f"clavicle_{side}" not in index:
            continue
        sh = np.asarray(shoulders[side], float)
        arm_cols = [index[b.format(s=side)] for b in ARM_BONES if b.format(s=side) in index]
        if not arm_cols:
            continue
        d = sign * (positions[:, 0] - sh[0])
        t_in = _smooth((d + inboard_m) / (inboard_m + outboard_m))
        pit = armpit_height(positions, sh, sign)
        report["armpit_z"][side] = None if pit is None else round(pit, 4)
        t_under = np.ones(len(w)) if pit is None else _smooth((positions[:, 2] - (pit - under_armpit_m)) / armpit_blend_m)
        arm_w = w[:, arm_cols]
        keep = arm_w * (t_in * t_under)[:, None]
        lost = (arm_w - keep).sum(1)
        w[:, arm_cols] = keep
        # what fades under the arm goes to the spine; what fades inboard goes to the clavicle
        to_spine = lost * (1 - t_under) / np.maximum((1 - t_under) + (1 - t_in) * t_under, 1e-9)
        to_spine[lost <= 0] = 0
        to_clav = lost - to_spine
        # near the breastbone the chest follows the spine, not the clavicle
        share = _smooth((sign * positions[:, 0] - clavicle_from_m) / max(sign * sh[0] - inboard_m - clavicle_from_m, 1e-6))
        to_spine += to_clav * (1 - share)
        to_clav *= share
        w[:, index[f"clavicle_{side}"]] += to_clav
        if spine_cols:
            sp = np.array(spine_cols)[np.argmax(w[:, spine_cols], axis=1)]
            sp[w[:, spine_cols].max(1) <= 0] = index.get(spine_fallback, spine_cols[0])
            np.add.at(w, (np.arange(len(w)), sp), to_spine)
        else:
            w[:, index[f"clavicle_{side}"]] += to_spine
        report["moved_to_clavicle"] += float(to_clav.sum())
        report["moved_to_spine"] += float(to_spine.sum())
    w = _cap(w, max_influences)
    report["moved_to_clavicle"] = round(report["moved_to_clavicle"], 3)
    report["moved_to_spine"] = round(report["moved_to_spine"], 3)
    return w, report


def _cap(w, max_influences):
    if max_influences and w.shape[1] > max_influences:
        np.put_along_axis(w, np.argsort(-w, axis=1)[:, max_influences:], 0.0, axis=1)
    total = w.sum(1, keepdims=True)
    return np.where(total > 0, w / np.maximum(total, 1e-12), w)


def smooth_across_layers(weights, positions, region, radius_m=0.015, iterations=2, max_influences=4, chunk=256):
    """Each vertex in `region` takes the Gaussian mean (sigma `radius_m` / 2) of the weights within `radius_m`
    of it, on whatever surface they lie, `iterations` times: layers millimetres apart then move together.

    Returns (new weights, report)."""
    w = np.array(weights, float)
    pos = np.asarray(positions, float)
    idx = np.flatnonzero(region)
    if not len(idx):
        return w, {"layer_vertices": 0, "layer_pairs": 0}
    lo, hi = pos[idx].min(0) - radius_m, pos[idx].max(0) + radius_m
    cand = np.flatnonzero(((pos >= lo) & (pos <= hi)).all(1))
    pc, sq = pos[cand], (pos[cand] ** 2).sum(1)
    rows, cols, gains = [], [], []
    for k in range(0, len(idx), chunk):
        q = idx[k:k + chunk]
        d2 = np.maximum((pos[q] ** 2).sum(1)[:, None] - 2 * pos[q] @ pc.T + sq[None, :], 0.0)
        qi, j = np.nonzero(d2 < radius_m ** 2)
        rows.append(q[qi])
        cols.append(cand[j])
        gains.append(np.exp(-4.0 * d2[qi, j] / radius_m ** 2))
    rows, cols, gains = np.concatenate(rows), np.concatenate(cols), np.concatenate(gains)
    total = np.bincount(rows, gains, minlength=len(w))
    for _ in range(iterations):
        acc = np.zeros_like(w)
        np.add.at(acc, rows, w[cols] * gains[:, None])
        w[idx] = acc[idx] / total[idx, None]
    return _cap(w, max_influences), {"layer_vertices": int(len(idx)), "layer_pairs": int(len(rows))}
