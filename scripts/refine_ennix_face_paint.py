"""Face-paint refinement after the surface rebake: blush, stubble, hairline, ears and neck.

Works on the head texture refine_ennix_surface.py writes (template UV layout).
Every change is a smooth colour adjustment over a region found on the
conformed head, so the paint keeps its own detail: the guidance pictures cap
the detail, this pass fixes colour and shading.

- Regions come from the 68 DWPose points of the front guidance, mapped onto
  the head's surface through the conform registration (picture pixel -> the
  nearest texel the front picture sees), plus the template's ear group and
  the hair shell the groom grows inside.
- Colours are measured at landmark probes, on the guidance and on the texture
  alike: blush against plain lower cheek, stubble against plain skin, hair
  roots against forehead, ears and mid-neck against plain cheek.
- Blush: cheek and nose redness (low-pass Lab a* over plain skin) is spread and
  soft-capped at a share of the guidance's measured cheek redness, along the
  guidance's own blush direction, for redder-than-skin hues only.
- Stubble: upper lip, soul patch, chin, jaw, under-jaw and sideburns darken to
  the guidance's stubble tone wherever the paint is lighter, except where the
  front picture painted squarely (its stubble is there already); beyond the
  front-projected face the low-pass is replaced (old repairs left hard bands
  there) and a seeded 3D hair grain stands in for the picture's stipple.
- Hairline: scalp skin under the groom's roots (the groom's own root rules)
  takes the guidance's hair colour, fading out across a rounded hairline.
- Ears and neck: one Lab offset each brings their tone, relative to plain
  cheek, to what the guidance shows.

Deterministic; pure NumPy/SciPy/Pillow. Writes head_basecolor.png, a receipt
with every measurement, a UV mask of what changed (R stubble, G blush region,
B root shadow / ear and neck) and a region overlay on the guidance.

Usage:
  python scripts/refine_ennix_face_paint.py --template T.npz --head head.npz \
      --receipt head.json --texture paint/head_basecolor.png \
      --landmarks front-landmarks.json --guidance head-front.png \
      --painting paint/original-aligned.png --hair-shell hair.npz --out face-paint
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
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from reference_asset_compiler import view_projection as vp  # noqa: E402
from paint_head_from_views import head_triangles  # noqa: E402

LUMA = np.array([0.2126, 0.7152, 0.0722])


# ----------------------------------------------------------------------------- colour
def to_linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def to_srgb(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


_M = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750],
               [0.0193339, 0.1191920, 0.9503041]])
_WHITE = np.array([0.95047, 1.0, 1.08883])


def lab(rgb):
    xyz = to_linear(rgb) @ _M.T / _WHITE
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]),
                     200 * (f[..., 1] - f[..., 2])], -1)


def lab_to_rgb(c):
    fy = (c[..., 0] + 16) / 116
    f = np.stack([fy + c[..., 1] / 500, fy, fy - c[..., 2] / 200], -1)
    xyz = np.where(f ** 3 > 216 / 24389, f ** 3, (116 * f - 16) / (24389 / 27)) * _WHITE
    return to_srgb(xyz @ np.linalg.inv(_M).T)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def is_skin(pix):
    """Guidance pixels that are skin, not dark hair or the grey backdrop."""
    return (pix @ LUMA > 0.25) & (pix[:, 0] > pix[:, 2] + 0.15)


# ----------------------------------------------------------------------------- geometry
def vertex_normals(verts, tris):
    tn = np.cross(verts[tris[:, 1]] - verts[tris[:, 0]], verts[tris[:, 2]] - verts[tris[:, 0]])
    vn = np.zeros_like(verts)
    for k in range(3):
        np.add.at(vn, tris[:, k], tn)
    return vn / (np.linalg.norm(vn, axis=1, keepdims=True) + 1e-12)


def ray_hits(orig, dirs, verts, faces, reach):
    """Does a ray from each origin meet the mesh within `reach` (Moller-Trumbore)?"""
    a = verts[faces[:, 0]]
    e1, e2 = verts[faces[:, 1]] - a, verts[faces[:, 2]] - a
    hit = np.zeros(len(orig), bool)
    for i in range(0, len(orig), 48):
        o, d = orig[i:i + 48, None], dirs[i:i + 48, None]
        pv = np.cross(d, e2[None])
        det = (e1[None] * pv).sum(-1)
        ok = np.abs(det) > 1e-12
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        tv = o - a[None]
        u = (tv * pv).sum(-1) * inv
        qv = np.cross(tv, e1[None])
        v = (d * qv).sum(-1) * inv
        t = (e2[None] * qv).sum(-1) * inv
        hit[i:i + 48] = (ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 0) & (t < reach)).any(1)
    return hit


def polyline(points, step=0.0005, smooth=0):
    """Points resampled every `step` metres: positions, tangents, arc lengths, and the arc
    nearest each input point. `smooth` rounds of corner cutting first (Chaikin), so a line
    through landmarks has no kinks for a band along it to show."""
    knots_in = points
    for _ in range(smooth):
        q = points[:-1] * 0.75 + points[1:] * 0.25
        r = points[:-1] * 0.25 + points[1:] * 0.75
        points = np.vstack([points[:1], np.stack([q, r], 1).reshape(-1, 3), points[-1:]])
    seg = np.diff(points, axis=0)
    length = np.r_[0.0, np.cumsum(np.linalg.norm(seg, axis=1))]
    arc = np.arange(0.0, length[-1] + 1e-9, step)
    dense = np.stack([np.interp(arc, length, points[:, j]) for j in range(3)], 1)
    tang = np.gradient(dense, axis=0)
    tang /= np.linalg.norm(tang, axis=1, keepdims=True) + 1e-12
    return dense, tang, arc, arc[cKDTree(dense).query(knots_in)[1]]


class Texels:
    """Every painted texel of the head: its surface point, normal and front-picture pixel.

    Smooth fields go through the mesh vertices (no UV seams, no bleeding between
    islands); fine low-passes stay in texture space, island by island.
    """

    def __init__(self, z, template, size, front):
        self.tris, lt = head_triangles(z)
        self.V = z["verts"]
        self.used = np.unique(self.tris)
        self.vn = vertex_normals(self.V, self.tris)
        tri_id, bary = vp.uv_rasterize(template["loop_uv"], lt, size)
        self.size = size
        self.valid = tri_id >= 0
        self.tri = tri_id[self.valid]
        self.tv = self.tris[self.tri]
        self.bw = bary[self.valid]
        self.pos = np.einsum("nk,nkj->nj", self.bw, self.V[self.tv])
        nrm = np.einsum("nk,nkj->nj", self.bw, self.vn[self.tv])
        self.nrm = nrm / (np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12)
        self.labels, _ = ndimage.label(self.valid)
        self.px = front.pixels(self.pos)
        h, w = front.image.shape[:2]
        depth = vp.depth_buffer(front, self.V, self.tris, (h, w))
        self.xi = np.clip(self.px[:, 0].astype(int), 0, w - 1)
        self.yi = np.clip(self.px[:, 1].astype(int), 0, h - 1)
        # Texels the front picture sees, and how squarely (its colour there is the picture's).
        self.seen = (self.pos[:, 1] <= depth[self.yi, self.xi] + 0.002) & (self.nrm[:, 1] < 0)
        self.facing = self.seen * smoothstep(0.45, 0.75, -self.nrm[:, 1])
        self.tpm = None   # texels per metre on the face, set once the face is found
        self._sample = np.arange(0, len(self.pos), 3)
        self._tree = cKDTree(self.pos[self._sample])

    def per_metre(self, centre, radius):
        """Texels per metre on the surface around `centre` (texture-space blur scale)."""
        area = 0.5 * np.linalg.norm(np.cross(self.V[self.tris[:, 1]] - self.V[self.tris[:, 0]],
                                             self.V[self.tris[:, 2]] - self.V[self.tris[:, 0]]), axis=1)
        near = np.linalg.norm(self.V[self.tris].mean(1) - centre, axis=1) < radius
        return float(np.sqrt(np.bincount(self.tri, minlength=len(self.tris))[near].sum() / area[near].sum()))

    def vertex_value(self, per_vertex):
        return np.einsum("nk,nk...->n...", self.bw, per_vertex[self.tv])

    def surface_blur(self, values, weights, sigma, where=None):
        """Gaussian (sigma metres) weighted mean over the surface, read back per texel.

        Read back linearly over coarse triangles, a gradient creases along their edges;
        for colour, `where` smooths the result again in texture space over those texels.
        """
        vals, w = values[self._sample], weights[self._sample]
        out = np.zeros((len(self.V),) + vals.shape[1:])
        known = np.zeros(len(self.V), bool)
        groups = self._tree.query_ball_point(self.V[self.used], 2.5 * sigma, workers=-1)
        for vi, idx in zip(self.used, groups):
            if not idx:
                continue
            idx = np.asarray(idx)
            g = np.exp(-0.5 * ((self._tree.data[idx] - self.V[vi]) ** 2).sum(1) / sigma ** 2) * w[idx]
            if g.sum() > 1e-9:
                out[vi] = g @ vals[idx] / g.sum()
                known[vi] = True
        # A vertex with no weighted texel nearby takes the nearest vertex that has some.
        _, j = cKDTree(self.V[known]).query(self.V[~known])
        out[~known] = out[known][j]
        result = self.vertex_value(out)
        if where is None:
            return result
        flat = result.reshape(len(result), -1)
        return self.low_pass(flat, where, 0.5 * sigma * self.tpm).reshape(result.shape)

    def low_pass(self, values, where, sigma_px):
        """Normalised Gaussian within each UV island touching the texels `where`."""
        image = np.zeros((self.size, self.size, values.shape[1]))
        image[self.valid] = values
        rows = np.zeros(self.valid.shape, bool)
        rows[self.valid] = where
        out = image.copy()
        pad = int(3 * sigma_px) + 1
        for lab_id in np.unique(self.labels[rows]):
            sl = ndimage.find_objects((self.labels == lab_id).astype(np.int8))[0]
            sl = tuple(slice(max(s.start - pad, 0), s.stop + pad) for s in sl)
            m = (self.labels[sl] == lab_id).astype(float)
            den = np.maximum(ndimage.gaussian_filter(m, sigma_px), 1e-6)
            for c in range(values.shape[1]):
                num = ndimage.gaussian_filter(image[sl][..., c] * m, sigma_px)
                out[sl][..., c] = np.where(m > 0, num / den, image[sl][..., c])
        return out[self.valid]


# ----------------------------------------------------------------------------- regions
def landmarks_on_head(tx, lm_px):
    """Each guidance landmark on the surface: the nearest texel the front picture sees."""
    cand = np.flatnonzero(tx.seen)
    err, j = cKDTree(tx.px[cand]).query(lm_px)
    return tx.pos[cand[j]], err


def lip_mask(tx, lm_px, lm3, shape):
    """The guidance's outer lip contour on the texels the front picture paints."""
    img = Image.new("L", (shape[1], shape[0]), 0)
    ImageDraw.Draw(img).polygon([tuple(p) for p in lm_px[48:60]], fill=255)
    soft = ndimage.gaussian_filter(np.asarray(img, float) / 255, 2.0)
    lips = np.clip(vp.sample(soft[..., None].repeat(3, 2), tx.px)[:, 0] * 1.6, 0, 1)
    mouth = lm3[[48, 54, 51, 57]].mean(0)
    return lips * tx.seen * (np.linalg.norm(tx.pos - mouth, axis=1) < 0.04)


