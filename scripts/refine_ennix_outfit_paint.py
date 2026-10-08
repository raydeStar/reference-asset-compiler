"""Turn the painted outfit atlas into game garment materials.

The multiview bake (paint_ennix_body.py) carries the painting's light and its
mottled print, and the unseen-texel fill leaves faceted blotches. In game the
jacket read as blotchy rubber and the scarf as red camouflage. This stage
writes what a game material needs to read leather as leather and cloth as cloth:

1. garment classes per triangle (skin, leather, cloth, red fabric) from the
   painted colour (Lab rules), then a majority vote over mesh neighbours;
2. a cleaned albedo: inside each garment the colour is low-passed (normalized
   convolution weighted by the bake coverage, so the fill's facets barely feed
   it), its baked light is compressed toward the garment's median, and only a
   part of the painted detail is kept. Skin texels are copied unchanged, so the
   hands and neck still match the face;
3. an RGB garment mask (R leather, G cloth, B red fabric; skin = 1 - R - G - B);
4. tileable detail normals made here with numpy (leather pebble grain, plain
   weave), so no third-party texture is involved; and
5. the UV scale, so the game material tiles the detail at a real size.

Usage:
  python scripts/refine_ennix_outfit_paint.py <body.npz> <body_basecolor.png> <coverage.png> <out_dir>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage, sparse
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from reference_asset_compiler import view_projection as vp  # noqa: E402

SKIN, LEATHER, CLOTH, FABRIC = 0, 1, 2, 3
NAMES = ["skin", "leather", "cloth", "fabric"]

DEFAULTS = {
    # Lab rules on each triangle's mean painted colour (sRGB, D65).
    "skin_min_L": 44.0, "skin_min_chroma": 14.0, "skin_hue": [40.0, 80.0],
    "fabric_min_a": 18.0, "fabric_max_hue": 42.0, "fabric_min_chroma": 22.0,
    "cloth_max_chroma": 9.0,
    # Cloth (shirt and vest) only on the front of the torso: elsewhere a dark, grey patch is worn leather.
    "cloth_box_m": {"abs_x": 0.17, "z": [0.17, 0.62], "max_y": 0.02},
    "cloth_max_L": 27.0,  # the vest is darker than the jacket panels beside it
    # Bare skin in the outfit mesh: the forearms (rolled sleeves), hands and neck only.
    "skin_region_m": {"min_abs_x": 0.58, "neck_abs_x": 0.09, "neck_min_z": 0.58},
    "skin_region_min_L": 34.0,  # shadowed forearm undersides are darker than lit skin
    "hands_beyond_abs_x_m": 0.8,
    "vote_iterations": 8,
    # Albedo clean-up per garment: low-pass radius (m on the surface, via the UV scale),
    # the share of painted detail kept, and how far the baked light is compressed (1 = none).
    "lowpass_m": 0.06,
    # Detail is split by scale: features under fine_m (buckles, buttons, seams, stitching) are mostly kept;
    # the mid band between fine_m and the low-pass (the blotches and the print) mostly goes.
    "fine_m": 0.006,
    "fine_keep": 0.65,
    "detail_keep": {"leather": 0.3, "cloth": 0.3, "fabric": 0.25},
    "light_gamma": {"leather": 0.4, "cloth": 0.5, "fabric": 0.55},
    "unseen_weight": 0.15,
    # Where no view saw the garment, the 3D fill can carry a neighbour's colour (skin beside a sleeve):
    # pull those texels toward the garment's painted median colour.
    "unseen_to_median": 0.7,
    "mask_size": 1024,
    "normal_size": 512,
    # Detail tiles: physical size of one tile and its feature count.
    "leather_tile_m": 0.12, "leather_cells": 2600, "leather_wrinkles": 40,
    "weave_tile_m": 0.06, "weave_threads": 32,
    "seed": 20261008,
}


def srgb_to_lab(rgb):
    c = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def classify(lab, centroids, p):
    L, a, b = lab[:, 0], lab[:, 1], lab[:, 2]
    chroma = np.hypot(a, b)
    hue = np.degrees(np.arctan2(b, a))
    cls = np.full(len(lab), LEATHER)
    box = p["cloth_box_m"]
    torso = ((np.abs(centroids[:, 0]) < box["abs_x"]) & (centroids[:, 2] > box["z"][0]) & (centroids[:, 2] < box["z"][1])
             & (centroids[:, 1] < box["max_y"]))
    cls[((chroma < p["cloth_max_chroma"]) | (L < p["cloth_max_L"])) & torso] = CLOTH
    fabric = (a > p["fabric_min_a"]) & (hue < p["fabric_max_hue"]) & (chroma > p["fabric_min_chroma"])
    cls[fabric] = FABRIC
    skin = (L > p["skin_min_L"]) & (chroma > p["skin_min_chroma"]) & (hue > p["skin_hue"][0]) & (hue < p["skin_hue"][1])
    region = p["skin_region_m"]
    in_region = (np.abs(centroids[:, 0]) > region["min_abs_x"]) | (
        (np.abs(centroids[:, 0]) < region["neck_abs_x"]) & (centroids[:, 2] > region["neck_min_z"]))
    skin |= in_region & (L > p["skin_region_min_L"]) & (chroma > p["skin_min_chroma"]) & (hue > p["skin_hue"][0]) & (hue < p["skin_hue"][1])
    skin &= in_region
    cls[skin & ~fabric] = SKIN
    cls[np.abs(centroids[:, 0]) > p["hands_beyond_abs_x_m"]] = SKIN
    return cls


def vote(cls, tris, areas, iterations, locked):
    """Majority vote over edge neighbours, area weighted; locked triangles keep their class."""
    n = len(tris)
    edges = np.sort(np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]]), 1)
    owner = np.tile(np.arange(n), 3)
    key = edges[:, 0] * (tris.max() + 1) + edges[:, 1]
    order = np.argsort(key)
    key, owner = key[order], owner[order]
    same = key[1:] == key[:-1]
    i, j = owner[1:][same], owner[:-1][same]
    adj = sparse.coo_matrix((np.ones(len(i) * 2), (np.r_[i, j], np.r_[j, i])), shape=(n, n)).tocsr()
    for _ in range(iterations):
        onehot = np.zeros((n, 4))
        onehot[np.arange(n), cls] = areas
        score = adj @ onehot + onehot
        new = score.argmax(1)
        cls = np.where(locked, cls, new)
    return cls


def masked_lowpass(colour, weight, sigma):
    num = np.stack([ndimage.gaussian_filter(colour[..., c] * weight, sigma) for c in range(3)], -1)
    den = ndimage.gaussian_filter(weight, sigma)[..., None]
    return num / np.maximum(den, 1e-6), den[..., 0]


def height_to_normal(h, strength):
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5
    n = np.stack([-dx * strength, -dy * strength, np.ones_like(h)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return (np.clip(n * 0.5 + 0.5, 0, 1) * 255 + 0.5).astype(np.uint8)


def band_noise(size, lo, hi, rng):
    """Tileable noise with frequencies between lo and hi cycles per tile."""
    f = np.fft.fftfreq(size) * size
    r = np.hypot(*np.meshgrid(f, f))
    spec = (rng.standard_normal((size, size)) + 1j * rng.standard_normal((size, size))) * ((r >= lo) & (r <= hi))
    h = np.real(np.fft.ifft2(spec))
    return h / (np.abs(h).max() + 1e-9)


def worley(size, count, rng):
    pts = rng.random((count, 2)) * size
    tree = cKDTree(pts, boxsize=size)
    g = np.stack(np.meshgrid(np.arange(size) + 0.5, np.arange(size) + 0.5), -1).reshape(-1, 2)
    d, _ = tree.query(g, k=2, workers=-1)
    return d[:, 0].reshape(size, size), d[:, 1].reshape(size, size)


def leather_height(size, cells, wrinkles, rng):
    """Pebble grain: domed cells split by creases, broken by a few longer wrinkles."""
    f1, f2 = worley(size, cells, rng)
    cell = size / np.sqrt(cells)
    pebbles = (1 - np.exp(-(f2 - f1) / (0.18 * cell))) - 0.35 * (f1 / cell) ** 2
    w1, w2 = worley(size, wrinkles, rng)
    creases = 1 - np.exp(-(w2 - w1) / (0.05 * size / np.sqrt(wrinkles)))
    fine = band_noise(size, size / 8, size / 3, rng)
    # Soft, irregular pebbles: a wrapped blur rounds the cell edges (sharp ones read as reptile scales).
    pebbles = ndimage.gaussian_filter(pebbles + 0.15 * band_noise(size, 6, 24, rng), 1.6, mode="wrap")
    return pebbles + 0.35 * ndimage.gaussian_filter(creases, 1.0, mode="wrap") + 0.05 * fine


def weave_height(size, threads, rng):
    """Plain weave: warp and weft threads passing over and under each other."""
    t = np.arange(size) * threads / size
    u, v = np.meshgrid(t, t)
    i, j = np.floor(u), np.floor(v)
    fu, fv = u - i, v - j
    prof_u = np.sqrt(np.clip(1 - (2 * fu - 1) ** 2, 0, 1))
    prof_v = np.sqrt(np.clip(1 - (2 * fv - 1) ** 2, 0, 1))
    thick_i = 1 + 0.12 * rng.standard_normal(threads)[i.astype(int) % threads]
    thick_j = 1 + 0.12 * rng.standard_normal(threads)[j.astype(int) % threads]
    warp = prof_u * thick_i * (0.65 + 0.35 * np.cos(np.pi * (v + i)))
    weft = prof_v * thick_j * (0.65 + 0.35 * np.cos(np.pi * (u + j + 1)))
    fibre = band_noise(size, size / 6, size / 2, rng)
    return np.maximum(warp, weft) + 0.06 * fibre


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("mesh")
    ap.add_argument("basecolor")
    ap.add_argument("coverage")
    ap.add_argument("out")
    ap.add_argument("--params", help="JSON overriding DEFAULTS")
    a = ap.parse_args()
    p = dict(DEFAULTS)
    if a.params:
        p.update(json.loads(Path(a.params).read_text()))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(p["seed"])

    z = np.load(a.mesh)
    verts, tris, uv, tris_uv = z["verts"], z["tris"], z["uv"], z["tris_uv"]
    tex = np.asarray(Image.open(a.basecolor).convert("RGB")).astype(np.float32) / 255.0
    size = tex.shape[0]
    cov = np.asarray(Image.open(a.coverage).convert("L")).astype(np.float64) / 255.0
    if cov.shape != tex.shape[:2]:
        cov = np.asarray(Image.fromarray((cov * 255).astype(np.uint8)).resize(tex.shape[1::-1], Image.BILINEAR)) / 255.0

    # UV scale: surface metres per UV unit.
    e1, e2 = verts[tris[:, 1]] - verts[tris[:, 0]], verts[tris[:, 2]] - verts[tris[:, 0]]
    areas = 0.5 * np.linalg.norm(np.cross(e1, e2), axis=1)
    t = uv[tris_uv]
    uv_areas = 0.5 * np.abs((t[:, 1, 0] - t[:, 0, 0]) * (t[:, 2, 1] - t[:, 0, 1]) - (t[:, 2, 0] - t[:, 0, 0]) * (t[:, 1, 1] - t[:, 0, 1]))
    metres_per_uv = float(np.sqrt(areas.sum() / uv_areas.sum()))

    tri_id, _ = vp.uv_rasterize(uv, tris_uv, size)
    valid = tri_id >= 0
    lab = srgb_to_lab(tex)
    ids = tri_id[valid]
    counts = np.bincount(ids, minlength=len(tris))
    mean_lab = np.stack([np.bincount(ids, lab[valid][:, c], len(tris)) for c in range(3)], 1) / np.maximum(counts, 1)[:, None]
    centroids = verts[tris].mean(1)
    cls = classify(mean_lab, centroids, p)
    locked = (np.abs(centroids[:, 0]) > p["hands_beyond_abs_x_m"]) | (counts == 0)
    cls = vote(cls, tris, areas, p["vote_iterations"], locked)

    # Per-texel class; gutters take the nearest covered texel's class.
    texel_cls = np.where(valid, cls[np.maximum(tri_id, 0)], -1)
    _, (iy, ix) = ndimage.distance_transform_edt(~valid, return_indices=True)
    texel_cls = texel_cls[iy, ix]
    onehot = np.stack([(texel_cls == c).astype(np.float32) for c in range(4)], -1)
    soft = np.stack([ndimage.gaussian_filter(onehot[..., c], 1.2) for c in range(4)], -1)
    soft /= soft.sum(-1, keepdims=True)

    # Albedo: low-pass at a quarter resolution (fast), per garment, weighted to real paint.
    q = 4
    small = size // q
    lin = tex
    sigma = p["lowpass_m"] / metres_per_uv * small
    clean = tex.copy()
    record_cls = {}
    cov_soft = np.clip(ndimage.gaussian_filter(cov, 2.0), 0, 1)
    fine_sigma = p["fine_m"] / metres_per_uv * size
    smooth = np.stack([ndimage.gaussian_filter(tex[..., k], fine_sigma) for k in range(3)], -1)
    fine = (tex - smooth) * (p["fine_keep"] * cov_soft)[..., None]
    for c in (LEATHER, CLOTH, FABRIC):
        name = NAMES[c]
        inside = onehot[..., c]
        if inside.sum() == 0:
            continue
        w = inside * (p["unseen_weight"] + (1 - p["unseen_weight"]) * cov)
        w_small = w.reshape(small, q, small, q).mean((1, 3))
        col_small = (lin * w[..., None]).reshape(small, q, small, q, 3).sum((1, 3)) / np.maximum(w.reshape(small, q, small, q).sum((1, 3)), 1e-6)[..., None]
        low_small, _ = masked_lowpass(col_small, w_small, sigma)
        low = np.stack([np.asarray(Image.fromarray(low_small[..., k].astype(np.float32)).resize((size, size), Image.BILINEAR)) for k in range(3)], -1)
        # Compress the baked light toward the garment's median luminance (keeps hue and saturation).
        y = low @ np.array([0.2126, 0.7152, 0.0722])
        sel = inside > 0.5
        y_med = float(np.median(y[sel]))
        gamma = p["light_gamma"][name]
        y_new = y_med * (np.maximum(y, 1e-4) / y_med) ** gamma
        y_new *= y[sel].mean() / y_new[sel].mean()  # the garment's mean stays the painting's
        low_adj = low * (y_new / np.maximum(y, 1e-4))[..., None]
        seen = sel & (cov > 0.5)
        median = np.median(low_adj[seen if seen.any() else sel], 0)
        unseen = (p["unseen_to_median"] * (1 - cov_soft))[..., None]
        low_adj = low_adj * (1 - unseen) + median * unseen
        detail = (smooth - low) * (p["detail_keep"][name] * cov_soft)[..., None] + fine
        garment = np.clip(low_adj + detail, 0, 1)
        clean = clean * (1 - soft[..., c:c + 1]) + garment * soft[..., c:c + 1]
        record_cls[name] = {"triangles": int((cls == c).sum()), "area_m2": round(float(areas[cls == c].sum()), 4),
                            "median_luminance": round(y_med, 4), "light_gamma": gamma, "detail_keep": p["detail_keep"][name]}
    record_cls["skin"] = {"triangles": int((cls == SKIN).sum()), "area_m2": round(float(areas[cls == SKIN].sum()), 4),
                          "albedo": "unchanged"}
    # Skin texels are the bake's own colour, exactly.
    skin_hard = texel_cls == SKIN
    clean[skin_hard] = tex[skin_hard]
    Image.fromarray((np.clip(clean, 0, 1) * 255 + 0.5).astype(np.uint8)).save(out / "body_basecolor.png")

    # Garment mask: R leather, G cloth, B red fabric, at mask_size.
    ms = p["mask_size"]
    mask = np.stack([soft[..., LEATHER], soft[..., CLOTH], soft[..., FABRIC]], -1)
    mask = mask.reshape(ms, size // ms, ms, size // ms, 3).mean((1, 3))
    Image.fromarray((np.clip(mask, 0, 1) * 255 + 0.5).astype(np.uint8)).save(out / "garment_mask.png")

    # Detail normals.
    ns = p["normal_size"]
    lh = leather_height(ns, p["leather_cells"], p["leather_wrinkles"], rng)
    Image.fromarray(height_to_normal(lh, 6.0)).save(out / "leather_normal.png")
    wh = weave_height(ns, p["weave_threads"], rng)
    Image.fromarray(height_to_normal(wh, 2.5)).save(out / "weave_normal.png")

    record = {
        "stage": "refine_ennix_outfit_paint",
        "inputs": {k: {"path": str(Path(v).resolve()), "sha256": hashlib.sha256(Path(v).read_bytes()).hexdigest()}
                   for k, v in (("mesh", a.mesh), ("basecolor", a.basecolor), ("coverage", a.coverage))},
        "metres_per_uv": round(metres_per_uv, 5),
        # Material tiling: detail tiles per UV unit.
        "tiling": {"leather": round(metres_per_uv / p["leather_tile_m"], 3), "weave": round(metres_per_uv / p["weave_tile_m"], 3)},
        "classes": record_cls,
        "mask": "garment_mask.png: R leather, G cloth, B red fabric; skin = 1 - R - G - B",
        "params": p,
    }
    (out / "outfit-paint.json").write_text(json.dumps(record, indent=2))
    print(json.dumps({k: record[k] for k in ("metres_per_uv", "tiling", "classes")}, indent=2))


if __name__ == "__main__":
    main()
