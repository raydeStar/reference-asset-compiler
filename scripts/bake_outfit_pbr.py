# SPDX-License-Identifier: MIT
"""Bake deterministic 4K PBR derived maps (outfit_orm.png and outfit_normal.png) from the 3D garment mesh and cleaned paint.

- outfit_orm.png (linear RGB, TC_MASKS):
    R = Ambient Occlusion (3D mesh dihedral concavity + multi-ring fold occlusion + fine paint crevice cavity)
    G = Roughness (per-garment class roughness modulated by 3D convex ridge wear, concave fold damping, and hardware gloss)
    B = Metallic (brass buttons, buckles, and metallic trim features detected on the 3D surface)
- outfit_normal.png (tangent-space normal map, OpenGL Y+ convention):
    Multi-band seam, stitching, lapel, and fold relief derived from pull-push gutter-filled luminance and garment mask
    (neutral flat normal on bare skin texels so neck and hands remain smooth).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def pull_push(arr, w):
    """Fill pixels with weight 0 from the weighted pyramid of their surroundings."""
    if arr.ndim == 2:
        arr = arr[..., None]
        squeeze = True
    else:
        squeeze = False
    levels = [(arr * w[..., None], w)]
    while levels[-1][1].shape[0] > 1:
        c, ww = levels[-1]
        h, wd = c.shape[0] // 2, c.shape[1] // 2
        c2 = c[:h * 2, :wd * 2].reshape(h, 2, wd, 2, -1).sum((1, 3))
        w2 = ww[:h * 2, :wd * 2].reshape(h, 2, wd, 2).sum((1, 3))
        levels.append((c2, w2))
    filled = levels[-1][0] / np.maximum(levels[-1][1], 1e-9)[..., None]
    for c, ww in reversed(levels[:-1]):
        up = np.repeat(np.repeat(filled, 2, 0), 2, 1)[:c.shape[0], :c.shape[1]]
        own = c / np.maximum(ww, 1e-9)[..., None]
        filled = np.where((ww > 0)[..., None], own, up)
    return filled[..., 0] if squeeze else filled


def height_to_normal(h, strength):
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5
    n = np.stack([-dx * strength, dy * strength, np.ones_like(h)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-12
    return (np.clip(n * 0.5 + 0.5, 0, 1) * 255.0 + 0.5).astype(np.uint8)


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--islands', type=Path, required=True)
    p.add_argument('--basecolor', type=Path, required=True)
    p.add_argument('--mask', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--normal-strength', type=float, default=6.0)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    d = np.load(a.islands)
    loop_uv, loop_vert = d['loop_uv'], d['loop_vert']
    starts, totals = d['loop_start'], d['loop_total']
    centre, normal = d['centre'], d['normal']
    area = np.maximum(d['area'], 1e-8)
    F = len(starts)

    base = np.asarray(Image.open(a.basecolor).convert('RGB'), dtype=np.float64) / 255.0
    S = base.shape[0]
    mask = np.asarray(Image.open(a.mask).convert('RGB').resize((S, S), Image.NEAREST), dtype=np.float64) / 255.0

    # 1. Rasterize face IDs per texel (with polygon outline + centroid stamp)
    labels_img = Image.new('I', (S, S), -1)
    draw = ImageDraw.Draw(labels_img)
    centre_px = np.zeros((F, 2))
    for f in range(F):
        uv = loop_uv[starts[f]:starts[f] + totals[f]]
        pts = np.stack([uv[:, 0] * S, (1.0 - uv[:, 1]) * S], -1)
        centre_px[f] = pts.mean(0)
        q_pts = [tuple(q) for q in pts]
        draw.polygon(q_pts, fill=f, outline=f)
    labels = np.asarray(labels_img, dtype=np.int32).copy()
    cp = np.clip(centre_px.astype(int), 0, S - 1)
    labels[cp[:, 1], cp[:, 0]] = np.arange(F, dtype=np.int32)
    own = labels >= 0
    tex_face = np.maximum(labels, 0)

    # 2. Build 3D mesh adjacency and dihedral curvature (concavity & convexity)
    edges = defaultdict(list)
    for f in range(F):
        vs = loop_vert[starts[f]:starts[f] + totals[f]]
        for k in range(len(vs)):
            e = (min(vs[k], vs[(k + 1) % len(vs)]), max(vs[k], vs[(k + 1) % len(vs)]))
            edges[e].append(f)
    pairs = np.array([fs for fs in edges.values() if len(fs) == 2], dtype=np.int64)
    i_idx, j_idx = pairs[:, 0], pairs[:, 1]
    d_vec = centre[j_idx] - centre[i_idx]
    d_len = np.maximum(np.linalg.norm(d_vec, axis=1), 1e-6)
    d_dir = d_vec / d_len[:, None]
    # Positive when normals diverge (convex ridge), negative when normals converge (concave fold/valley)
    dihedral = np.sum((normal[j_idx] - normal[i_idx]) * d_dir, axis=1)

    face_concavity = np.zeros(F, dtype=np.float64)
    face_convexity = np.zeros(F, dtype=np.float64)
    deg = np.zeros(F, dtype=np.float64)
    conc_e = np.clip(-dihedral, 0.0, 1.5)
    conv_e = np.clip(dihedral, 0.0, 1.5)
    np.add.at(face_concavity, i_idx, conc_e)
    np.add.at(face_concavity, j_idx, conc_e)
    np.add.at(face_convexity, i_idx, conv_e)
    np.add.at(face_convexity, j_idx, conv_e)
    np.add.at(deg, i_idx, 1.0)
    np.add.at(deg, j_idx, 1.0)
    face_concavity /= np.maximum(deg, 1.0)
    face_convexity /= np.maximum(deg, 1.0)

    def smooth_on_mesh(vals, rings=4):
        cur = vals.copy()
        for _ in range(rings):
            acc = cur * area
            w = area.copy()
            np.add.at(acc, i_idx, cur[j_idx] * area[j_idx])
            np.add.at(w, i_idx, area[j_idx])
            np.add.at(acc, j_idx, cur[i_idx] * area[i_idx])
            np.add.at(w, j_idx, area[i_idx])
            cur = acc / np.maximum(w, 1e-12)
        return cur

    conc_broad = smooth_on_mesh(face_concavity, rings=5)
    conv_broad = smooth_on_mesh(face_convexity, rings=3)
    # Downward-facing under-surfaces (under collar, under lapels, inside coat hem) receive ambient shadow
    down_occ = np.clip(-normal[:, 2] * 0.22, 0.0, 0.18)
    face_ao = np.clip(1.0 - 0.55 * face_concavity - 0.65 * conc_broad - down_occ, 0.42, 1.0)
    face_wear = np.clip(0.5 * face_convexity + 0.7 * conv_broad, 0.0, 1.0)

    # 3. Compute pull-push-filled luminance in UV space so filters never step across island gutters
    lum = 0.2126 * base[..., 0] + 0.7152 * base[..., 1] + 0.0722 * base[..., 2]
    lum_filled = pull_push(lum, own.astype(np.float64))
    fine_hp = lum_filled - ndimage.gaussian_filter(lum_filled, sigma=2.5)
    meso_hp = lum_filled - ndimage.gaussian_filter(lum_filled, sigma=10.0)

    r_leather = mask[..., 0]
    g_cloth = mask[..., 1]
    b_fabric = mask[..., 2]
    garment_w = np.clip(r_leather + g_cloth + b_fabric, 0.0, 1.0)
    skin_w = 1.0 - garment_w

    # 4. Assemble ORM channels
    ao_3d = face_ao[tex_face]
    wear_3d = face_wear[tex_face]
    cavity_2d = np.clip(1.0 + 1.6 * np.minimum(fine_hp, 0.0) + 0.9 * np.minimum(meso_hp, 0.0), 0.40, 1.0)
    ao_garment = np.clip(ao_3d * cavity_2d, 0.35, 1.0)
    ao = ao_garment * garment_w + np.clip(0.92 + 0.08 * ao_3d, 0.85, 1.0) * skin_w

    # Detect metallic hardware features (brass buttons/buckles & bright cyan/silver trim on garment)
    max_c = base.max(axis=-1)
    min_c = base.min(axis=-1)
    sat = (max_c - min_c) / np.maximum(max_c, 1e-4)
    # Warm brass/gold highlights or bright cyan/silver studs on garment
    is_brass = (garment_w > 0.5) & (lum > 0.24) & (sat > 0.32) & (base[..., 0] > base[..., 2] * 1.25)
    is_cyan_stud = (garment_w > 0.5) & (lum > 0.22) & (sat > 0.28) & (base[..., 2] > base[..., 0] * 1.25) & (fine_hp > 0.02)
    metallic_raw = np.where(is_brass | is_cyan_stud, 0.82, 0.0)
    metallic = ndimage.gaussian_filter(metallic_raw, sigma=0.8) * garment_w

    # Roughness per class + convex wear gloss + concave fold damping + metallic hardware gloss
    base_rough = (0.58 * r_leather + 0.86 * g_cloth + 0.80 * b_fabric + 0.52 * skin_w)
    ridge_highlight = np.clip(wear_3d * 0.5 + np.maximum(fine_hp, 0.0) * 2.2, 0.0, 1.0)
    rough = base_rough - (0.18 * r_leather + 0.08 * g_cloth) * ridge_highlight + 0.10 * (1.0 - ao) * garment_w
    rough = np.where(metallic > 0.25, 0.30, rough)
    rough = np.clip(rough, 0.22, 0.96)

    orm = np.stack([ao, rough, metallic], axis=-1)
    orm_filled = pull_push(orm, own.astype(np.float64))
    orm_u8 = np.clip(orm_filled * 255.0 + 0.5, 0, 255).astype(np.uint8)
    orm_path = a.out / 'outfit_orm.png'
    Image.fromarray(orm_u8).save(orm_path)

    # 5. Tangent-space relief normal map (masked to 0 on bare skin so neck/hands stay smooth)
    garment_filled = pull_push(garment_w, own.astype(np.float64))
    height = (0.65 * fine_hp + 0.35 * meso_hp + 0.15 * metallic) * garment_filled
    normal_u8 = height_to_normal(height, a.normal_strength)
    normal_path = a.out / 'outfit_normal.png'
    Image.fromarray(normal_u8).save(normal_path)

    report = {
        'stage': 'bake_outfit_pbr',
        'islands': str(a.islands),
        'islands_sha256': sha(a.islands),
        'basecolor': str(a.basecolor),
        'basecolor_sha256': sha(a.basecolor),
        'mask': str(a.mask),
        'mask_sha256': sha(a.mask),
        'script_sha256': sha(__file__),
        'normal_strength': a.normal_strength,
        'ao_mean': round(float(ao[own].mean()), 4),
        'ao_p05': round(float(np.percentile(ao[own], 5)), 4),
        'roughness_mean': round(float(rough[own].mean()), 4),
        'metallic_fraction': round(float((metallic[own] > 0.25).mean()), 5),
        'outputs': {
            'outfit_orm.png': sha(orm_path),
            'outfit_normal.png': sha(normal_path),
        },
        'production_ready': False,
    }
    (a.out / 'pbr.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
