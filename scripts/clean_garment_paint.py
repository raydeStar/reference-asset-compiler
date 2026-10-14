# SPDX-License-Identifier: MIT
"""Take the projection speckle out of a painted garment, filtering on the body surface, not in UV space.

A garment painted by projecting reference pictures onto a dense, face-island atlas ends up as one flat chip
of colour per triangle (the median triangle of character-02's coat covers ~3 texels of a 4K map), each chip a
little different, plus pale smears where the painting's highlights landed. In game that reads as a spotty
coat. This works on the mesh:

  1. each face's colour is read from its own texels (sub-texel faces from their centre);
  2. faces whose hue/chroma stands out from their surroundings (stitching, buttons, emblems, piping, small
     leather pieces) are features and are kept exactly;
  3. every other face of a class is smoothed over its same-class neighbours (area-weighted, edge-aware in
     CIELAB with lightness down-weighted), which dissolves baked highlight smears and chip-to-chip noise
     while hue edges (shirt against coat, leather, stitching, brass) stay sharp;
  4. texels are rewritten in the same UV layout: smoothed colour plus the texel's own deviation, scaled by
     how squarely its face met a source painting (--view-axes): painted detail on faces the pictures saw
     head-on survives, smear stretched over grazing faces (shoulder tops, flanks) fades; gutters are refilled
     pull-push.

  python scripts/clean_garment_paint.py --islands <outfit_uv_islands.py dump .npz> --basecolor <png>
      --mask <garment_mask.png> --out <fresh dir> [--classes cloth:25:7,leather:15:6] [--view-axes 0,1,0]

--classes: class:iterations:sigma per class to clean (mask G cloth, R leather, B fabric; skin is left alone,
its material handles it). Smoothing is bilateral: a neighbour's pull falls off with its CIELAB distance, in
which lightness counts --lightness-weight as much as hue and chroma. Writes <out>/body_basecolor.png and clean.json (hashes, settings,
feature count, and the speckle metric: mean CIELAB distance between adjacent same-class faces, before/after).
The UVs and mesh do not change, so a game reimports only the texture.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

CLASS_INDEX = {'leather': 0, 'cloth': 1, 'fabric': 2, 'skin': 3}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def srgb_to_lab(rgb):
    c = rgb / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = lin @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], -1)


def lab_to_srgb(lab):
    fy = (lab[:, 0] + 16) / 116
    fx, fz = fy + lab[:, 1] / 500, fy - lab[:, 2] / 200
    f = np.stack([fx, fy, fz], -1)
    xyz = np.where(f ** 3 > 0.008856, f ** 3, (f - 16 / 116) / 7.787) * np.array([0.95047, 1.0, 1.08883])
    m = np.array([[3.2406, -1.5372, -0.4986], [-0.9689, 1.8758, 0.0415], [0.0557, -0.2040, 1.0570]])
    lin = np.clip(xyz @ m.T, 0, 1)
    c = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055)
    return np.clip(c * 255, 0, 255)


def pull_push(rgb, w):
    levels = [(rgb * w[..., None], w)]
    while levels[-1][1].shape[0] > 1:
        c, ww = levels[-1]
        h, wd = c.shape[0] // 2, c.shape[1] // 2
        levels.append((c[:h * 2, :wd * 2].reshape(h, 2, wd, 2, -1).sum((1, 3)),
                       ww[:h * 2, :wd * 2].reshape(h, 2, wd, 2).sum((1, 3))))
    filled = levels[-1][0] / np.maximum(levels[-1][1], 1e-9)[..., None]
    for c, ww in reversed(levels[:-1]):
        up = np.repeat(np.repeat(filled, 2, 0), 2, 1)[:c.shape[0], :c.shape[1]]
        filled = np.where((ww > 0)[..., None], c / np.maximum(ww, 1e-9)[..., None], up)
    return filled


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--islands', type=Path, required=True)
    p.add_argument('--basecolor', type=Path, required=True)
    p.add_argument('--mask', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--classes', default='cloth:25:7,leather:15:6',
                   help='class:iterations:sigma (CIELAB, lightness weighted by --lightness-weight)')
    p.add_argument('--lightness-weight', type=float, default=0.25)
    p.add_argument('--keep-grain', type=float, default=1.0, help='fraction of each texel\'s own deviation kept')
    p.add_argument('--view-axes', default='0,1,0',
                   help='axes the source paintings looked along (x,y,z; ";" between several). Texel detail on faces '
                        'seen at a grazing angle is projection smear and is faded (--grazing)')
    p.add_argument('--grazing', default='0.25,0.65',
                   help='|n.view| below the first fades detail to --grain-floor; above the second keeps it all')
    p.add_argument('--grain-floor', type=float, default=0.15)
    p.add_argument('--feature-de', type=float, default=10.0, help='a*b* distance from the 2-ring neighbourhood')
    p.add_argument('--feature-chroma', type=float, default=10.0, help='extra chroma over the neighbourhood')
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    d = np.load(a.islands)
    base = np.asarray(Image.open(a.basecolor).convert('RGB'))
    S = base.shape[0]
    mask = np.asarray(Image.open(a.mask).convert('RGB').resize((S, S), Image.NEAREST)).astype(float) / 255
    loop_uv, loop_vert = d['loop_uv'], d['loop_vert']
    starts, totals = d['loop_start'], d['loop_total']
    area = np.maximum(d['area'], 1e-8)     # slivers still take part
    F = len(starts)

    # Face ids per texel (texel centres), and each face's texels.
    labels = Image.new('I', (S, S), -1)
    draw = ImageDraw.Draw(labels)
    centre_px = np.zeros((F, 2))
    for f in range(F):
        uv = loop_uv[starts[f]:starts[f] + totals[f]]
        pts = np.stack([uv[:, 0] * S, (1 - uv[:, 1]) * S], -1)
        centre_px[f] = pts.mean(0)
        draw.polygon([tuple(q) for q in pts], fill=f)
    labels = np.asarray(labels, dtype=np.int64).ravel()
    flat = base.reshape(-1, 3).astype(np.float64)
    own = labels >= 0
    counts = np.bincount(labels[own], minlength=F)
    sums = np.stack([np.bincount(labels[own], flat[own, c], minlength=F) for c in range(3)], -1)
    cp = np.clip(centre_px.astype(int), 0, S - 1)
    face_rgb = np.where(counts[:, None] > 0, sums / np.maximum(counts, 1)[:, None], base[cp[:, 1], cp[:, 0]])
    m = mask[cp[:, 1], cp[:, 0]]
    face_cls = np.where(m.max(1) < 0.5, 3, m.argmax(1))     # 0 leather (R), 1 cloth (G), 2 fabric (B), 3 skin
    lab = srgb_to_lab(face_rgb)

    # Same-class face adjacency through shared edges.
    edges = defaultdict(list)
    for f in range(F):
        vs = loop_vert[starts[f]:starts[f] + totals[f]]
        for k in range(len(vs)):
            e = (min(vs[k], vs[(k + 1) % len(vs)]), max(vs[k], vs[(k + 1) % len(vs)]))
            edges[e].append(f)
    pairs = np.array([fs for fs in edges.values() if len(fs) == 2])
    same = face_cls[pairs[:, 0]] == face_cls[pairs[:, 1]]
    pairs = pairs[same]
    nbr = [[] for _ in range(F)]
    for i, j in pairs:
        nbr[i].append(j)
        nbr[j].append(i)

    def speckle(values):
        out = {}
        for name, k in CLASS_INDEX.items():
            sel = face_cls[pairs[:, 0]] == k
            if sel.any():
                dist = np.linalg.norm(values[pairs[sel, 0]] - values[pairs[sel, 1]], axis=1)
                out[name] = {'mean': round(float(dist.mean()), 3), 'p90': round(float(np.percentile(dist, 90)), 3)}
        return out

    # Neighbourhood (2-ring, area weighted) for feature detection.
    def ring_mean(values, rings=2):
        acc, w = values * area[:, None], area.copy()
        cur = values * area[:, None]
        cw = area.copy()
        for _ in range(rings):
            nxt = np.zeros_like(cur)
            nw = np.zeros_like(cw)
            for i, j in pairs:
                nxt[i] += cur[j]
                nw[i] += cw[j]
                nxt[j] += cur[i]
                nw[j] += cw[i]
            acc, w = acc + nxt, w + nw
            cur, cw = nxt, nw
        return acc / np.maximum(w, 1e-12)[:, None]
    around = ring_mean(lab)
    chroma = np.hypot(lab[:, 1], lab[:, 2])
    around_chroma = np.hypot(around[:, 1], around[:, 2])
    # A feature differs from its 2-ring in hue/chroma (a*b*) - teal stitching on navy, brass, leather - or is
    # markedly more chromatic; lightness alone (shading, highlight smears) never makes one.
    ab_far = np.linalg.norm(lab[:, 1:] - around[:, 1:], axis=1) > a.feature_de
    feature = ab_far | (chroma > around_chroma + 2 * a.feature_chroma)

    # How squarely each face met a source painting: detail on grazing faces is smear, not artwork.
    axes = np.array([[float(v) for v in ax.split(',')] for ax in a.view_axes.split(';')])
    axes /= np.linalg.norm(axes, axis=1)[:, None]
    facing = np.abs(d['normal'] @ axes.T).max(1)
    g0, g1 = (float(v) for v in a.grazing.split(','))
    trust = np.clip((facing - g0) / (g1 - g0), 0, 1)
    # Edge-aware weights from the painted colours: lightness differences (baked shading, highlight smears)
    # count for little, hue/chroma differences (shirt against coat, leather, stitching, brass) for a lot.
    diff = lab[pairs[:, 0]] - lab[pairs[:, 1]]
    guide = np.sqrt((a.lightness_weight * diff[:, 0]) ** 2 + diff[:, 1] ** 2 + diff[:, 2] ** 2)
    settings = {}
    new_lab = lab.copy()
    for spec in a.classes.split(','):
        name, iters, sigma = spec.split(':')
        k, iters, sigma = CLASS_INDEX[name], int(iters), float(sigma)
        settings[name] = {'iterations': iters, 'sigma': sigma}
        sel = (face_cls == k) & ~feature
        i_idx, j_idx = pairs[:, 0], pairs[:, 1]
        # A face the paintings saw at a grazing angle has an unreliable colour of its own: it holds on to it
        # weakly, and its edge test relaxes, so trusted (head-on) neighbours repaint it; a trusted
        # neighbour also pulls harder than a grazing one.
        relax_i = 1 + 3 * (1 - trust[i_idx])
        relax_j = 1 + 3 * (1 - trust[j_idx])
        pull = 0.2 + trust
        w_ij = np.where(sel[i_idx] & ~feature[j_idx], np.exp(-(guide / (sigma * relax_i)) ** 2) * area[j_idx] * pull[j_idx], 0.0)
        w_ji = np.where(sel[j_idx] & ~feature[i_idx], np.exp(-(guide / (sigma * relax_j)) ** 2) * area[i_idx] * pull[i_idx], 0.0)
        hold = area * pull
        cur = lab.copy()
        for _ in range(iters):
            acc = cur * hold[:, None]
            w = hold.copy()
            np.add.at(acc, i_idx, cur[j_idx] * w_ij[:, None])
            np.add.at(w, i_idx, w_ij)
            np.add.at(acc, j_idx, cur[i_idx] * w_ji[:, None])
            np.add.at(w, j_idx, w_ji)
            cur = np.where(sel[:, None], acc / w[:, None], cur)
        new_lab[sel] = cur[sel]
    new_rgb = lab_to_srgb(new_lab)

    # Rewrite texels: new face colour + kept grain; features and untouched classes stay as painted.
    changed = np.any(np.abs(new_rgb - face_rgb) > 0.5, axis=1)
    out = flat.copy()
    tex_face = np.where(own, labels, 0)
    grain = flat - face_rgb[tex_face]
    edit = own & changed[tex_face]
    keep = a.keep_grain * (a.grain_floor + (1 - a.grain_floor) * trust)
    out[edit] = new_rgb[tex_face[edit]] + keep[tex_face[edit], None] * grain[edit]
    out = out.reshape(S, S, 3)
    # Sub-texel faces: their centre texel carries the new colour (later faces win; neighbours are alike).
    small = changed & (counts == 0)
    out[cp[small, 1], cp[small, 0]] = new_rgb[small]
    weight = own.reshape(S, S).astype(float)
    weight[cp[small, 1], cp[small, 0]] = 1
    filled = pull_push(out, weight)
    out = np.where(weight[..., None] > 0, out, filled)
    Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).save(a.out / 'body_basecolor.png')
    report = {'stage': 'clean_garment_paint', 'islands': str(a.islands), 'islands_sha256': sha(a.islands),
              'basecolor': str(a.basecolor), 'basecolor_sha256': sha(a.basecolor), 'mask': str(a.mask),
              'mask_sha256': sha(a.mask), 'script_sha256': sha(__file__), 'classes': settings,
              'keep_grain': a.keep_grain, 'lightness_weight': a.lightness_weight, 'view_axes': a.view_axes,
              'grazing': a.grazing, 'grain_floor': a.grain_floor,
              'faces_grazing': int((trust < 0.5).sum()), 'feature_de': a.feature_de, 'feature_chroma': a.feature_chroma,
              'faces': int(F), 'features': int(feature.sum()),
              'faces_per_class': {n: int((face_cls == k).sum()) for n, k in CLASS_INDEX.items()},
              'speckle_before': speckle(lab), 'speckle_after': speckle(new_lab),
              'output_sha256': sha(a.out / 'body_basecolor.png'), 'uv_changed': False, 'production_ready': False}
    (a.out / 'clean.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ['features', 'faces_per_class', 'classes', 'speckle_before', 'speckle_after']}, indent=1))


if __name__ == '__main__':
    main()