def across_line(tx, points, toward, smooth=3):
    """Each texel against a line on the skin: distance, signed offset across it (positive
    toward `toward`, along the skin), how far past its ends, and its arc position."""
    line, tang, arc, knots = polyline(points, smooth=smooth)
    dist, k = cKDTree(line).query(tx.pos)
    q, tk = line[k], tang[k]
    up = toward - q
    up -= (up * tk).sum(1, keepdims=True) * tk
    up -= (up * tx.nrm).sum(1, keepdims=True) * tx.nrm
    up /= np.linalg.norm(up, axis=1, keepdims=True) + 1e-12
    h = ((tx.pos - q) * up).sum(1)
    past = (np.where(k == 0, -((tx.pos - q) * tk).sum(1), 0.0)
            + np.where(k == len(line) - 1, ((tx.pos - q) * tk).sum(1), 0.0))
    return dist, h, past, arc[k], arc, knots


def jaw_line(tx, lm3, ear_pts, d_ear, a, sideburns=False):
    """The jaw line on the skin: landmarks 4..12 (its lower edge, as the front picture
    outlines it), back to the jaw's angle under each earlobe and, with `sideburns`, on up
    in front of each ear. Points 0..3 and 13..16 outline the cheeks, not the jaw, so the
    ends come from the ear instead. Returns the points and the index of the chin (8)."""
    pts = lm3[4:13].copy()
    # Seen from the front, the outline's depth wanders: smoothed along the line.
    for _ in range(2):
        pts[1:-1] = 0.25 * pts[:-2] + 0.5 * pts[1:-1] + 0.25 * pts[2:]
    cand = tx.pos[d_ear > 0.004][::3]
    tree = cKDTree(cand)

    def on_skin(p):
        return cand[tree.query(p)[1]]

    ends = []
    mx = lm3[[48, 54], 0].mean()
    for side in (-1, 1):
        e = ear_pts[np.sign(ear_pts[:, 0] - mx) == side]
        front, bottom = e[:, 1].min(), e[:, 2].min()
        lobe_x = float(np.median(e[e[:, 2] < bottom + 0.01, 0]))
        angle = on_skin([lobe_x, front - a.jaw_angle[0], bottom - a.jaw_angle[1]])
        burn = on_skin([lobe_x, front - a.sideburn[1], bottom + a.sideburn[0]])
        ends.append([burn, angle] if sideburns else [angle])
    line = np.vstack([ends[0], on_skin(pts), ends[1][::-1]])
    return line, len(ends[0]) + 4


