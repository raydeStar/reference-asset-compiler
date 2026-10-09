"""Source-derived face reprojection and continuous neck paint, without new AI images.

The original illustration is registered to the existing face by DWPose points.
Only skin is rebaked; the acquired geometry, UVs and expressions stay intact.

Per-character (Ennix-tuned): the face, mouth, neck and forehead zones are
heights and widths on the first character's conformed head (z 1.525-1.746 m).
Conformed heads share that frame (character-02's eyes sit 3 mm lower), so the
zones carry over. What came from his pictures now comes from each picture's
own landmarks (2026-10-09):

- the brow window (--brow-window landmarks, the default): his fixed pixels
  were his brows; on character-02 they were 113 px above them, and the
  fringe there was pasted onto the forehead as dark spikes;
- the forehead's clean colour is sampled where his picture shows forehead
  skin; where a fringe covers that spot, the skin between the eyes and on the
  cheeks stands in (a dark sample painted a hair-dark band with a straight
  edge across character-02's forehead);
- the painting's mouth is kept only when it is closed (--source-mouth auto):
  a grin's teeth painted onto the lips read as a grin in every expression.
See docs/CHARACTER_REBUILD.md, "Still tuned to the first character".
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.interpolate import RBFInterpolator

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from reference_asset_compiler import view_projection as vp
from paint_head_from_views import head_triangles

LUMA = np.array([0.2126, 0.7152, 0.0722])
# Ennix's brow window, fitted to his picture's brow landmarks (17-21 on his left, image left): its centre
# sits (0.09, 0.09) brow spans right of and below their mean, half 0.50 by 0.24 spans. That reproduces
# his hand-set pixels (519, 460), 82 by 39, and the other brow 5.4 px lower, to within 0.25 px.
BROW_OFFSET_SPANS, BROW_HALF_SPANS = (0.089, 0.091), (0.502, 0.239)
FIXED_BROW_WINDOW = {"centre_px": [519.0, 460.0], "half_px": [82.0, 39.0], "other_brow_dy_px": 5.4}


def mouth_open_ratio(landmarks_68):
    """Gap between the inner lips (DWPose 61-67, 62-66, 63-65) over the mouth's width (48-54)."""
    lm = np.asarray(landmarks_68, float)
    gap = np.mean([np.linalg.norm(lm[a] - lm[b]) for a, b in ((61, 67), (62, 66), (63, 65))])
    return float(gap / max(np.linalg.norm(lm[54] - lm[48]), 1e-6))


def brow_window(landmarks_68, mode="landmarks"):
    """Where the front picture's brows are: the restore's centre, half sizes and the other brow's offset (px)."""
    if mode == "fixed":
        return dict(FIXED_BROW_WINDOW)
    lm = np.asarray(landmarks_68, float)
    first, second = lm[17:22], lm[22:27]
    span = float(first[:, 0].max() - first[:, 0].min())
    centre = first.mean(0) + np.array(BROW_OFFSET_SPANS) * span
    return {"centre_px": centre.round(2).tolist(), "half_px": (np.array(BROW_HALF_SPANS) * span).round(2).tolist(),
            "other_brow_dy_px": round(float(second[:, 1].mean() - first[:, 1].mean()), 2)}


