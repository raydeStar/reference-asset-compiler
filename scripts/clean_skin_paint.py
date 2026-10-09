"""Lift stray hair paint off a head's skin texture.

Projection painting puts whatever a picture shows in front of the skin onto the
skin: a lock of hair hanging past the jaw becomes a dark blot at the jaw corner.
This finds dark blots on skin in texture space (a morphological black-hat: the
dark detail a closing of the texture fills in, where the closed colour is skin)
and inpaints them from the skin around them. Features that are dark by nature
stay: brows, eyes, nostrils and lips (the template's face landmarks, located in
UV space through their surface binding and grown by a margin), and the scalp,
whose paint is the hair's root colour, the ears, and anything that is not the body's skin (eyeballs, teeth).

Usage:
  python scripts/clean_skin_paint.py --template template.npz \
      --binding profiles/head-templates/hm08-male-face-landmarks.json \
      --texture head_basecolor.png --out head_basecolor.png [--mask blots.png]
      [--work-size 1024] [--blot-frac 0.035] [--min-depth 40] [--keep-margin-frac 0.012]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

# 68-point groups that keep their dark paint: brows, eyes, nostrils, mouth.
KEEP_GROUPS = (range(17, 22), range(22, 27), range(36, 42), range(42, 48), range(31, 36), range(48, 60))


def vertex_uv(t):
    """One UV per vertex (the first loop that uses it; seams pick a side)."""
    loops = t["loops"]
    uv = np.full((int(loops.max()) + 1, 2), np.nan)
    first = np.unique(loops, return_index=True)
    uv[first[0]] = t["loop_uv"][first[1]]
    return uv


def to_px(uv, size):
    return np.stack([uv[:, 0] * size, (1.0 - uv[:, 1]) * size], 1)


def skin_like(bgr):
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    L = lab[..., 0] * 100 / 255
    a, b = lab[..., 1] - 128, lab[..., 2] - 128
    hue = np.degrees(np.arctan2(b, a))
    return (L > 25) & (np.hypot(a, b) > 14) & (hue > 20) & (hue < 85)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--template", required=True)
    p.add_argument("--binding", required=True, help="face-landmark binding (fit_head_placement.py --save-binding)")
    p.add_argument("--texture", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--mask", help="write the blots found here")
    p.add_argument("--work-size", type=int, default=1024)
    p.add_argument("--blot-frac", type=float, default=0.035, help="widest blot, as a share of the texture")
    p.add_argument("--min-depth", type=float, default=40.0, help="how much darker than the skin around (0-255)")
    p.add_argument("--keep-margin-frac", type=float, default=0.012)
    p.add_argument("--head-min-z", type=float, default=1.4, help="template height (m) where the head's skin starts")
    a = p.parse_args(argv)

    t = np.load(a.template, allow_pickle=True)
    binding = json.loads(Path(a.binding).read_text(encoding="utf-8"))
    tex = cv2.imread(a.texture, cv2.IMREAD_COLOR)
    full = tex.shape[0]
    n = a.work_size
    small = cv2.resize(tex, (n, n), interpolation=cv2.INTER_AREA)

    keep = np.zeros((n, n), np.uint8)
    vuv = vertex_uv(t)
    lm = {i: to_px((np.array(b)[:, None] * vuv[v]).sum(0)[None], n)[0]
          for i, (v, b) in enumerate(zip(binding["vertices"], binding["barycentric"])) if v is not None}
    for g in KEEP_GROUPS:
        pts = np.array([lm[i] for i in g if i in lm])
        if len(pts) >= 3:
            cv2.fillConvexPoly(keep, cv2.convexHull(pts.astype(np.int32)), 1)
    starts, totals, loops = t["loop_starts"], t["loop_totals"], t["loops"]
    nv = int(loops.max()) + 1

    def group(*names):
        g = np.zeros(nv, bool)
        for name in names:
            if "vg__" + name in t.files:
                g[t["vg__" + name]] = True
        return g

    scalp, body = group("scalp", "ears"), group("body")
    body &= t["verts"][:nv, 2] > a.head_min_z      # the head and neck: the rest of the body's UVs carry no paint here
    skin = np.zeros((n, n), np.uint8)       # only the body's own skin: never the eyeballs, teeth or tongue
    for st, tot in zip(starts, totals):
        poly = [to_px(t["loop_uv"][st:st + tot], n).astype(np.int32)]
        vs = loops[st:st + tot]
        if scalp[vs].all():
            cv2.fillPoly(keep, poly, 1)
        elif body[vs].all():
            cv2.fillPoly(skin, poly, 1)
    m = max(1, int(a.keep_margin_frac * n))
    keep = cv2.dilate(keep, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * m + 1,) * 2)).astype(bool)
    keep |= ~skin.astype(bool)

    k = max(3, int(a.blot_frac * n) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    grey = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    depth = cv2.morphologyEx(grey, cv2.MORPH_BLACKHAT, kernel).astype(np.float32)
    around = cv2.morphologyEx(small, cv2.MORPH_CLOSE, kernel)
    blot = (depth > a.min_depth) & skin_like(around) & ~keep
    blot = cv2.dilate(blot.astype(np.uint8), np.ones((5, 5), np.uint8))
    filled = cv2.inpaint(small, blot, 7, cv2.INPAINT_TELEA)
    up_mask = cv2.resize(cv2.GaussianBlur(blot.astype(np.float32), (5, 5), 0), (full, full))[..., None]
    up_fill = cv2.resize(filled, (full, full), interpolation=cv2.INTER_CUBIC).astype(np.float32)
    out = tex.astype(np.float32) * (1 - up_mask) + up_fill * up_mask
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(a.out, np.clip(out, 0, 255).astype(np.uint8))
    if a.mask:
        vis = small.copy()
        vis[keep] = (vis[keep] * 0.5).astype(np.uint8)
        vis[blot.astype(bool)] = (255, 0, 255)
        cv2.imwrite(a.mask, vis)
    print(json.dumps({"texture": a.texture, "out": a.out, "blot_share": round(float(blot.mean()), 5)}))


if __name__ == "__main__":
    main()