def below_jaw(tx, lm3, ear_pts, d_ear, a):
    """Metres below the jaw line (negative above it); behind the jaw's ends, below the ears."""
    mouth = lm3[[48, 54, 51, 57]].mean(0)
    line, _ = jaw_line(tx, lm3, ear_pts, d_ear, a)
    _, h, past, *_ = across_line(tx, line, mouth)
    behind = smoothstep(0.0, 0.01, past)
    return (1 - behind) * -h + behind * (ear_pts[:, 2].min() - 0.01 - tx.pos[:, 2])


def beard_density(tx, lm3, lips, ear_pts, d_ear, a):
    """Stubble density 0..1 from the landmarks: moustache, soul patch, chin and jaw."""
    pos = tx.pos
    mouth = lm3[[48, 54, 51, 57]].mean(0)
    half_face = float(np.linalg.norm(lm3[16] - lm3[0])) / 2
    nostril = smoothstep(0.004, 0.0015, cKDTree(lm3[31:36]).query(pos)[0])

    # The jaw line, continued up the front of each ear (the sideburn); s = 0 at the chin,
    # 1 at the jaw's angles, beyond 1 up the sideburns. h: across it, positive toward the mouth.
    line, c = jaw_line(tx, lm3, ear_pts, d_ear, a, sideburns=True)
    dist, h, past, at, arc, knots = across_line(tx, line, mouth)
    chin = knots[c]
    s = np.abs(at - chin) / np.where(at < chin, chin - knots[1], knots[-2] - chin)
    up_past = np.where(at < chin, knots[1] / (chin - knots[1]), (arc[-1] - knots[-2]) / (knots[-2] - chin))
    w_up = a.jaw_up[0] + (a.jaw_up[1] - a.jaw_up[0]) * smoothstep(0.0, 1.0, np.clip(s, 0, 1)) ** 0.7
    d_jaw = np.where(h >= 0, 1 - smoothstep(0.55 * w_up, w_up, h),
                     a.density[3] / a.density[2] * (1 - smoothstep(0.0, a.jaw_down, -h)))
    # Up the sideburn the stubble thins out toward the hair.
    d_jaw *= 1 - (1 - a.sideburn[2]) * smoothstep(1.0, 1.0 + up_past, s)
    d_jaw *= (1 - smoothstep(0.0, 0.008, past)) * (1 - smoothstep(1.3, 1.6, dist / np.maximum(w_up, a.jaw_down)))
    # The chin patch stays below the mouth; the cheeks above its corners stay clean.
    above = smoothstep(-0.004, 0.004, pos[:, 2] - lm3[[48, 54], 2].mean())
    d_jaw *= 1 - above * smoothstep(0.7 * half_face, 0.5 * half_face, np.abs(pos[:, 0] - mouth[0]))

    # Moustache: a band over the upper lip, from past one corner (drooping) to the other.
    def droop(i, side):
        p = lm3[i] + np.array([side * a.moustache_droop[0], 0.0, -a.moustache_droop[1]])
        return pos[np.argmin(np.linalg.norm(pos - p, axis=1))]
    line, _, marc, mknots = polyline(np.vstack([droop(48, -1), lm3[48:55], droop(54, 1)]), smooth=2)
    md, mk = cKDTree(line).query(pos)
    off = np.clip(np.abs(marc[mk] - mknots[4]) / (mknots[-1] / 2), 0, 1)
    w_m = a.moustache_width[0] + (a.moustache_width[1] - a.moustache_width[0]) * off ** 1.5
    # Past the corners (the droop) it thins.
    d_m = (1 - smoothstep(0.45 * w_m, w_m, md)) * (1 - 0.7 * smoothstep(0.7, 1.0, off))
    d_m *= 1 - smoothstep(lm3[31:36, 2].mean() - 0.004, lm3[31:36, 2].mean() - 0.001, pos[:, 2])

    # Soul patch: under the lower lip's centre, widening into the chin.
    s0, s1 = lm3[57], lm3[57] + 0.6 * (lm3[8] - lm3[57])
    tt = np.clip(((pos - s0) @ (s1 - s0)) / ((s1 - s0) @ (s1 - s0)), 0, 1)
    sd = np.linalg.norm(pos - (s0 + tt[:, None] * (s1 - s0)), axis=1)
    w_s = a.soul_width[0] + (a.soul_width[1] - a.soul_width[0]) * tt
    d_s = (1 - smoothstep(0.5 * w_s, w_s, sd)) * smoothstep(0.0, 0.08, tt)

    density = 1 - (1 - a.density[0] * d_m) * (1 - a.density[1] * d_s) * (1 - a.density[2] * d_jaw)
    density *= (1 - lips) * (1 - nostril) * (np.linalg.norm(pos - mouth, axis=1) < 0.12)
    density *= smoothstep(0.003, 0.012, d_ear)   # never on the ear
    return density, nostril


