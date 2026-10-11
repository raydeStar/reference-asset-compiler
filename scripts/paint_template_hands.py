"""Paint the template's hands into a face texture's atlas, in the face's own skin tone.

The template's hands (blender/transplant_template_hands.py) carry the template's
UVs, which put them in the head texture's atlas, where the face paint leaves
whatever the projection or fill put there (on character-02, dark hair colour
under the right hand). This paints their polygons there:

- tone: the cheeks' texels (template_hands.cheek_vertices: skin no brow, lip,
  hair or ear covers), a median of the luminance between the 20th and 80th
  percentiles;
- the back of each hand and the forearm lining in that tone; the palm lighter
  (`--palm-gain`, linear) and the nails lighter still (`--nail-gain`);
- softened (a Gaussian of `--blur-px` within the hands, so palm and back meet
  without a step) and grown `--margin-px` past the islands for texture filtering,
  never over another polygon's texels.

Usage:
  python scripts/paint_template_hands.py --template template.npz --texture head_basecolor.png \
      --out hands-paint/head_basecolor.png --receipt hands-paint/receipt.json [--hand-weight 0.3] [--wrist-back-m 0.05]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from reference_asset_compiler.template_hands import (  # noqa: E402
    cheek_vertices, hand_vertices, landmarks, palm_normal, polygon_normals, polygons_within, skin_tone)


def to_linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def rasterize(polys, uv, size, starts, totals):
    """A mask of the polygons' UV shapes; each polygon in `polys` (indices) gets the value 255."""
    w, h = size
    mask = Image.new("L", size)
    draw = ImageDraw.Draw(mask)
    for k in polys:
        s, n = starts[k], totals[k]
        draw.polygon([(u * w, (1 - v) * h) for u, v in uv[s:s + n]], fill=255)
    return np.asarray(mask) > 0


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--template", type=Path, required=True)
    p.add_argument("--texture", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--receipt", type=Path, required=True)
    p.add_argument("--hand-weight", type=float, default=0.3)
    p.add_argument("--wrist-back-m", type=float, default=0.05)
    p.add_argument("--palm-gain", type=float, default=1.18, help="the palm's linear brightness over the back's")
    p.add_argument("--nail-gain", type=float, default=1.35, help="the nails' linear brightness over the back's")
    p.add_argument("--blur-px", type=float, default=6.0)
    p.add_argument("--margin-px", type=int, default=8)
    a = p.parse_args(argv)

    t = np.load(a.template, allow_pickle=True)
    verts, weights = t["verts"].astype(float), t["weights"].astype(float)
    loops, starts, totals, uv = t["loops"], t["loop_starts"], t["loop_totals"], t["loop_uv"]
    index = {str(b): i for i, b in enumerate(t["bone_names"])}
    tex = np.asarray(Image.open(a.texture).convert("RGB"), float) / 255
    size = (tex.shape[1], tex.shape[0])

    cheeks = np.flatnonzero(polygons_within(cheek_vertices(t), loops, starts, totals))
    tone = skin_tone(tex[rasterize(cheeks, uv, size, starts, totals)])
    lin = to_linear(tone)
    nails = np.zeros(len(verts), bool)
    nails[t["vg__fingernails"]] = True
    normals = polygon_normals(verts, loops, starts, totals)
    colour = np.zeros_like(tex)
    inside = np.zeros(tex.shape[:2], bool)
    counts, every_hand = {}, []
    for side in ("l", "r"):
        hand = np.flatnonzero(polygons_within(
            hand_vertices(verts, weights, index, side, a.hand_weight, a.wrist_back_m), loops, starts, totals))
        every_hand.append(hand)
        palm = hand[normals[hand] @ palm_normal(landmarks(verts, weights, index, side), side) > 0.3]
        nail = hand[polygons_within(nails, loops, starts, totals)[hand]]
        for polys, gain in ((hand, 1.0), (palm, a.palm_gain), (nail, a.nail_gain)):
            m = rasterize(polys, uv, size, starts, totals)
            colour[m] = lin * gain
            inside |= m
        counts[side] = {"polygons": int(len(hand)), "palm_polygons": int(len(palm)), "nail_polygons": int(len(nail))}

    # soften within the hands, blur(colour * mask) / blur(mask), and grow past the islands for
    # filtering, never over another polygon's texels
    m = inside.astype(float)
    weight = ndimage.gaussian_filter(m, a.blur_px)
    soft = np.stack([ndimage.gaussian_filter(colour[..., c] * m, a.blur_px) for c in range(3)], -1)
    soft /= np.maximum(weight, 1e-6)[..., None]
    others = rasterize(np.setdiff1d(np.arange(len(starts)), np.concatenate(every_hand)), uv, size, starts, totals)
    grown = ndimage.binary_dilation(inside, iterations=a.margin_px)
    paint = inside | (grown & ~others & (weight > 1e-3))
    out = tex.copy()
    out[paint] = to_srgb(soft[paint])
    a.out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)).save(a.out)
    receipt = {
        "stage": "paint_template_hands", "tone_srgb": np.round(tone, 4).tolist(),
        "palm_srgb": np.round(to_srgb(lin * a.palm_gain), 4).tolist(),
        "nail_srgb": np.round(to_srgb(lin * a.nail_gain), 4).tolist(),
        "cheek_polygons": int(len(cheeks)), "sides": counts, "texels_painted": int(paint.sum()),
        "texels_over_other_polygons": int((inside & others).sum()),
        "parameters": {k: v for k, v in vars(a).items() if k not in ("template", "texture", "out", "receipt")},
        "inputs": {name: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                   for name, path in (("template", a.template), ("texture", a.texture))},
        "output_sha256": hashlib.sha256(a.out.read_bytes()).hexdigest()}
    a.receipt.parent.mkdir(parents=True, exist_ok=True)
    a.receipt.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