def skin_or_probe(sample, probes, hair_luma=0.6):
    """`sample` unless it is hair (darker than hair_luma of the probes' skin): then the probes' median."""
    skin = np.median(np.asarray(probes, float), axis=0)
    if float(np.asarray(sample) @ LUMA) < hair_luma * float(skin @ LUMA):
        return skin, True
    return np.asarray(sample, float), False


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--template", required=True)
    p.add_argument("--head", required=True)
    p.add_argument("--receipt", required=True)
    p.add_argument("--texture", required=True)
    p.add_argument("--original-landmarks", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--mode", choices=("full", "accents"), default="accents")
    p.add_argument("--restore-brows", action="store_true", help="restore fine source brow paint over the old mirrored blocks")
    p.add_argument("--brow-window", choices=("landmarks", "fixed"), default="landmarks",
                   help="where the brows are in the front picture: from its landmarks, or the first character's "
                        "hand-set pixels (reproduces builds before 2026-10-09)")
    p.add_argument("--source-mouth", choices=("auto", "keep", "skip"), default="auto",
                   help="keep the painting's mouth (accents mode): auto keeps it only when its lips are closed")
    p.add_argument("--open-mouth-ratio", type=float, default=0.03,
                   help="inner-lip gap over mouth width above which the painting's mouth counts as open")
    a = p.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    z = dict(np.load(a.head))
    t = np.load(a.template)
    rec = json.loads(Path(a.receipt).read_text())
    old = json.loads(Path(rec["picture"]["landmarks"]).read_text())
    orig = json.loads(Path(a.original_landmarks).read_text())
    old_lm, orig_lm = np.array(old["landmarks_68"]), np.array(orig["landmarks_68"])
    # DWPose supplies the correspondence. A smoothed TPS avoids little detector
    # disagreements becoming wrinkles -- the gentleman already has enough worries.
    warp = RBFInterpolator(old_lm / 1024, orig_lm, kernel="thin_plate_spline", smoothing=0.000003)
    old_image = vp.load_image(old["image"])
    original = vp.load_image(orig["image"])
    h, w = old_image.shape[:2]
    yy, xx = np.mgrid[:h, :w]
    flat = np.c_[xx.ravel(), yy.ravel()]
    aligned = np.zeros((len(flat), 3))
    for start in range(0, len(flat), 65536):
        aligned[start:start + 65536] = vp.sample(original, warp(flat[start:start + 65536] / 1024))
    aligned = aligned.reshape(h, w, 3)
    Image.fromarray((np.clip(aligned, 0, 1) * 255).astype(np.uint8)).save(out / "original-aligned.png")

    tex = vp.load_image(a.texture)
    size = tex.shape[0]
    tris, lt = head_triangles(z)
    tri, bary = vp.uv_rasterize(t["loop_uv"], lt, size)
    valid = tri >= 0
    pos = np.einsum("nk,nkj->nj", bary[valid], z["verts"][tris[tri[valid]]])
    reg = rec["picture"]["registration"]
    px = reg["scale_px_per_m"] * np.c_[pos[:, 0], -pos[:, 2]] @ np.array(reg["rotation"]).T + reg["translation_px"]
    col = vp.sample(aligned, px)
    x, y, height = pos.T
    # The original is low resolution. Keep its expression/colour on the face;
    # inferred side views still describe skin around the ears and back of skull.
    # Per-character (Ennix-tuned): every zone below is in his head's metres.
    alpha = np.clip((0.087 - np.abs(x + 0.002)) / 0.022, 0, 1)
    alpha *= np.clip((-0.058 - y) / 0.024, 0, 1)
    alpha *= np.clip((height - 1.577) / 0.014, 0, 1)
    alpha *= np.clip((1.746 - height) / 0.018, 0, 1)
    # Source locks above the brows are occlusion, not facial pigmentation.
    luma = col @ [0.2126, 0.7152, 0.0722]
    alpha *= np.where((height > 1.716) & (luma < 0.32), 0.0, 1.0)
    open_ratio = mouth_open_ratio(orig_lm)
    keep_mouth = a.source_mouth == "keep" or (a.source_mouth == "auto" and open_ratio <= a.open_mouth_ratio)
    if a.mode == "accents":
        # A 130-pixel face cannot replace a detailed skin map wholesale.
        # Keep the source expression at the mouth while retaining fine skin,
        # irises and inferred profile coverage from the close-up acquisition.
        # An open mouth (a grin's teeth) is not kept: on the closed lips of a
        # neutral head it reads as a grin through every expression.
        mouth = np.exp(-((x + 0.002) / 0.041) ** 6 - ((height - 1.626) / 0.022) ** 6)
        alpha *= mouth * (0.65 if keep_mouth else 0.0)
    blended = tex[valid] * (1 - alpha[:, None]) + col * alpha[:, None]
    tex[valid] = blended

    # Eliminate the nearest-texel mosaic below the jaw using a continuously
    # sampled front-neck gradient. Preserve the jaw/beard and the face itself.
    front = vp.load_image(old["image"])
    neck_col = vp.sample(front, px)
    front_neck = (np.abs(x) < 0.035) & (y < -0.07) & (height < 1.585) & (height > 1.525)
    sampled = neck_col[front_neck]
    tone = np.median(sampled, axis=0)
    # Projecting the source's large-scale neck gradient has no UV seam and no
    # dependency on how an acquisition happened to triangulate its throat.
    neck = np.clip((1.593 - height) / 0.027, 0, 1)
    neck = np.maximum(neck, np.clip((y + 0.09) / 0.025, 0, 1) * np.clip((1.65 - height) / 0.025, 0, 1))
    soft_front = ndimage.gaussian_filter(front, sigma=(20, 20, 0))
    neck_px = px.copy()
    # Take clean neck paint near the front centre, not hair/grey at the sides.
    clean_pos = pos.copy()
    clean_pos[:, 0] = np.clip(clean_pos[:, 0], -0.025, 0.025)
    neck_px = reg["scale_px_per_m"] * np.c_[clean_pos[:, 0], -clean_pos[:, 2]] @ np.array(reg["rotation"]).T + reg["translation_px"]
    smooth = vp.sample(soft_front, neck_px)
    clean_tone = np.percentile(tex[valid][(height < 1.61) & (height > 1.54)], 65, axis=0)
    smooth = 0.45 * smooth + 0.55 * clean_tone
    tex[valid] = tex[valid] * (1 - neck[:, None]) + smooth * neck[:, None]
    # Old hair-removal masks left polygon-shaped islands on the forehead.
    # This skin-only area can take a broad clean gradient sampled between brows
    # and hairline; the eyebrows themselves remain outside the repair.
    forehead = np.clip((height - 1.718) / 0.012, 0, 1) * np.clip((-y - 0.035) / 0.05, 0, 1)
    forehead *= np.clip((0.091 - np.abs(x)) / 0.014, 0, 1)
    centre_px = reg["scale_px_per_m"] * np.array([[0.0, -1.739]]) @ np.array(reg["rotation"]).T + reg["translation_px"]
    soft8 = ndimage.gaussian_filter(front, sigma=(8, 8, 0))
    skin_colour = vp.sample(soft8, centre_px)[0]
    # A fringe over that spot is hair, not forehead: then the skin between the eyes and on the cheeks.
    probes_px = np.array([old_lm[28], (old_lm[2] + old_lm[31]) / 2, (old_lm[14] + old_lm[35]) / 2])
    skin_colour, forehead_from_probes = skin_or_probe(skin_colour, vp.sample(soft8, probes_px))
    smooth_forehead = skin_colour * (0.98 + 0.035 * np.clip(-x / 0.07, -1, 1))[:, None]
    tex[valid] = tex[valid] * (1 - forehead[:, None]) + smooth_forehead * forehead[:, None]
    if a.restore_brows:
        # The old repair mirrored nearest UV texels, leaving rectangular skin
        # blocks under the brows. Use the clean source brow as an image-space
        # witness with a continuous feather instead of mirroring the UV islands.
        window = brow_window(old_lm, a.brow_window)
        (cx, cy), (hx, hy) = window["centre_px"], window["half_px"]
        brow_px = px.copy()
        centre_x = float((old_lm[21, 0] + old_lm[22, 0]) / 2)
        right = brow_px[:, 0] > centre_x
        brow_px[right, 0] = 2 * centre_x - brow_px[right, 0]
        brow_px[right, 1] -= window["other_brow_dy_px"]
        brow = np.exp(-((brow_px[:, 0] - cx) / hx) ** 8 - ((brow_px[:, 1] - cy) / hy) ** 8)
        brow *= np.clip((-y - 0.060) / 0.035, 0, 1)
        brow_colour = vp.sample(front, brow_px)
        tex[valid] = tex[valid] * (1 - brow[:, None]) + brow_colour * brow[:, None]
    tex = vp.fill_unpainted(tex, valid)
    Image.fromarray((np.clip(tex, 0, 1) * 255).astype(np.uint8)).save(out / "head_basecolor.png")
    alpha_map = np.zeros(valid.shape)
    alpha_map[valid] = alpha
    Image.fromarray((alpha_map * 255).astype(np.uint8)).save(out / "source-face-mask.png")
    record = {"source": orig["image"], "source_sha256": orig["image_sha256"],
              "source_landmarks_sha256": hashlib.sha256(Path(a.original_landmarks).read_bytes()).hexdigest(),
              "face_texels": int((alpha > 0).sum()), "neck_texels": int((neck > 0).sum()),
              "neck_tone": tone.tolist(), "geometry_changed": False,
              "source_mouth": {"mode": a.source_mouth, "open_ratio": round(open_ratio, 4),
                               "threshold": a.open_mouth_ratio, "kept": bool(keep_mouth)},
              "forehead_colour": {"srgb": np.round(skin_colour, 4).tolist(),
                                  "from": "skin probes (a fringe covers the forehead)" if forehead_from_probes
                                  else "the forehead"},
              "brow_window": ({"mode": a.brow_window, **brow_window(old_lm, a.brow_window)}
                              if a.restore_brows else None),
              "method": "DWPose correspondences, TPS image registration, UV barycentric bake; no generative image tool"}
    (out / "surface-receipt.json").write_text(json.dumps(record, indent=2))
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