def probes(lm_px):
    """Probe discs (picture px) at fixed landmark positions; the same on any face."""
    fw = float(np.linalg.norm(lm_px[16] - lm_px[0]))
    return {
        # The apple of each cheek: the painted blush.
        "cheek": [((lm_px[2] + lm_px[31] + lm_px[41]) / 3, 0.07 * fw),
                  ((lm_px[14] + lm_px[35] + lm_px[46]) / 3, 0.07 * fw)],
        # Lower cheek between jaw and mouth corner: plain skin, no blush, little stubble.
        "plain": [(0.65 * lm_px[4] + 0.35 * lm_px[48], 0.035 * fw),
                  (0.65 * lm_px[12] + 0.35 * lm_px[54], 0.035 * fw)],
        # Moustache either side of the philtrum, and the chin.
        "stubble": [((lm_px[33] + lm_px[51]) / 2 + [-0.07 * fw, 0.01 * fw], 0.025 * fw),
                    ((lm_px[33] + lm_px[51]) / 2 + [0.07 * fw, 0.01 * fw], 0.025 * fw),
                    (lm_px[8] + [0, -0.12 * fw], 0.04 * fw)],
        "forehead": [((lm_px[21] + lm_px[22]) / 2 + [0, -0.17 * fw], 0.05 * fw)],
    }, fw


def disc_mask(shape, items):
    yy, xx = np.mgrid[:shape[0], :shape[1]]
    return np.any([((xx - c[0]) ** 2 + (yy - c[1]) ** 2) < r ** 2 for c, r in items], axis=0)


def cheek_redness(image, discs, shape):
    """Blush strength of a picture: 90th-percentile low-pass a* in the cheeks over plain cheek."""
    a = ndimage.gaussian_filter(lab(image)[..., 1], 4.0)
    return float(np.percentile(a[disc_mask(shape, discs["cheek"])], 90)
                 - np.median(a[disc_mask(shape, discs["plain"])]))


def hair_colour(guide, lm_px, fw, forehead):
    """Hair just above the forehead hairline in the guidance: its root colour."""
    brow, chin = (lm_px[21] + lm_px[22]) / 2, lm_px[8]
    top = brow + (brow - chin) * 0.55
    yy, xx = np.mgrid[:guide.shape[0], :guide.shape[1]]
    pix = guide[(np.abs(xx - top[0]) < 0.3 * fw) & (np.abs(yy - top[1]) < 0.12 * fw)]
    return np.median(pix[pix @ LUMA < 0.6 * float(forehead @ LUMA)], axis=0)


