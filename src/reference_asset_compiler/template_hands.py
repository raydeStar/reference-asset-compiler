"""The template's hands for a scanned character (pure numpy).

blender/transplant_template_hands.py fits them to a rig and cuts the scan's;
paint_template_hands.py paints them in the face texture's atlas.

A generator's hands from a T-pose picture are mittens or paddles: fingers
fused or stiff, palm and back unseen by the front and back pictures. The
template (MakeHuman hm08, the one the head is conformed from) has hands with
finger topology, skin weights on UE5-named finger bones and UVs in the same
atlas as the head. Positions are hm08's: metres, facing -y.
"""

from __future__ import annotations

import numpy as np

FINGERS = ("index", "middle", "ring", "pinky", "thumb")


def _unit(v):
    return v / np.linalg.norm(v)


def hand_columns(index, side):
    """The weight columns of the hand bone and its finger bones."""
    return [index[f"hand_{side}"]] + [index[f"{f}_{k}_{side}"] for f in FINGERS for k in ("01", "02", "03")
                                      if f"{f}_{k}_{side}" in index]


def frame(axis, side):
    """An orthonormal frame (columns: axis, side, normal) from the hand's axis and its index-to-pinky direction.

    A left hand's normal points out of its palm; a right hand's, mirrored, out of its back."""
    a = _unit(np.asarray(axis, float))
    s = np.asarray(side, float) - a * (np.asarray(side, float) @ a)
    s = _unit(s)
    return np.stack([a, s, np.cross(a, s)], 1)


def palm_normal(marks, side):
    """The direction out of the palm."""
    f = frame(marks["middle"] - marks["wrist"], marks["index"] - marks["pinky"])
    return f[:, 2] * (1.0 if side == "l" else -1.0)


def landmarks(verts, weights, index, side):
    """The template's wrist (where the hand's and forearm's weights meet) and middle, index and pinky
    knuckles (where their first bones' weights pass half)."""
    hand = weights[:, hand_columns(index, side)].sum(1)
    ring = (hand > 0.3) & (weights[:, index[f"lowerarm_{side}"]] > 0.2) & (weights[:, index[f"hand_{side}"]] > 0.2)
    marks = {"wrist": verts[ring].mean(0) if ring.any() else verts[hand > 0.3].mean(0)}
    for finger in ("middle", "index", "pinky"):
        marks[finger] = verts[weights[:, index[f"{finger}_01_{side}"]] > 0.5].mean(0)
    return marks


def hand_vertices(verts, weights, index, side, hand_weight=0.3, wrist_back_m=0.05, lining_radius_m=0.06):
    """The template's hand (hand and finger weights past `hand_weight`) and its forearm up to `wrist_back_m`
    behind the wrist within `lining_radius_m` of the hand's axis: it lines the sleeve, so no view into the
    cuff sees through it."""
    hand = weights[:, hand_columns(index, side)].sum(1)
    marks = landmarks(verts, weights, index, side)
    axis = _unit(marks["middle"] - marks["wrist"])
    rel = verts - marks["wrist"]
    along = rel @ axis
    radial = np.linalg.norm(rel - along[:, None] * axis, axis=1)
    lining = ((along > -wrist_back_m) & (along <= 0) & (radial < lining_radius_m)
              & (weights[:, index[f"lowerarm_{side}"]] + hand > 0.5))
    return (hand > hand_weight) | lining


def polygons_within(mask, loops, starts, totals):
    """Polygons whose every vertex is in `mask`."""
    return np.array([bool(mask[loops[s:s + n]].all()) for s, n in zip(starts, totals)], bool)


def fit(template_marks, target_marks):
    """The turn and scale that carry the template's hand onto the target's joints: its wrist onto the
    target's wrist, its middle knuckle along the target's hand axis and its index-to-pinky line across it."""
    def axes(m):
        return frame(m["middle"] - m["wrist"], m["index"] - m["pinky"])
    rot = axes(target_marks) @ axes(template_marks).T
    scale = (np.linalg.norm(target_marks["middle"] - target_marks["wrist"])
             / np.linalg.norm(template_marks["middle"] - template_marks["wrist"]))
    return rot, float(scale)


def place(verts, template_marks, target_marks, rot, scale):
    return (verts - template_marks["wrist"]) @ rot.T * scale + target_marks["wrist"]


def cuff_end(along, back, near, ratio=0.8, step=0.005, span=(-0.10, 0.10), cuff=(-0.06, -0.01), cap=0.06):
    """Where a sleeve's cuff ends along the hand's axis (metres past the wrist joint), and the cuff's height.

    The back of a hand is flat and a cuff stands up round the wrist, so this reads the outfit's height over
    the back of the hand (`back`, for the vertices `near` the axis) in `step`s along it: not its width,
    which a palm matches, nor the palm side, where a scanned thumb hangs. The cuff's height is the median
    over `cuff`; it ends after the last step (short of `cap`) still `ratio` of that."""
    bins = np.arange(span[0], span[1], step)
    profile = np.array([back[near & (along >= b) & (along < b + step)].max(initial=0.0) for b in bins])
    height = float(np.median(profile[(bins >= cuff[0]) & (bins < cuff[1])]))
    wide = np.flatnonzero((profile > ratio * height) & (bins < cap))
    return (float(bins[wide.max()] + step) if len(wide) else 0.0), height


def cheek_vertices(template):
    """The template's cheeks beside the nose, between the eyes and the mouth: skin that no brow, lip, hair
    or ear covers (hm08's vertex groups and eye and mouth joints)."""
    verts, weights = template["verts"], template["weights"]
    index = {str(b): i for i, b in enumerate(template["bone_names"])}
    skin = np.zeros(len(verts), bool)
    skin[template["vg__body"]] = True
    for group in ("vg__lips", "vg__scalp", "vg__ears"):
        skin[template[group]] = False
    eye = verts[template["vg__joint-l-eye"]].mean(0)
    mouth = verts[template["vg__joint-mouth"]].mean(0)
    x, y, z = np.abs(verts[:, 0]), verts[:, 1], verts[:, 2]
    return (skin & (weights[:, index["head"]] > 0.9) & (z > mouth[2] - 0.035) & (z < eye[2] - 0.02)
            & (x > 0.02) & (x < 0.055) & (y < eye[1] + 0.04))


def skin_tone(texels, trim=(20, 80)):
    """The median of sRGB texels (0-1) whose luminance lies between the `trim` percentiles."""
    texels = np.asarray(texels, float)
    lum = texels @ np.array([0.2126, 0.7152, 0.0722])
    lo, hi = np.percentile(lum, trim)
    return np.median(texels[(lum >= lo) & (lum <= hi)], axis=0)


def polygon_normals(verts, loops, starts, totals):
    """Each polygon's normal (Newell's method), unit length."""
    out = np.zeros((len(starts), 3))
    for k, (s, n) in enumerate(zip(starts, totals)):
        p = verts[loops[s:s + n]]
        q = np.roll(p, -1, axis=0)
        out[k] = [((p[:, 1] - q[:, 1]) * (p[:, 2] + q[:, 2])).sum(), ((p[:, 2] - q[:, 2]) * (p[:, 0] + q[:, 0])).sum(),
                  ((p[:, 0] - q[:, 0]) * (p[:, 1] + q[:, 1])).sum()]
    return out / np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-12)
