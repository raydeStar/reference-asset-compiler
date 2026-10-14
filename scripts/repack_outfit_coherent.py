# SPDX-License-Identifier: MIT
"""Rearrange a face-island garment atlas so neighbours in the texture are neighbours on the body.

A scanned garment unwrapped into thousands of tiny islands mixes unrelated colours in every mip level below
the top one: the GPU's 2x2 averages blend a navy coat island with the orange skin or tan leather island packed
beside it, and the coat reads as speckled at play distance. Re-unwrapping such a mesh (folds, slivers,
overlapping layers) distorts it; this keeps every island exactly as it is and only moves it:

  1. islands are grouped by garment class (the outfit stage's mask: cloth, leather, red fabric, skin) and
     ordered along a Morton curve through their 3D centroids;
  2. they are shelf-packed in that order at their original texel density, at whole-pixel offsets, so the
     paint moves as exact pixel copies (no resampling);
  3. gutters are filled pull-push from the islands around them, which are now the same material.

  python scripts/repack_outfit_coherent.py --blend <character.blend> --object <outfit object>
      --basecolor <body_basecolor.png> --mask <garment_mask.png> --out <fresh dir> [--blender <exe>] [--pad 3]

Writes <out>/outfit-paint/{body_basecolor,garment_mask}.png, <out>/<blend name> with the new UVs,
<out>/repack.json (hashes, settings, island counts, and the mip-contamination measurement before/after:
the mean colour error a triangle shows at mip 3 and 4 against its own colour). Other objects and maps are
untouched; export with scripts/blender/export_ue5_character.py.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

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
    """Pixel -> island id (-1 none), by pixel centre, triangles drawn in island order."""
    img = Image.new('I', (size, size), -1)
    draw = ImageDraw.Draw(img)
    for t, i in zip(tri_px, island):
        draw.polygon([tuple(p) for p in t], fill=int(i))
    return np.asarray(img, dtype=np.int32)


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


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--blend', type=Path, required=True)
    p.add_argument('--object', required=True)
    p.add_argument('--basecolor', type=Path, required=True)
    p.add_argument('--mask', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--blender', default=r'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe')
    p.add_argument('--pad', type=int, default=3, help='pixels around each island (gutter = 2 x pad)')
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    (a.out / 'outfit-paint').mkdir()
    islands_npz = a.out / 'islands.npz'
    def run(*x):
        subprocess.run([a.blender, '-b', '--factory-startup', str(a.blend), '--python-exit-code', '1',
                        '-P', str(HERE / 'blender' / 'outfit_uv_islands.py'), '--', *x], check=True)
    run('dump', a.object, str(islands_npz))
    d = np.load(islands_npz)
    loop_uv, loop_face, island, centre = d['loop_uv'], d['loop_face'], d['island'], d['centre']
    # Fan triangles per face, for rasterising and measuring.
    tris, tri_face = [], []
    for f, (s0, t) in enumerate(zip(d['loop_start'], d['loop_total'])):
        for k in range(1, t - 1):
            tris.append((s0, s0 + k, s0 + k + 1))
            tri_face.append(f)
    tris, tri_face = np.array(tris), np.array(tri_face)
    tri_uv = loop_uv[tris]
    face_island = island
    island = face_island[tri_face]
    base = np.asarray(Image.open(a.basecolor).convert('RGB'))
    S = base.shape[0]
    # The mask moves with the paint at the paint's resolution (nearest upsample keeps its classes crisp).
    mask_img = Image.open(a.mask).convert('RGB')
    mask_px = mask_img.size[0]
    mask = np.asarray(mask_img.resize((S, S), Image.NEAREST))
    assert base.shape[:2] == (S, S) == mask.shape[:2]
    tri_px = np.stack([tri_uv[..., 0] * S, (1 - tri_uv[..., 1]) * S], -1)       # F x 3 x 2, y down
    n = int(face_island.max()) + 1
    labels = raster_labels(tri_px, island, S)

    # Per island: pixel box, class, centroid.
    lo = np.full((n, 2), np.inf)
    hi = np.full((n, 2), -np.inf)
    np.minimum.at(lo, island, tri_px.min(1))
    np.maximum.at(hi, island, tri_px.max(1))
    box_lo = np.floor(lo).astype(int) - a.pad
    box_hi = np.ceil(hi).astype(int) + a.pad
    size = box_hi - box_lo
    cpx = np.clip(tri_px.mean(1).astype(int), 0, S - 1)
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

    # Skyline packing at original density, whole-pixel placement: each island, in curve order, drops to the
    # lowest spot it fits, searched from where the previous island ended so the order stays local.
    place = np.zeros((n, 2), int)
    sky = np.zeros(S, int)
    cursor = 0
    for i in order:
        w, h = size[i]
        best = None
        for start in list(range(cursor, S - w + 1, 4)) + list(range(0, min(cursor, S - w + 1), 4)):
            y = int(sky[start:start + w].max())
            # prefer low, then close to the cursor (keeps neighbours in the curve next to each other)
            key = (y // 16, (start - cursor) % S)
            if best is None or key < best[0]:
                best = (key, start, y)
        _, x, y = best
        place[i] = (x, y)
        sky[x:x + w] = y + h
        cursor = x + w if x + w < S else 0
    used_h = int(sky.max())
    if used_h > S:
        raise SystemExit(f'Islands need {used_h} rows of {S}; a scale step is not implemented (use a larger map).')

    # Move pixels: each island's own labelled pixels, exact copies.
    new_base = np.zeros_like(base)
    new_mask = np.zeros_like(mask)
    weight = np.zeros((S, S))
    shift = place - box_lo
    for i in range(n):
        x0, y0 = np.maximum(box_lo[i], 0)
        x1, y1 = np.minimum(box_hi[i], S)
        own = labels[y0:y1, x0:x1] == i
        nx0, ny0 = x0 + shift[i][0], y0 + shift[i][1]
        dst = (slice(ny0, ny0 + (y1 - y0)), slice(nx0, nx0 + (x1 - x0)))
        new_base[dst][own] = base[y0:y1, x0:x1][own]
        new_mask[dst][own] = mask[y0:y1, x0:x1][own]
        weight[dst][own] = 1
    filled_base = pull_push(new_base.astype(np.float64), weight)
    filled_mask = pull_push(new_mask.astype(np.float64), weight)
    out_base = np.where(weight[..., None] > 0, new_base, np.clip(filled_base, 0, 255).astype(np.uint8))
    out_mask = np.where(weight[..., None] > 0, new_mask, np.clip(filled_mask, 0, 255).astype(np.uint8))
    Image.fromarray(out_base).save(a.out / 'outfit-paint' / 'body_basecolor.png')
    Image.fromarray(out_mask).save(a.out / 'outfit-paint' / 'garment_mask.png')

    loop_island = face_island[loop_face]
    new_loop_uv = loop_uv.copy()
    new_loop_uv[:, 0] += shift[loop_island][:, 0] / S
    new_loop_uv[:, 1] -= shift[loop_island][:, 1] / S
    np.savez_compressed(a.out / 'uv.npz', loop_uv=new_loop_uv)
    new_uv = new_loop_uv[tris]
    new_px = np.stack([new_uv[..., 0] * S, (1 - new_uv[..., 1]) * S], -1)
    blend_out = a.out / a.blend.name
    run('apply', a.object, str(a.out / 'uv.npz'), str(blend_out))

    # Exactness: every face's own pixels are identical at their new place.
    check = np.abs(out_base[np.clip(new_px.mean(1).astype(int), 0, S - 1)[:, 1], np.clip(new_px.mean(1).astype(int), 0, S - 1)[:, 0]].astype(int)
                   - base[cpx[:, 1], cpx[:, 0]].astype(int)).max()
    report = {
        'stage': 'repack_outfit_coherent', 'blend': str(a.blend), 'blend_sha256': sha(a.blend), 'object': a.object,
        'basecolor': str(a.basecolor), 'basecolor_sha256': sha(a.basecolor), 'mask': str(a.mask), 'mask_sha256': sha(a.mask),
        'script_sha256': sha(__file__), 'pad_px': a.pad, 'map_px': S, 'mask_source_px': mask_px, 'islands': n,
        'islands_per_class': {c: int((cls == k).sum()) for k, c in enumerate(CLASSES)},
        'rows_used_px': int(used_h), 'texel_density_scale': 1.0, 'face_centre_max_colour_change': int(check),
        'mip_contamination_before': mip_contamination(base, labels, tri_px),
        'mip_contamination_after': mip_contamination(out_base, None, new_px),
        'outputs': {k: sha(a.out / k) for k in ['outfit-paint/body_basecolor.png', 'outfit-paint/garment_mask.png', a.blend.name]},
        'geometry_changed': False, 'paint_resampled': False, 'production_ready': False,
    }
    (a.out / 'repack.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ['islands', 'islands_per_class', 'rows_used_px', 'face_centre_max_colour_change',
                                             'mip_contamination_before', 'mip_contamination_after']}, indent=1))


if __name__ == '__main__':
    main()