# ----------------------------------------------------------------------------- stages
def calm_blush(tx, col, lm3, lips, plain_lab, cap, slope, tpm, a):
    """Lower cheek and nose redness (low-pass a* over plain skin) to a soft, capped spread of
    itself: patches lose their edges and peaks, never gain redness; redder hues only."""
    region = np.zeros(len(tx.pos))
    for c in (lm3[[2, 31, 41]].mean(0), lm3[[14, 35, 46]].mean(0)):
        region = np.maximum(region, np.exp(-(np.linalg.norm(tx.pos - c, axis=1) / a.blush_radius) ** 4))
    nose = np.exp(-(np.linalg.norm(tx.pos - lm3[30], axis=1) / 0.022) ** 4)
    region = np.maximum(region, a.nose_blush * nose) * (1 - lips)
    roi = region > 1e-3
    L = lab(col)
    lp = tx.low_pass(L[:, 1:], roi, a.blush_sigma * tpm)
    excess = np.maximum(lp[:, 0] - plain_lab[1], 0.0)
    spread = tx.surface_blur(excess, np.ones(len(excess)), a.blush_spread, where=roi)
    kept = np.minimum(cap * np.tanh(spread / cap), excess)
    # Only where the patch is redder in hue than plain skin: yellow-orange skin is not blush.
    hue_gap = np.arctan2(plain_lab[2], plain_lab[1]) - np.arctan2(lp[:, 1], lp[:, 0])
    cut = region * (excess - kept) * smoothstep(-0.08, 0.0, hue_gap)
    # Along the guidance's own blush direction: per unit of a*, its L* and b*.
    L -= cut[:, None] * np.array([slope[0], 1.0, slope[1]])[None]
    out = np.where(roi[:, None], lab_to_rgb(L), col)
    after = tx.low_pass(lab(out)[:, 1:], roi, a.blush_sigma * tpm)[:, 0] - plain_lab[1]
    core = region > 0.5
    return out, region, {"texture_excess_a_p99_before": round(float(np.percentile(excess[core], 99)), 2),
                         "texture_excess_a_p99_after": round(float(np.percentile(np.maximum(after[core], 0), 99)), 2),
                         "texels_changed": int((cut > 0.25).sum())}


def even_tone(tx, col, guide, ref_t, ref_g, ear_w, neck_w, below, mouth_x, a):
    """Lab offsets bringing ears and neck, relative to plain cheek, to the guidance's.

    The ear is measured where the front picture sees it, the neck at mid-neck (clear of the
    jaw's cast shadow, which the render's own light makes). The ear takes only part of
    the picture's darkness: seen edge-on from the front, it is mostly in shade.
    """
    L = lab(col)
    report = {}
    for name, w, sel, share, amount in (
            ("ear", ear_w, (ear_w > 0.9) & (tx.nrm[:, 1] < -0.05) & tx.seen, a.ear_lightness, a.ear_tone),
            ("neck", neck_w, (below > a.neck_probe[0]) & (below < a.neck_probe[1]) & (neck_w > 0.95)
             & (np.abs(tx.pos[:, 0] - mouth_x) < 0.03) & (tx.facing > 0.2), a.neck_lightness, a.neck_tone)):
        pix = guide[tx.yi[sel], tx.xi[sel]]
        g = np.median(lab(pix[is_skin(pix)]), axis=0)
        t = np.median(L[sel] if name == "neck" else L[w > 0.9], axis=0)
        shift = ((g - ref_g) * np.array([share, 1.0, 1.0]) - (t - ref_t)) * amount
        L += w[:, None] * shift[None]
        report[name] = {"guidance_lab": np.round(g, 2).tolist(), "texture_lab_before": np.round(t, 2).tolist(),
                        "guidance_pixels": int(is_skin(pix).sum()), "lab_shift": np.round(shift, 2).tolist()}
    touched = (ear_w > 1e-3) | (neck_w > 1e-3)
    return np.where(touched[:, None], lab_to_rgb(L), col), report


