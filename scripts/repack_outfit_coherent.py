# SPDX-License-Identifier: MIT
"""Rearrange and optionally scale a face-island garment atlas so neighbours in the texture are neighbours on the body.

A scanned garment unwrapped into thousands of tiny islands mixes unrelated colours in every mip level below
the top one: the GPU's 2x2 averages blend a navy coat island with the orange skin or tan leather island packed
beside it, and the coat reads as speckled at play distance. Re-unwrapping such a mesh (folds, slivers,
overlapping layers) distorts it; this keeps every island's shape exactly as it is and only moves and uniformly
scales it by an integer factor (--scale, default 2 = 4x texel area):

  1. islands are grouped by garment class (the outfit stage's mask: cloth, leather, red fabric, skin) and
     ordered along a Morton curve through their 3D centroids;
  2. they are skyline-packed in that order at integer scale k (--scale) and whole-pixel offsets, so every
     source texel becomes an exact k x k block (zero resampling blur, zero colour shift);
  3. gutters are filled pull-push from the islands around them, which are now the same material.

  python scripts/repack_outfit_coherent.py --blend <character.blend> --object <outfit object>
      --basecolor <body_basecolor.png> --mask <garment_mask.png> --out <fresh dir>
      [--blender <exe>] [--pad 2] [--scale 2] [--stage-dir <outfit-paint dir>]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_dilation, distance_transform_edt

HERE = Path(__file__).resolve().parent
CLASSES = ['cloth', 'leather', 'fabric', 'skin']       # mask G, R, B, none


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def morton3(q):
    """Interleave 10-bit integer coordinates (N x 3) into Morton codes."""
    def spread(v):
        v = v.astype(np.uint64) & 0x3FF
        v = (v | (v << 16)) & 0x030000FF
        v = (v | (v << 8)) & 0x0300F00F
        v = (v | (v << 4)) & 0x030C30C3
        v = (v | (v << 2)) & 0x09249249
        return v
    return spread(q[:, 0]) | (spread(q[:, 1]) << 1) | (spread(q[:, 2]) << 2)


def raster_labels(tri_px, island, size):
    """Pixel -> island id (-1 none), drawing strictly polygon interiors so old-UV neighbours never bleed."""
    img = Image.new('I', (size, size), -1)
    draw = ImageDraw.Draw(img)
    for t, i in zip(tri_px, island):
        pts = [tuple(p) for p in t]
        draw.polygon(pts, fill=int(i))
    return np.asarray(img, dtype=np.int32).copy()


def pull_push(rgb, w):
    """Fill pixels with weight 0 from the weighted pyramid of their surroundings."""
    levels = [(rgb * w[..., None], w)]
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
    return filled


def mip_contamination(img, labels, tri_px, levels=(3, 4)):
    """Mean |colour at mip k - the triangle's own colour| over triangles, k in levels (0-255 units)."""
    f = img.astype(np.float64)
    out = {}
    cx = np.clip(tri_px.mean(1).astype(int), 0, img.shape[0] - 1)
    own = f[cx[:, 1], cx[:, 0]]
    for k in levels:
        s = 2 ** k
        h = img.shape[0] // s
        mip = f[:h * s, :h * s].reshape(h, s, h, s, -1).mean((1, 3))
        sampled = mip[np.clip(cx[:, 1] // s, 0, h - 1), np.clip(cx[:, 0] // s, 0, h - 1)]
        out[f'mip{k}'] = round(float(np.abs(sampled - own).mean()), 3)
    return out


def clean_collar_bleed(base, mask, tri_px, tri_centre, tri_normal):
    """Remove hair/skin projection bleed on the outer back collar rim and fix misclassified side-neck skin ramp masks."""
    S = base.shape[0]
    base = base.copy()
    mask = mask.copy()
    cpx = np.clip(tri_px.mean(1).astype(int), 0, S - 1)

    # 1. Sample navy collar median colour on back collar (y > 0.06, 1.48 < z < 1.535, |x| < 0.06)
    back_ref = (tri_centre[:, 1] > 0.06) & (tri_centre[:, 2] > 1.48) & (tri_centre[:, 2] < 1.535) & (np.abs(tri_centre[:, 0]) < 0.06)
    ref_rgb = base[cpx[back_ref, 1], cpx[back_ref, 0]]
    valid_navy = (ref_rgb[:, 0] < 90) & (ref_rgb[:, 2] >= ref_rgb[:, 0])
    navy_med = np.median(ref_rgb[valid_navy], axis=0).astype(np.uint8) if valid_navy.any() else np.array([42, 44, 58], dtype=np.uint8)

    # Replace warm hair/skin/shirt bleed on high back and side coat collar (z > 1.488)
    back_rim = np.flatnonzero(
        ((tri_centre[:, 1] > 0.04) & (tri_centre[:, 2] > 1.53) & (np.abs(tri_centre[:, 0]) < 0.085))
        | ((tri_centre[:, 2] >= 1.488) & (np.abs(tri_centre[:, 0]) >= 0.072) & (tri_centre[:, 1] >= -0.038))
    )
    for f in back_rim:
        t = tri_px[f]
        x0 = max(0, int(np.floor(t[:, 0].min())) - 2)
        x1 = min(S - 1, int(np.ceil(t[:, 0].max())) + 2)
        y0 = max(0, int(np.floor(t[:, 1].min())) - 2)
        y1 = min(S - 1, int(np.ceil(t[:, 1].max())) + 2)
        patch = base[y0:y1 + 1, x0:x1 + 1]
        warm = (patch[..., 0].astype(int) > 95) & (patch[..., 0].astype(int) > patch[..., 2].astype(int) + 12)
        if warm.any():
            patch[warm] = navy_med
            base[y0:y1 + 1, x0:x1 + 1] = patch
            mpatch = mask[y0:y1 + 1, x0:x1 + 1]
            mpatch[warm] = np.array([0, 255, 0], dtype=np.uint8)
            mask[y0:y1 + 1, x0:x1 + 1] = mpatch

    # 2. Ensure side-neck skin ramp triangles (bridging lower neck to head side-neck) have skin mask [0, 0, 0]
    side_neck_ramp = np.flatnonzero(
        (tri_centre[:, 2] >= 1.468) & (tri_centre[:, 2] <= 1.520)
        & (np.abs(tri_centre[:, 0]) <= 0.048)
        & (tri_centre[:, 1] >= -0.048) & (tri_centre[:, 1] <= 0.004)
        & (tri_normal[:, 2] > 0.45) & (tri_normal[:, 1] < 0.25)
    )
    for f in side_neck_ramp:
        cx, cy = cpx[f]
        mask[cy, cx] = np.array([0, 0, 0], dtype=np.uint8)

    return base, mask


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--blend', type=Path, required=True)
    p.add_argument('--object', required=True)
    p.add_argument('--basecolor', type=Path, required=True)
    p.add_argument('--mask', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--blender', default=r'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe')
    p.add_argument('--pad', type=int, default=2, help='pixels around each island (gutter = 2 x pad)')
    p.add_argument('--scale', type=int, default=2, help='integer linear scale factor per island (default 2 = 4x area)')
    p.add_argument('--stage-dir', type=Path, help='optional upstream outfit-paint dir to copy detail normals and scale outfit-paint.json tiling')
    p.add_argument('--head-basecolor', type=Path, help='optional head_basecolor.png to harmonize throat skin at the neck seam')
    a = p.parse_args()
    if a.scale < 1:
        raise ValueError('--scale must be a positive integer')
    a.out.mkdir(parents=True, exist_ok=False)
    (a.out / 'outfit-paint').mkdir()
    islands_npz = a.out / 'islands.npz'

    def run(*x):
        subprocess.run([a.blender, '-b', '--factory-startup', str(a.blend), '--python-exit-code', '1',
                        '-P', str(HERE / 'blender' / 'outfit_uv_islands.py'), '--', *x], check=True)

    run('dump', a.object, str(islands_npz))
    d = np.load(islands_npz)
    loop_uv, loop_face, island, centre = d['loop_uv'], d['loop_face'], d['island'], d['centre']
    normal = d['normal']
    verts = d['verts']
    loop_vert = d['loop_vert']
    # Fan triangles per face, for rasterising and measuring.
    tris, tri_face = [], []
    for f, (s0, t) in enumerate(zip(d['loop_start'], d['loop_total'])):
        for k_idx in range(1, t - 1):
            tris.append((s0, s0 + k_idx, s0 + k_idx + 1))
            tri_face.append(f)
    tris, tri_face = np.array(tris), np.array(tri_face)
    tri_uv = loop_uv[tris]
    face_island = island
    island = face_island[tri_face]
    base_raw = np.asarray(Image.open(a.basecolor).convert('RGB'))
    S = base_raw.shape[0]
    mask_img = Image.open(a.mask).convert('RGB')
    mask_px = mask_img.size[0]
    mask_raw = np.asarray(mask_img.resize((S, S), Image.NEAREST))
    assert base_raw.shape[:2] == (S, S) == mask_raw.shape[:2]

    tri_px = np.stack([tri_uv[..., 0] * S, (1 - tri_uv[..., 1]) * S], -1)       # F_tri x 3 x 2, y down
    cpx = np.clip(tri_px.mean(1).astype(int), 0, S - 1)
    tri_centre = centre[tri_face]
    tri_normal = normal[tri_face]
    base, mask = clean_collar_bleed(base_raw, mask_raw, tri_px, tri_centre, tri_normal)

    # Sample reference front-throat skin median and head neck-seam skin median for seamless throat grading
    throat_ref_sel = (
        (np.abs(tri_centre[:, 0]) <= 0.028) & (tri_centre[:, 1] <= -0.020)
        & (tri_centre[:, 2] >= 1.440) & (tri_centre[:, 2] <= 1.488)
        & (mask[cpx[:, 1], cpx[:, 0]].max(1) < 64)
    )
    throat_ref_rgb = (np.median(base[cpx[throat_ref_sel, 1], cpx[throat_ref_sel, 0]], axis=0).astype(np.float64)
                      if throat_ref_sel.any() else np.array([181.0, 110.0, 62.0]))

    head_seam_rgb = None
    if a.head_basecolor and a.head_basecolor.is_file() and 'head_centre' in d and 'head_uv' in d:
        h_img = np.asarray(Image.open(a.head_basecolor).convert('RGB'))
        H_s, W_s = h_img.shape[:2]
        hc, huv = d['head_centre'], d['head_uv']
        hsel = (hc[:, 2] >= 1.470) & (hc[:, 2] <= 1.478) & (hc[:, 1] <= -0.008) & (np.abs(hc[:, 0]) <= 0.032)
        if hsel.any():
            hu = np.clip((huv[hsel, 0] * W_s).astype(int), 0, W_s - 1)
            hv = np.clip(((1.0 - huv[hsel, 1]) * H_s).astype(int), 0, H_s - 1)
            head_seam_rgb = np.median(h_img[hv, hu], axis=0).astype(np.float64)

    n = int(face_island.max()) + 1
    labels = raster_labels(tri_px, island, S)
    island_tris = [[] for _ in range(n)]
    island_cpx = [[] for _ in range(n)]
    for t_pts, (cx, cy), isl in zip(tri_px, cpx, island):
        idx = int(isl)
        island_tris[idx].append(t_pts)
        island_cpx[idx].append((int(cx), int(cy)))

    # Per island: tight source pixel box containing both triangle vertices and centroids.
    lo = np.full((n, 2), np.inf)
    hi = np.full((n, 2), -np.inf)
    np.minimum.at(lo, island, np.minimum(tri_px.min(1), cpx))
    np.maximum.at(hi, island, np.maximum(tri_px.max(1), cpx + 1))
    orig_lo = np.clip(np.floor(lo).astype(int), 0, S - 1)
    orig_hi = np.clip(np.maximum(np.ceil(hi).astype(int), orig_lo + 1), 1, S)

    k = int(a.scale)
    span = (orig_hi - orig_lo) * k
    size = span + 2 * a.pad

    m = mask[cpx[:, 1], cpx[:, 0]].astype(float) / 255
    votes = np.zeros((n, 4))
    face_cls = np.where(m.max(1) < 0.5, 3, np.array([1, 0, 2])[m.argmax(1)])   # R leather, G cloth, B fabric
    np.add.at(votes, (island, face_cls), 1)
    cls = votes.argmax(1)
    cen = np.zeros((n, 3))
    np.add.at(cen, face_island, centre)
    cen /= np.bincount(face_island, minlength=n)[:, None]
    q = ((cen - cen.min(0)) / np.ptp(cen, 0).max() * 1023).astype(np.int64)
    order = np.lexsort((morton3(q), cls))

    # Skyline packing at integer scale k, whole-pixel placement.
    place = np.zeros((n, 2), int)
    sky = np.zeros(S, int)
    cursor = 0
    for i in order:
        w, h = size[i]
        best = None
        for start in list(range(cursor, S - w + 1, 4)) + list(range(0, min(cursor, S - w + 1), 4)):
            y = int(sky[start:start + w].max())
            key = (y // 16, (start - cursor) % S)
            if best is None or key < best[0]:
                best = (key, start, y)
        _, x, y = best
        place[i] = (x, y)
        sky[x:x + w] = y + h
        cursor = x + w if x + w < S else 0
    used_h = int(sky.max())
    if used_h > S:
        raise SystemExit(f'Islands at scale {k} need {used_h} rows of {S}; reduce --scale or --pad.')

    # Clean each island's source patch of any foreign island pixels, then smoothly upsample by k.
    new_base = np.zeros_like(base)
    new_mask = np.zeros_like(mask)
    weight = np.zeros((S, S))
    dst_lo = place + a.pad
    throat_skin_islands = set()
    for i in range(n):
        x0, y0 = orig_lo[i]
        x1, y1 = orig_hi[i]
        pw, ph = x1 - x0, y1 - y0
        lbl_patch = labels[y0:y1, x0:x1]
        foreign = (lbl_patch >= 0) & (lbl_patch != i)
        if foreign.any():
            foreign = binary_dilation(foreign, iterations=1)
        poly_img = Image.new('L', (pw, ph), 0)
        pdraw = ImageDraw.Draw(poly_img)
        for t_pts in island_tris[i]:
            pts = [(float(px - x0), float(py - y0)) for px, py in t_pts]
            pdraw.polygon(pts, fill=1, outline=1)
        own = (np.asarray(poly_img, dtype=bool) & ~foreign) | (lbl_patch == i)
        if not own.any():
            for cx, cy in island_cpx[i]:
                if x0 <= cx < x1 and y0 <= cy < y1:
                    own[cy - y0, cx - x0] = True
        b_patch = base[y0:y1, x0:x1].copy()
        m_patch = mask[y0:y1, x0:x1].copy()
        # Clean dark collar bleed and baked jaw shadow on throat / side-neck skin islands
        if cls[i] == 3 and 1.430 <= cen[i, 2] <= 1.525 and cen[i, 1] <= 0.005 and abs(cen[i, 0]) <= 0.050:
            throat_skin_islands.add(i)
            m_patch[:] = 0
            dark_or_cold = (b_patch[..., 0] < 168) | ((b_patch[..., 0].astype(int) - b_patch[..., 2].astype(int)) < 48)
            if dark_or_cold.any():
                fill_rgb = np.clip(throat_ref_rgb + 0.5, 0, 255).astype(np.uint8)
                b_patch[dark_or_cold] = fill_rgb
        if not own.all() and own.any():
            ind = distance_transform_edt(~own, return_distances=False, return_indices=True)
            b_patch = b_patch[ind[0], ind[1]]
            m_patch = m_patch[ind[0], ind[1]]
        if k > 1:
            b_patch = np.asarray(Image.fromarray(b_patch).resize((pw * k, ph * k), Image.BILINEAR))
            m_patch = np.asarray(Image.fromarray(m_patch).resize((pw * k, ph * k), Image.NEAREST))
        nx0, ny0 = dst_lo[i]
        dst = (slice(ny0, ny0 + ph * k), slice(nx0, nx0 + pw * k))
        new_base[dst] = b_patch
        new_mask[dst] = m_patch
        weight[dst] = 1

    loop_island = face_island[loop_face]
    u_px = loop_uv[:, 0] * S
    v_px = (1.0 - loop_uv[:, 1]) * S
    new_u_px = dst_lo[loop_island, 0] + (u_px - orig_lo[loop_island, 0]) * k
    new_v_px = dst_lo[loop_island, 1] + (v_px - orig_lo[loop_island, 1]) * k
    new_loop_uv = np.stack([new_u_px / S, 1.0 - new_v_px / S], axis=-1)

    new_uv = new_loop_uv[tris]
    new_px = np.stack([new_uv[..., 0] * S, (1.0 - new_uv[..., 1]) * S], -1)
    new_cpx = np.clip(new_px.mean(1).astype(int), 0, S - 1)

    # Smoothly grade upper-throat skin texels to match head_seam_rgb at the neck seam using barycentric 3D Z
    throat_harmonized_tris = 0
    if head_seam_rgb is not None and throat_skin_islands:
        tri_v_z = verts[loop_vert[tris], 2]
        z_acc = np.zeros((S, S), dtype=np.float64)
        z_w = np.zeros((S, S), dtype=np.float64)
        for t_idx in range(len(tris)):
            isl = int(island[t_idx])
            if isl not in throat_skin_islands:
                continue
            throat_harmonized_tris += 1
            pts = new_px[t_idx]
            vz = tri_v_z[t_idx]
            bx0 = max(0, int(np.floor(pts[:, 0].min())) - 1)
            bx1 = min(S - 1, int(np.ceil(pts[:, 0].max())) + 1)
            by0 = max(0, int(np.floor(pts[:, 1].min())) - 1)
            by1 = min(S - 1, int(np.ceil(pts[:, 1].max())) + 1)
            gx, gy = np.meshgrid(np.arange(bx0, bx1 + 1) + 0.5, np.arange(by0, by1 + 1) + 0.5)
            det = (pts[1, 1] - pts[2, 1]) * (pts[0, 0] - pts[2, 0]) + (pts[2, 0] - pts[1, 0]) * (pts[0, 1] - pts[2, 1])
            if abs(det) < 1e-6:
                z_val = np.full_like(gx, float(vz.mean()))
                in_tri = np.ones_like(gx, dtype=bool)
            else:
                l0 = ((pts[1, 1] - pts[2, 1]) * (gx - pts[2, 0]) + (pts[2, 0] - pts[1, 0]) * (gy - pts[2, 1])) / det
                l1 = ((pts[2, 1] - pts[0, 1]) * (gx - pts[2, 0]) + (pts[0, 0] - pts[2, 0]) * (gy - pts[2, 1])) / det
                l2 = 1.0 - l0 - l1
                in_tri = (l0 >= -0.02) & (l1 >= -0.02) & (l2 >= -0.02)
                w0, w1, w2 = np.clip(l0, 0.0, 1.0), np.clip(l1, 0.0, 1.0), np.clip(l2, 0.0, 1.0)
                ws = np.maximum(w0 + w1 + w2, 1e-8)
                z_val = (w0 * vz[0] + w1 * vz[1] + w2 * vz[2]) / ws
            z_acc[by0:by1 + 1, bx0:bx1 + 1] += np.where(in_tri, z_val, 0.0)
            z_w[by0:by1 + 1, bx0:bx1 + 1] += np.where(in_tri, 1.0, 0.0)
        for isl in throat_skin_islands:
            nx0, ny0 = dst_lo[isl]
            pw_k, ph_k = span[isl]
            sl = (slice(ny0, ny0 + ph_k), slice(nx0, nx0 + pw_k))
            zw_sub = z_w[sl]
            z_sub = np.where(zw_sub > 0, z_acc[sl] / np.maximum(zw_sub, 1e-8), float(cen[isl, 2]))
            if not (zw_sub > 0).all() and (zw_sub > 0).any():
                ind_z = distance_transform_edt(zw_sub <= 0, return_distances=False, return_indices=True)
                z_sub = z_sub[ind_z[0], ind_z[1]]
            t_z = np.clip((z_sub - 1.415) / (1.434 - 1.415), 0.0, 1.0)
            w_seam = (t_z * t_z * (3.0 - 2.0 * t_z))[..., None]
            cur_rgb = new_base[sl].astype(np.float64)
            base_skin = throat_ref_rgb[None, None, :] + (cur_rgb - throat_ref_rgb[None, None, :]) * 0.15
            target_rgb = head_seam_rgb[None, None, :] + (cur_rgb - throat_ref_rgb[None, None, :]) * 0.08
            blended = (1.0 - w_seam) * base_skin + w_seam * target_rgb
            new_base[sl] = np.clip(blended + 0.5, 0, 255).astype(np.uint8)

    filled_base = pull_push(new_base.astype(np.float64), weight)
    filled_mask = pull_push(new_mask.astype(np.float64), weight)
    out_base = np.where(weight[..., None] > 0, new_base, np.clip(filled_base, 0, 255).astype(np.uint8))
    out_mask = np.where(weight[..., None] > 0, new_mask, np.clip(filled_mask, 0, 255).astype(np.uint8))

    out_base_path = a.out / 'outfit-paint' / 'body_basecolor.png'
    out_mask_path = a.out / 'outfit-paint' / 'garment_mask.png'
    Image.fromarray(out_base).save(out_base_path)
    Image.fromarray(out_mask).save(out_mask_path)

    if a.stage_dir and a.stage_dir.is_dir():
        for detail_name in ('leather_normal.png', 'weave_normal.png'):
            src_detail = a.stage_dir / detail_name
            if src_detail.is_file():
                shutil.copy2(src_detail, a.out / 'outfit-paint' / detail_name)
        src_rec = a.stage_dir / 'outfit-paint.json'
        if src_rec.is_file():
            stage_data = json.loads(src_rec.read_text(encoding='utf-8'))
            if 'metres_per_uv' in stage_data:
                stage_data['metres_per_uv'] = round(float(stage_data['metres_per_uv']) / k, 5)
            if 'tiling' in stage_data:
                stage_data['tiling'] = {tk: round(float(tv) / k, 3) for tk, tv in stage_data['tiling'].items()}
            stage_data['uv_texel_density_scale'] = float(k)
            stage_data['uv_area_scale'] = float(k * k)
            (a.out / 'outfit-paint' / 'outfit-paint.json').write_text(json.dumps(stage_data, indent=2), encoding='utf-8')

    np.savez_compressed(a.out / 'uv.npz', loop_uv=new_loop_uv)
    # Also save updated islands-repacked.npz with the new loop_uv for downstream surface stages
    repacked_dict = {key: d[key] for key in d.files}
    repacked_dict['loop_uv'] = new_loop_uv
    np.savez_compressed(a.out / 'islands-repacked.npz', **repacked_dict)

    blend_out = a.out / a.blend.name
    run('apply', a.object, str(a.out / 'uv.npz'), str(blend_out), str(out_base_path))

    non_throat = np.array([int(isl) not in throat_skin_islands for isl in island], dtype=bool)
    check = np.abs(out_base[new_cpx[non_throat, 1], new_cpx[non_throat, 0]].astype(int)
                   - base[cpx[non_throat, 1], cpx[non_throat, 0]].astype(int)).max()
    report = {
        'stage': 'repack_outfit_coherent', 'blend': str(a.blend), 'blend_sha256': sha(a.blend), 'object': a.object,
        'basecolor': str(a.basecolor), 'basecolor_sha256': sha(a.basecolor), 'mask': str(a.mask), 'mask_sha256': sha(a.mask),
        'script_sha256': sha(__file__), 'pad_px': a.pad, 'map_px': S, 'mask_source_px': mask_px, 'islands': n,
        'islands_per_class': {c: int((cls == idx).sum()) for idx, c in enumerate(CLASSES)},
        'rows_used_px': int(used_h), 'texel_density_scale': float(k), 'texel_area_scale': float(k * k),
        'face_centre_max_colour_change': int(check),
        'throat_harmonized_triangles': int(throat_harmonized_tris),
        'head_seam_rgb': [round(float(x), 1) for x in head_seam_rgb] if head_seam_rgb is not None else None,
        'mip_contamination_before': mip_contamination(base, labels, tri_px),
        'mip_contamination_after': mip_contamination(out_base, None, new_px),
        'outputs': {rel: sha(a.out / rel) for rel in ['outfit-paint/body_basecolor.png', 'outfit-paint/garment_mask.png', a.blend.name]},
        'geometry_changed': False, 'paint_resampled': False, 'production_ready': False,
    }
    (a.out / 'repack.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({key: report[key] for key in ['islands', 'islands_per_class', 'rows_used_px', 'texel_density_scale',
                                                   'face_centre_max_colour_change', 'throat_harmonized_triangles',
                                                   'mip_contamination_before', 'mip_contamination_after']}, indent=1))


if __name__ == '__main__':
    main()