def stubble_grain(pos, cell, radius, fill, seed):
    """Seeded hair dots on a jittered 3D grid (no UV seams): 0..1 per texel."""
    base = np.floor(pos / cell).astype(np.int64)
    grain = np.zeros(len(pos))
    for off in np.stack(np.meshgrid(*[[-1, 0, 1]] * 3, indexing="ij"), -1).reshape(-1, 3):
        c = (base + off).astype(np.uint64)
        h = (c[:, 0] * np.uint64(0x9E3779B97F4A7C15) ^ c[:, 1] * np.uint64(0xC2B2AE3D27D4EB4F)
             ^ c[:, 2] * np.uint64(0x165667B19E3779F9) ^ np.uint64(seed))
        h = (h ^ (h >> np.uint64(31))) * np.uint64(0xBF58476D1CE4E5B9)
        h = (h ^ (h >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        h ^= h >> np.uint64(33)
        parts = [((h >> np.uint64(16 * i)) & np.uint64(0xFFFF)).astype(float) / 65535.0 for i in range(4)]
        dot = (base + off + np.stack(parts[:3], 1)) * cell
        on = parts[3] < fill
        grain = np.maximum(grain, on * np.exp(-((pos - dot) ** 2).sum(1) / radius ** 2))
    return grain


def add_stubble(tx, lin, density, lips, nostril, tint, tpm, a):
    """Darken toward plain skin x tint^density where the paint is lighter than that, then
    give it a hair grain (zero mean, so the measured tone holds)."""
    wide = np.clip(density * 4, 0, 1)
    base = tx.surface_blur(lin, (1 - wide) * (1 - lips) * (1 - nostril), 0.008, where=density > 1e-3)
    target = base * tint[None] ** density[:, None]
    where = density > 1e-3
    lp = tx.low_pass(lin, where, a.stubble_sigma * tpm)
    # Where the front picture painted squarely, its own stubble is already there (and the
    # paint's lips need not sit on the picture's landmarks): leave it. Elsewhere, lighter
    # than the stubble tone darkens (detail kept: it is a gain); darker bands left by
    # older repairs ease toward it.
    painted = a.front_keep * tx.facing
    lighter = (target @ LUMA) > (lp @ LUMA)
    ease = np.where(lighter, a.lighten_side * (1 - tx.facing), 1 - painted) * np.clip(density / 0.15, 0, 1)
    gain = (target / np.maximum(lp, 1e-5)) ** ease[:, None]
    # Beyond the front-projected face, old repairs left sharp-edged bands; their edges
    # survive as detail around the replaced low-pass. Clamp that detail to stubble grain.
    replaced = (1 - tx.facing) * np.clip(density / 0.15, 0, 1)
    detail = np.log(np.maximum(lin, 1e-5) / np.maximum(lp, 1e-5))
    clamped = np.clip(detail, -a.side_detail, a.side_detail)
    gain = gain * np.exp((clamped - detail) * replaced[:, None])
    out = np.where(where[:, None], lin * gain, lin)
    if a.grain[0] > 0:
        dots = stubble_grain(tx.pos[where], a.grain[1], a.grain[2], a.grain[3], int(a.grain[4]))
        k = a.grain[0] * density[where] * (1 - painted[where]) * (dots - dots.mean())
        out[where] *= tint[None] ** k[:, None]
    return out, {
        "texels": int((density > 0.05).sum()),
        "darkened_texels": int((where & ~lighter & (gain @ LUMA < 0.98)).sum()),
        "eased_texels": int((where & lighter & (gain @ LUMA > 1.02)).sum())}


def root_shadow(tx, z, hair, ear_pts, a):
    """0..1 shadow of the groom's roots on the skin: the groom's root rules, faded at the edge."""
    V, vn = tx.V, tx.vn
    eyes = V[np.concatenate([z["vg__helper-l-eye"], z["vg__helper-r-eye"]])]
    hairline_z = float(eyes[:, 2].mean()) + a.hairline_above_eyes
    ear_bottom = float(ear_pts[:, 2].min())
    upper = tx.used[V[tx.used, 2] > ear_bottom - 0.01]
    cov = np.zeros(len(V))
    cov[upper] = ray_hits(V[upper] + vn[upper] * 0.001, vn[upper], hair["verts"].astype(float), hair["tris"], 0.12)
    pos, nrm = tx.pos, tx.nrm
    # Smoothed over the surface: the shell's edge, not the scalp's coarse triangles.
    covered = tx.surface_blur(tx.vertex_value(cov), np.ones(len(pos)), 0.006) > 0.5
    face = ((nrm[:, 1] < -0.35) | (pos[:, 1] < eyes[:, 1].mean() + a.temple_behind_eyes)) & (pos[:, 2] < hairline_z)
    sideburn = (pos[:, 1] < ear_pts[:, 1].min() + 0.004) & (pos[:, 2] < eyes[:, 2].mean() + a.sideburn_roots)
    near_ear = cKDTree(ear_pts).query(pos)[0] < 0.012
    root = covered & ~face & ~near_ear & ~sideburn & (pos[:, 2] > ear_bottom - 0.004)
    # The rules meet at corners (hairline height, temple, sideburn); a hairline has none.
    root = tx.low_pass(root[:, None].astype(float), root, a.root_round * tx.tpm)[:, 0] > 0.5
    reach = a.root_fade_out + a.root_ramp_in + 0.005
    d_out = np.minimum(cKDTree(pos[root][::4]).query(pos, distance_upper_bound=reach)[0], reach)
    d_in = np.minimum(cKDTree(pos[~root][::4]).query(pos, distance_upper_bound=reach)[0], reach)
    signed = np.where(root, d_in, -d_out)
    # Sparse roots at the edge: the shadow builds slowly there, fully only well inside.
    shade = smoothstep(-a.root_fade_out, a.root_ramp_in, signed) ** a.root_gamma
    return a.root_strength * shade, root, hairline_z


# ----------------------------------------------------------------------------- arguments
def _args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    for name in ("template", "head", "receipt", "texture", "landmarks", "guidance", "hair_shell", "out"):
        p.add_argument("--" + name.replace("_", "-"), required=True)
    p.add_argument("--painting", help="the original painting registered to the guidance frame "
                   "(refine_ennix_surface.py's original-aligned.png): its blush is measured for the record")
    g = p.add_argument_group("blush")
    g.add_argument("--blush-keep", type=float, default=0.6,
                   help="the cap, as a share of the guidance's measured cheek redness")
    g.add_argument("--blush-radius", type=float, default=0.03, help="metres around each cheek centre")
    g.add_argument("--nose-blush", type=float, default=0.6, help="strength of the same cap on the nose")
    g.add_argument("--blush-sigma", type=float, default=0.004, help="metres: the scale of a blotch")
    g.add_argument("--blush-spread", type=float, default=0.008, help="metres the kept blush is spread over")
    g = p.add_argument_group("stubble")
    g.add_argument("--stubble-strength", type=float, default=1.0, help="exponent on the measured stubble tint")
    g.add_argument("--moustache-width", type=float, nargs=2, default=(0.007, 0.003),
                   help="metres off the upper lip: at its centre, at the corners")
    g.add_argument("--moustache-droop", type=float, nargs=2, default=(0.004, 0.006),
                   help="metres the moustache runs past each mouth corner: outward, down")
    g.add_argument("--soul-width", type=float, nargs=2, default=(0.0025, 0.006),
                   help="metres, soul-patch half width under the lip and where it meets the chin")
    g.add_argument("--jaw-up", type=float, nargs=2, default=(0.026, 0.02),
                   help="metres the stubble climbs from the jaw line: at the chin, below the ears")
    g.add_argument("--jaw-down", type=float, default=0.012, help="metres it runs under the jaw")
    g.add_argument("--jaw-angle", type=float, nargs=2, default=(0.008, 0.01), metavar=("BEFORE_EAR", "BELOW_LOBE"),
                   help="metres: where the jaw line turns up, in front of and below each earlobe")
    g.add_argument("--sideburn", type=float, nargs=3, default=(0.025, 0.006, 0.4),
                   metavar=("RISE", "BEFORE_EAR", "DENSITY"),
                   help="the jaw line continues to this many metres above the lobe, this far in front of the ear, thinning to DENSITY")
    g.add_argument("--density", type=float, nargs=4, default=(0.85, 1.0, 1.0, 0.6),
                   metavar=("MOUSTACHE", "SOUL", "JAW", "UNDER"))
    g.add_argument("--front-keep", type=float, default=1.0,
                   help="share of the front picture's own stubble kept where it painted squarely (no darkening there)")
    g.add_argument("--lighten-side", type=float, default=1.0,
                   help="share of excess darkness eased off beyond the front-projected face")
    g.add_argument("--stubble-sigma", type=float, default=0.002, help="metres: detail finer than this is kept")
    g.add_argument("--grain", type=float, nargs=5, default=(1.5, 0.0006, 0.00022, 0.6, 7),
                   metavar=("AMOUNT", "CELL", "RADIUS", "FILL", "SEED"),
                   help="hair grain: exponent on the stubble tint at a dot; metres between hairs, dot radius; "
                        "share of cells with a hair; seed")
    g.add_argument("--side-detail", type=float, default=0.08,
                   help="largest log-contrast of detail kept where the side-of-face stubble is replaced")
    g = p.add_argument_group("hairline (mirrors grow_hair_groom.py's root rules)")
    g.add_argument("--hairline-above-eyes", type=float, default=0.062)
    g.add_argument("--temple-behind-eyes", type=float, default=0.03)
    g.add_argument("--sideburn-roots", type=float, default=0.025)
    g.add_argument("--root-strength", type=float, default=0.85)
    g.add_argument("--root-fade-out", type=float, default=0.008, help="metres the shadow reaches onto skin")
    g.add_argument("--root-ramp-in", type=float, default=0.012, help="metres inside the roots to full shadow")
    g.add_argument("--root-gamma", type=float, default=1.6, help="exponent on the fade: above 1, lighter at the edge")
    g.add_argument("--root-round", type=float, default=0.006, help="metres: corners of the root region rounded off")
    g = p.add_argument_group("tone")
    g.add_argument("--ear-tone", type=float, default=0.5, help="share of the measured ear offset applied")
    g.add_argument("--ear-feather", type=float, default=0.005, help="metres the ear offset fades over")
    g.add_argument("--ear-lightness", type=float, default=0.3,
                   help="share of the guidance's ear darkness taken (the rest is the picture's shading)")
    g.add_argument("--neck-tone", type=float, default=1.0, help="share of the measured neck offset applied")
    g.add_argument("--neck-lightness", type=float, default=1.0, help="share of the guidance's neck darkness taken")
    g.add_argument("--neck-probe", type=float, nargs=2, default=(0.025, 0.06),
                   help="metres below the jaw line where the neck is measured (mid-neck)")
    g.add_argument("--neck-ramp", type=float, default=0.015, help="metres below the jaw to full neck tone")
    return p.parse_args(argv)


# ----------------------------------------------------------------------------- main
def main(argv=None):
    a = _args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    template = np.load(a.template)
    z = dict(np.load(a.head))
    reg = json.loads(Path(a.receipt).read_text())["picture"]["registration"]
    lm_px = np.array(json.loads(Path(a.landmarks).read_text())["landmarks_68"], float)
    guide = vp.load_image(a.guidance)
    tex = vp.load_image(a.texture)
    front = vp.View("front", guide, reg["scale_px_per_m"], np.array(reg["rotation"]), np.array(reg["translation_px"]))
    tx = Texels(z, template, tex.shape[0], front)

    lm3, err = landmarks_on_head(tx, lm_px)
    mouth = lm3[[48, 54, 51, 57]].mean(0)
    tpm = tx.tpm = tx.per_metre(mouth, 0.06)
    lips = lip_mask(tx, lm_px, lm3, guide.shape[:2])
    ear_pts = tx.V[template["vg__ears"]]
    d_ear = cKDTree(ear_pts).query(tx.pos)[0]
    density, nostril = beard_density(tx, lm3, lips, ear_pts, d_ear, a)
    discs, fw = probes(lm_px)
    shape = guide.shape[:2]
    masks = {k: disc_mask(shape, v) for k, v in discs.items()}
    g_med = {k: np.median(guide[m], axis=0) for k, m in masks.items()}
    g_lab = {k: lab(v) for k, v in g_med.items()}
    before = tex[tx.valid].copy()

    def tex_probe(colours, name):
        return np.median(colours[masks[name][tx.yi, tx.xi] & tx.seen], axis=0)

    receipt = {"landmark_px_error": {"median": round(float(np.median(err)), 3), "max": round(float(err.max()), 3)},
               "texels_per_mm": round(tpm / 1000, 3),
               "probes_px": {k: [[np.round(c, 1).tolist(), round(float(r), 1)] for c, r in v] for k, v in discs.items()},
               "guidance_probe_lab": {k: np.round(v, 2).tolist() for k, v in g_lab.items()}}

    # 1. Blush, capped at the painting's measured cheek redness.
    red_g = cheek_redness(guide, discs, shape)
    red_p = cheek_redness(vp.load_image(a.painting), discs, shape) if a.painting else None
    cap = a.blush_keep * red_g
    plain_t = lab(tex_probe(before, "plain"))
    d_blush = g_lab["cheek"] - g_lab["plain"]
    slope = np.clip(np.array([d_blush[0], d_blush[2]]) / max(d_blush[1], 1e-3), [-1.0, 0.0], [0.0, 1.0])
    col, blush_region, rep = calm_blush(tx, before, lm3, lips, plain_t, max(cap, 0.5), slope, tpm, a)
    receipt["blush"] = {"guidance_redness_a": round(red_g, 2), "painting_redness_a": None if red_p is None else round(red_p, 2),
                        "cap_a": round(cap, 2), "l_b_per_a": np.round(slope, 3).tolist(), "texture_plain_lab": np.round(plain_t, 2).tolist(), **rep}

    # 2. Ears and neck against plain cheek.
    ears_v = np.zeros(len(tx.V))
    ears_v[template["vg__ears"]] = 1.0
    ear_w = smoothstep(0.2, 0.8, np.clip(tx.surface_blur(tx.vertex_value(ears_v), np.ones(len(tx.pos)), a.ear_feather,
                                                                 where=tx.vertex_value(ears_v) > 0), 0, 1))
    below = below_jaw(tx, lm3, ear_pts, d_ear, a)
    neck_w = smoothstep(0.002, 0.002 + a.neck_ramp, below) * (1 - ear_w)
    col, rep = even_tone(tx, col, guide, lab(tex_probe(col, "plain")), g_lab["plain"], ear_w, neck_w,
                         np.maximum(below, 0.0), float(mouth[0]), a)
    receipt["tone"] = rep

    # 3. Stubble at the guidance's tone.
    lin = to_linear(col)
    tint = (to_linear(g_med["stubble"]) / to_linear(g_med["plain"])) ** a.stubble_strength
    lin, rep = add_stubble(tx, lin, density, lips, nostril, tint, tpm, a)
    receipt["stubble"] = {"tint_linear": tint.round(4).tolist(), **rep}

    # 4. Root shadow under the groom, in the guidance's hair colour.
    shadow, root, hairline_z = root_shadow(tx, z, np.load(a.hair_shell), ear_pts, a)
    hair = hair_colour(guide, lm_px, fw, g_med["forehead"])
    root_tint = to_linear(hair) / to_linear(g_med["forehead"])
    lin *= root_tint[None] ** shadow[:, None]
    receipt["hairline"] = {"hairline_z": round(hairline_z, 4), "root_texels": int(root.sum()),
                           "guidance_hair_srgb": np.round(hair, 4).tolist(), "root_tint_linear": root_tint.round(4).tolist(),
                           "shaded_texels": int((shadow > 0.02).sum())}

    col = to_srgb(lin)
    tex[tx.valid] = col
    tex = vp.fill_unpainted(tex, tx.valid)
    Image.fromarray((np.clip(tex, 0, 1) * 255 + 0.5).astype(np.uint8)).save(out / "head_basecolor.png")
    receipt.update(
        changed_texels=int((np.abs(col - before).max(1) > 2 / 255).sum()), geometry_changed=False,
        inputs={name: {"path": str(path), "sha256": _sha(path)} for name, path in (
            ("texture", a.texture), ("guidance", a.guidance), ("landmarks", a.landmarks),
            ("hair_shell", a.hair_shell), ("painting", a.painting)) if path},
        parameters={k: v for k, v in vars(a).items() if k not in (
            "template", "head", "receipt", "texture", "landmarks", "guidance", "hair_shell", "painting", "out")},
        method="DWPose landmarks mapped onto the conformed head; colours measured at landmark probes on the "
               "guidance and painting; smooth Lab / linear-RGB gains; no generative image tool")
    (out / "face-paint-receipt.json").write_text(json.dumps(receipt, indent=2))
    masks_uv = np.zeros(tex.shape)
    masks_uv[tx.valid] = np.c_[density, blush_region, np.maximum(shadow, 0.5 * np.maximum(ear_w, neck_w))]
    Image.fromarray((np.clip(masks_uv, 0, 1) * 255).astype(np.uint8)).save(out / "face-paint-masks.png")
    _overlay(out / "regions-front.png", guide, lm_px, discs, tx, (density, blush_region, shadow, np.maximum(ear_w, neck_w)))
    print(json.dumps(receipt, indent=2))


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _overlay(path, guide, lm_px, discs, tx, fields):
    """What changed and where, in the front guidance's frame: stubble blue, blush red,
    roots amber, ears and neck green; probe discs and landmarks drawn on top."""
    h, w = guide.shape[:2]
    colours = np.array([[0.15, 0.45, 1.0], [1.0, 0.15, 0.25], [1.0, 0.7, 0.1], [0.3, 0.9, 0.4]])
    over = guide.copy()
    for f, c in zip(fields, colours):
        img = np.zeros((h, w))
        np.maximum.at(img, (tx.yi[tx.seen], tx.xi[tx.seen]), f[tx.seen])
        img = ndimage.grey_closing(img, size=3)[..., None] * 0.6
        over = over * (1 - img) + c * img
    im = Image.fromarray((np.clip(over, 0, 1) * 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    for x, y in lm_px:
        d.ellipse((x - 2.5, y - 2.5, x + 2.5, y + 2.5), outline=(255, 255, 255))
    for name, items in discs.items():
        for c, r in items:
            d.ellipse((c[0] - r, c[1] - r, c[0] + r, c[1] + r), outline=(255, 255, 255), width=2)
            d.text((c[0] + r + 3, c[1] - 6), name, fill=(255, 255, 255))
    im.save(path)


if __name__ == "__main__":
    main()
