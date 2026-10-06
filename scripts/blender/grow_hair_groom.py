"""Grow a strand groom on a finished head, filling its hair envelope in layers.

The hair shell taken from an acquisition is a good silhouette and a bad
surface: lumps, shards and painted smears. This grows real strands inside it
instead. The shell is read as a volume over the scalp: at every scalp point,
the hair reaches out to the shell's last crossing along the normal (the
silhouette). Each lock is given a depth in that volume, rises to it off the
scalp and flows along it (swept back, falling at the sides, a share of front
locks forward over the forehead) in broad S-waves, weaving a little in and out
of its layer. Outer locks make the silhouette; inner locks fill underneath, so
the volume is even and nothing stands proud of it. Where a lock reaches the
envelope's edge its end falls free and flicks out.

Children spread around their guide as a flat ribbon in the guide's own frame
(across the flow, a little through the layer) and taper toward the tip.
Colour comes from the painted hair texture, darker the deeper a strand lies.

Deterministic (seeded); CPU; run with Blender for its BVH queries. Writes a
strands NPZ (points, per-strand point counts, per-point colour and radius)
that render_painted_head.py --strands draws as Cycles hair.

Usage:
  blender -b --factory-startup --python scripts/blender/grow_hair_groom.py -- \
      <template.npz> <head.npz> <hair_shell.npz> <hair_basecolor.png> <out_strands.npz> \
      [--guides 450] [--children 170] [--seed 7]
"""

from __future__ import annotations

import argparse
import json
import sys

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

HELPERS = ("helper-l-eye", "helper-r-eye", "helper-upper-teeth", "helper-lower-teeth",
           "helper-tongue")
STEP = 0.004            # metres per strand segment
MAX_STEPS = 95
HAIRLINE_ABOVE_EYES = 0.062   # forehead height: front-facing skin below this is face
BRIGHTEN = 1.3
WARM = np.array([1.2, 0.9, 0.66])   # toward the painting's red-brown copper
SATURATE = 1.3      # the shell paint is greyer than the painting's hair
RADIAL = 0.2        # how much hair fans out from the crown
FLICK = 0.3         # share of a lock's length over which its end turns out (the shag's flicks)
PART_SWEEP = 0.55
PART_RAMP = 0.035   # metres from the part over which the sideways sweep builds up
TEMPLE_BEHIND_EYES = 0.03     # metres behind the eyes before hair may root at the temples
CAP_INSET = 0.015             # metres the dark scalp cap stays inside the hair's edge
CAP_DENSITY = 0.35            # ...and only under hair this dense (share of the median strand density)
REACH = 0.15        # metres along the scalp normal searched for the silhouette
RISE = 0.03         # metres of arc over which a lock climbs to its layer
CLIMB = 0.7         # steepest climb off the scalp (rise per run): hair leaves the scalp low
CLIMB_FRONT = 1.0   # ...except at the front hairline, where the swept-up front lock lifts
LAYER_WAVE = 0.08   # how far (share of the depth) a lock weaves in and out of its layer
MIN_ENVELOPE = 0.004  # metres: thinner than this the envelope has ended
ENVELOPE_SMOOTHING = 25  # neighbour-averaging passes over the envelope depth
VOLUME = 1.3         # the scan's hair is tighter to the head than the painting's: grown out by this
ENVELOPE_MAX = 0.06   # metres: hair stands no taller off the scalp than this (a scan's bulge
                      # would otherwise raise the few locks under it into tufts)
SHADE_DEPTH = 0.025   # metres of hair over a strand at which it is fully in the shade of it
SIDEBURN = 0.4        # sideburns end this far up the ear (0 = lobe, 1 = top)
SIDEBURN_ROOTS = 0.025  # metres above the eyes below which nothing roots in front of the ears


def _args():
    argv = sys.argv[sys.argv.index("--") + 1:]
    p = argparse.ArgumentParser()
    for name in ("template", "head", "shell", "hair_tex", "out"):
        p.add_argument(name)
    p.add_argument("--guides", type=int, default=300)
    p.add_argument("--children", type=int, default=255)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--length", type=float, nargs=2, default=(0.09, 0.19),
                   help="range of lock lengths (metres); a lock also ends past the envelope")
    p.add_argument("--wave-length", type=float, nargs=2, default=(0.07, 0.12),
                   help="range of wave lengths (metres); each lock draws its own")
    p.add_argument("--wave", type=float, default=0.25)
    p.add_argument("--curl", type=float, default=0.6,
                   help="largest sideways C-curve a lock takes toward its tip")
    p.add_argument("--fringe", type=float, default=0.3,
                   help="share of the front hairline whose locks fall forward over the forehead")
    p.add_argument("--clump", type=float, default=0.9,
                   help="how close a lock's strands come together at its tip (1 = to a point)")
    p.add_argument("--strays", type=float, default=0.05,
                   help="share of children that leave their lock (flyaways)")
    p.add_argument("--part", type=float, default=0.012,
                   help="metres the parting sits to the side of the crown (x)")
    return p.parse_args(argv)


def skin_mesh(z):
    helper = np.zeros(len(z["verts"]), bool)
    for g in HELPERS:
        if "vg__" + g in z.files:
            helper[z["vg__" + g]] = True
    tris = []
    for i in z["keep_polys"]:
        s, n = int(z["loop_starts"][i]), int(z["loop_totals"][i])
        lv = z["loops"][s:s + n]
        if helper[lv].any():
            continue
        for k in range(1, n - 1):
            tris.append((lv[0], lv[k], lv[k + 1]))
    return z["verts"].astype(np.float64), np.array(tris)


def tri_normals(v, t):
    n = np.cross(v[t[:, 1]] - v[t[:, 0]], v[t[:, 2]] - v[t[:, 0]])
    area = np.linalg.norm(n, axis=1) / 2
    return n / (2 * area[:, None] + 1e-18), area


def barycentric(p, tri):
    v0, v1 = tri[1] - tri[0], tri[2] - tri[0]
    v2 = p - tri[0]
    d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
    d20, d21 = v2 @ v0, v2 @ v1
    den = d00 * d11 - d01 * d01 + 1e-18
    bv = (d11 * d20 - d01 * d21) / den
    bw = (d00 * d21 - d01 * d20) / den
    return np.array([1 - bv - bw, bv, bw])


def main():
    a = _args()
    rng = np.random.default_rng(a.seed)
    tz = np.load(a.template)
    z = np.load(a.head)
    hz = np.load(a.shell)
    hv, ht = hz["verts"].astype(np.float64), hz["tris"]
    huv = hz["loop_uv"].reshape(len(ht), 3, 2)
    img = bpy.data.images.load(a.hair_tex)
    tw, th = img.size
    tex = np.asarray(img.pixels[:], np.float32).reshape(th, tw, 4)[..., :3]   # bottom row first
    # The painted texture is sRGB; strand colours are shaded as linear.
    tex = np.where(tex <= 0.04045, tex / 12.92, ((tex + 0.055) / 1.055) ** 2.4)

    sv, st = skin_mesh(z)
    head_bvh = BVHTree.FromPolygons([Vector(p) for p in sv], st.tolist())
    shell_bvh = BVHTree.FromPolygons([Vector(p) for p in hv], ht.tolist())

    ears = z["verts"][tz["vg__ears"]]
    eyes = z["verts"][np.concatenate([z["vg__helper-l-eye"], z["vg__helper-r-eye"]])]
    hairline_z = float(eyes[:, 2].mean()) + HAIRLINE_ABOVE_EYES
    ear_bottom = float(ears[:, 2].min())
    sideburn_z = ear_bottom + SIDEBURN * float(ears[:, 2].max() - ear_bottom)

    tn, area = tri_normals(sv, st)
    sn = np.zeros_like(sv)
    for k in range(3):
        np.add.at(sn, st[:, k], tn * area[:, None])
    sn /= np.linalg.norm(sn, axis=1, keepdims=True) + 1e-12

    # ------------------------------------------------------------------ the envelope
    # How far the hair reaches off each skin vertex: the shell's last crossing along the
    # normal. Zero where no hair lies over the skin.
    used = np.unique(st)
    outer = np.zeros(len(sv))
    for vi in used:
        o, d = Vector(sv[vi]), Vector(sn[vi])
        travelled = 0.0
        while travelled < REACH:
            hit = shell_bvh.ray_cast(o + d * 1e-4, d, REACH - travelled)
            if hit[0] is None:
                break
            travelled += hit[3] + 1e-4
            outer[vi] = travelled
            o = hit[0]
    # Smoothed among covered vertices only, so the envelope's edge stays where it is; well
    # smoothed, so a bump in the scan's hair does not raise a lone lock into a tuft.
    e = np.concatenate([st[:, [0, 1]], st[:, [1, 2]], st[:, [2, 0]]])
    e = np.unique(np.sort(np.r_[e, e[:, ::-1]], axis=1), axis=0)
    for _ in range(ENVELOPE_SMOOTHING):
        pos = outer > 0
        acc = np.zeros(len(sv))
        cnt = np.zeros(len(sv))
        ok = pos[e[:, 0]] & pos[e[:, 1]]
        np.add.at(acc, e[ok, 0], outer[e[ok, 1]])
        np.add.at(acc, e[ok, 1], outer[e[ok, 0]])
        np.add.at(cnt, e[ok, 0], 1)
        np.add.at(cnt, e[ok, 1], 1)
        upd = pos & (cnt > 0)
        outer[upd] = 0.5 * outer[upd] + 0.5 * acc[upd] / cnt[upd]

    def layer(p):
        """Nearest skin point, its smooth normal, height above it and the envelope there."""
        loc, _, fi, _ = head_bvh.find_nearest(Vector(p))
        if loc is None:
            return p, np.array([0.0, 0.0, 1.0]), 0.0, 0.0
        loc = np.array(loc)
        tri = st[fi]
        w = np.clip(barycentric(loc, sv[tri]), 0.0, 1.0)
        w /= w.sum()
        n = w @ sn[tri]
        n /= np.linalg.norm(n) + 1e-12
        return loc, n, float(np.dot(p - loc, n)), min(VOLUME * float(w @ outer[tri]), ENVELOPE_MAX)

    # ------------------------------------------------------------------ roots on the scalp
    n_cand = (a.guides * (a.children + 1)) * 4
    pick = rng.choice(len(st), n_cand, p=area / area.sum())
    r1, r2 = rng.random(n_cand), rng.random(n_cand)
    s1 = np.sqrt(r1)
    bary = np.stack([1 - s1, s1 * (1 - r2), s1 * r2], 1)
    pts = np.einsum("nk,nkj->nj", bary, sv[st[pick]])
    nrm = tn[pick]
    covered = np.zeros(n_cand, bool)
    for i in range(n_cand):
        hit = shell_bvh.ray_cast(Vector(pts[i] + nrm[i] * 0.001), Vector(nrm[i]), 0.12)
        covered[i] = hit[0] is not None
    # The face: front-facing skin, and anything in front of the temples, below the hairline.
    eye_y0 = float(eyes[:, 1].mean())
    face = ((nrm[:, 1] < -0.35) | (pts[:, 1] < eye_y0 + TEMPLE_BEHIND_EYES)) & (pts[:, 2] < hairline_z)
    ear_tree = KDTree(len(ears))
    for i, ep in enumerate(ears):
        ear_tree.insert(Vector(ep), i)
    ear_tree.balance()
    near_ear = np.array([ear_tree.find(Vector(p))[2] < 0.012 for p in pts])
    eye_z = float(eyes[:, 2].mean())
    # No roots in front of the ears below the brows: hair grown there lies flat and dense on
    # the skin and reads as a painted sticker, not a sideburn. The temple hair above covers
    # that edge.
    sideburn_root = (pts[:, 1] < float(ears[:, 1].min()) + 0.004) & (pts[:, 2] < eye_z + SIDEBURN_ROOTS)
    scalp = covered & ~face & ~near_ear & ~sideburn_root & (pts[:, 2] > ear_bottom - 0.004)
    eye_y = float(eyes[:, 1].mean())
    roots, root_n = pts[scalp], nrm[scalp]
    rng.shuffle(order := np.arange(len(roots)))
    roots, root_n = roots[order], root_n[order]
    n_g = min(a.guides, len(roots) // (a.children + 1))
    g_roots, g_n = roots[:n_g], root_n[:n_g]
    c_roots = roots[n_g:n_g * (a.children + 1)]
    # The crown: the scalp point highest towards the back.
    whorl = roots[np.argmax(roots[:, 2] + 0.35 * roots[:, 1])]

    # ------------------------------------------------------------------ guides
    # The style: swept up and back off the forehead with volume on top, falling in waves
    # at the sides and the nape; a share of the front locks fall forward instead.
    front_y = float(g_roots[:, 1].min())
    # Fringe locks come in bands along the hairline (whole locks, not single strands).
    band = np.sin(2 * np.pi * g_roots[:, 0] / 0.05 + rng.random() * 2 * np.pi)
    fringe = (g_roots[:, 1] < front_y + 0.035) & (band > np.cos(np.pi * a.fringe))
    back_flow = np.array([0.0, 1.0, -0.55])
    fringe_flow = np.array([0.0, -1.0, -0.9])
    up = np.array([0.0, 0.0, 1.0])
    down = np.array([0.0, 0.0, -1.0])
    # The parting: front hair sweeps away from it to either side as it goes back.
    part_x = float(whorl[0]) + a.part
    # Locks at the part itself lift and sweep aside; none falls straight down the forehead.
    fringe &= np.abs(g_roots[:, 0] - part_x) > 0.018
    front_half = g_roots[:, 1] < float(whorl[1]) - 0.02
    # The sweep grows with distance from the part, so locks either side never cross over it.
    sweep = np.where(front_half, np.clip((g_roots[:, 0] - part_x) / PART_RAMP, -1.0, 1.0), 0.0) * PART_SWEEP
    # On the sides of the head hair falls rather than sweeping back: it comes down around
    # the ears.
    side_fall = np.clip((np.abs(g_n[:, 0]) - 0.45) / 0.4, 0.0, 1.0)
    # ...behind the ears: the ears stay clear.
    side_flow = np.array([0.0, 0.9, -0.8])
    ear_front_y = float(ears[:, 1].min())
    climb = np.where(g_roots[:, 1] < front_y + 0.03, CLIMB_FRONT, CLIMB)
    # Depth in the envelope: most locks lie toward the outside, the rest fill underneath.
    depth = 0.35 + 0.62 * np.sqrt(rng.random(n_g))
    # Fringe locks lie low and fall forward; they do not stand up off the hairline.
    depth[fringe] = rng.uniform(0.3, 0.6, int(fringe.sum()))
    climb[fringe] = CLIMB
    steps = (rng.uniform(a.length[0], a.length[1], n_g) / STEP).astype(int).clip(8, MAX_STEPS)
    tail_len = rng.integers(1, 5, n_g)
    flick_from = ((1.0 - FLICK * rng.uniform(0.6, 1.2, n_g)) * steps).astype(int)
    phase = rng.random(n_g) * 2 * np.pi
    phase2 = rng.random(n_g) * 2 * np.pi
    wave_len = rng.uniform(a.wave_length[0], a.wave_length[1], n_g)
    weave_len = rng.uniform(0.06, 0.10, n_g)
    # Each lock bends its own way: a C-curve to one side, and a slightly different heading.
    curl = rng.uniform(-a.curl, a.curl, n_g)
    heading = rng.uniform(-0.25, 0.25, n_g)
    guides, g_frames = [], []
    for g in range(n_g):
        p = g_roots[g].copy()
        pts_g, nor_g, side_g, t_g, room_g = [p.copy()], [], [], [0.0], [0.0]
        arc, tail = 0.0, 0
        for k in range(steps[g]):
            loc, n, h, b = layer(p)
            radial = p - whorl
            radial -= n * np.dot(radial, n)
            rl = np.linalg.norm(radial)
            radial = radial / rl if rl > 1e-6 else np.zeros(3)
            # Curtains: fringe locks also sweep out from the part toward the brow ends.
            flow = fringe_flow + np.array([1.2 * sweep[g], 0.0, 0.0]) if fringe[g] else \
                (back_flow + np.array([sweep[g], 0.0, 0.0])) * (1.0 - side_fall[g]) + side_flow * side_fall[g]
            ft = 0.8 * flow + RADIAL * radial
            ft = ft - n * np.dot(ft, n)
            ft /= np.linalg.norm(ft) + 1e-12
            side = np.cross(n, ft)
            ft = ft + (heading[g] + curl[g] * k / steps[g]) * side
            ft /= np.linalg.norm(ft) + 1e-12
            side = np.cross(n, ft)
            if k == 0:
                nor_g.append(n)
                side_g.append(side)
            # Past the envelope (its edge, or outside the silhouette) the lock's end is free:
            # it turns out from the head and up a little, as a layered cut's ends do.
            if tail or b < MIN_ENVELOPE or h > b + 0.005:
                tail += 1
                # (A fringe lock's end falls over the forehead instead.)
                # (On top of the head "out" is up: there the end lies along the flow.)
                out_k = float(np.clip((0.7 - n[2]) / 0.3, 0.0, 1.0))
                d = 0.5 * ft + 0.8 * down + 0.15 * n if fringe[g] else \
                    0.6 * ft + out_k * (0.7 * n + 0.2 * up) + 0.15 * down
                t_here = 1.0
            elif k >= flick_from[g] and not fringe[g]:
                # The lock's last stretch turns out of its layer. On top of the head "out" is up:
                # there it would stand as a tuft, so the ends lie down instead.
                r = (k - flick_from[g]) / max(1, steps[g] - flick_from[g])
                lift_out = r * float(np.clip((0.7 - n[2]) / 0.3, 0.0, 1.0))
                d = ft + lift_out * (0.9 * n + 0.4 * up)
                t_here = 1.0
            else:
                target = np.clip(depth[g] + LAYER_WAVE * np.sin(2 * np.pi * arc / weave_len[g] + phase2[g]),
                                 0.15, 0.97) * b
                # Climb to the layer quickly; leave it slowly, so at the envelope's thin edge the
                # lock runs out of the volume (a free end) instead of tucking under.
                v_n = float(np.clip((target - h) / RISE, -0.3, climb[g]))
                # Broad S-waves across the flow; they open up away from the root.
                amp = a.wave * (0.3 + 0.7 * min(1.0, arc / 0.06))
                d = ft + v_n * n + amp * np.sin(2 * np.pi * arc / wave_len[g] + phase[g]) * side
                # Light reaching it: none under a full depth of hair, all at the silhouette (and
                # where the envelope is thin, e.g. the sideburns, it is near the silhouette).
                t_here = float(np.clip(1.0 - (b - h) / SHADE_DEPTH, 0.0, 1.0))
            d /= np.linalg.norm(d) + 1e-12
            p = p + d * STEP
            arc += STEP
            # Keep off the skin.
            loc2, n2, h2, b2 = layer(p)
            if h2 < 0.003:
                p = p + n2 * (0.003 - h2)
            # Hair frames the face, it does not curtain it: in front of the temples a strand
            # ends before it falls past the eyes; behind them it may fall to the jaw.
            if p[1] < eye_y + 0.02 and p[2] < eye_z + 0.012:
                break
            # In front of the ears it ends part way down them (sideburns), clear of the cheek.
            if p[1] < ear_front_y and p[2] < sideburn_z:
                break
            pts_g.append(p.copy())
            nor_g.append(n2)
            side_g.append(np.cross(n2, d))
            t_g.append(t_here)
            room_g.append(max(0.0, b2 - h2) if not tail else 0.0)
            if tail >= tail_len[g]:
                break
        guides.append(np.array(pts_g))
        sg = np.array(side_g)
        sg /= np.linalg.norm(sg, axis=1, keepdims=True) + 1e-12
        g_frames.append((np.array(nor_g), sg, np.array(t_g), np.array(room_g)))

    # ------------------------------------------------------------------ children
    # Interpolated, then clumped: a child follows the blend of its nearest guides' shapes
    # from its own root, so the hair is one continuous mass, and is drawn part of the way
    # toward its own guide, so the locks still read.
    K = 48
    uk = np.linspace(0.0, 1.0, K)
    G = np.zeros((n_g, K, 3))
    N = np.zeros((n_g, K, 3))
    TT = np.zeros((n_g, K))
    L = np.zeros(n_g)
    for g in range(n_g):
        gp = guides[g]
        nor_i, _, t_i, _ = g_frames[g]
        seg = np.linalg.norm(np.diff(gp, axis=0), axis=1)
        s = np.r_[0.0, np.cumsum(seg)]
        L[g] = s[-1]
        s = s / max(s[-1], 1e-9)
        for j in range(3):
            G[g, :, j] = np.interp(uk, s, gp[:, j])
            N[g, :, j] = np.interp(uk, s, nor_i[:, j])
        TT[g] = np.interp(uk, s, t_i)
    g_tree = KDTree(n_g)
    for i, r in enumerate(g_roots):
        g_tree.insert(Vector(r), i)
    g_tree.balance()
    lock_clump = np.clip(rng.uniform(0.9, 1.08, n_g) * a.clump, 0.0, 0.97)
    side_of_part = np.sign(np.round(sweep, 2))
    strands = [*guides]
    strand_t = [f[2] for f in g_frames]
    owner = np.zeros(len(c_roots), np.int64)
    stray = rng.random(len(c_roots)) < a.strays
    for c, r in enumerate(c_roots):
        near = g_tree.find_n(Vector(r), 3)
        idx = np.array([n_[1] for n_ in near])
        dist = np.array([n_[2] for n_ in near])
        g0 = idx[0]
        owner[c] = g0
        # Blend only guides of the same kind (fringe or not, same side of the part) whose
        # locks go the same way; across a parting the hair divides, it does not average.
        ok = (fringe[idx] == fringe[g0]) & (side_of_part[idx] == side_of_part[g0]) \
            & (np.linalg.norm(G[idx, -1] - G[g0, -1], axis=1) < 3.0 * dist + 0.03)
        idx, dist = idx[ok], dist[ok]
        w = 1.0 / (dist + 0.002) ** 2
        w /= w.sum()
        shape = np.einsum("j,jkd->kd", w, G[idx] - G[idx, :1])
        path = r[None, :] + shape
        own = G[g0] + (r - g_roots[g0])[None, :] * 0.1
        # The lock stays wide along its length and comes to a point at the tip.
        clump = 0.0 if stray[c] else lock_clump[g0]
        path = path + (clump * uk ** 2)[:, None] * (own - path)
        nrm_c = np.einsum("j,jkd->kd", w, N[idx])
        lift = rng.normal(0.0, 0.0012) * np.minimum(1.0, uk / 0.15)
        path = path + nrm_c * lift[:, None]
        if stray[c]:
            sd = np.cross(nrm_c, np.gradient(path, axis=0))
            sd /= np.linalg.norm(sd, axis=1, keepdims=True) + 1e-12
            path = path + 0.006 * uk[:, None] * (sd * np.sin(2 * np.pi * (uk * rng.uniform(0.8, 1.6)
                                                                          + rng.random()))[:, None]
                                                  + nrm_c * np.cos(2 * np.pi * (uk * rng.uniform(0.8, 1.6)
                                                                                + rng.random()))[:, None])
        jitter = 0.0012 * uk[:, None] * np.sin(2 * np.pi * (uk[:, None] * rng.uniform(1.0, 2.5)
                                                             + rng.random(3)[None, :]))
        path = path + jitter
        length = float(w @ L[idx]) * rng.uniform(0.85, 1.0)
        frac = length / max(float(w @ L[idx]), 1e-9)
        m = max(3, int(round(length / STEP)) + 1)
        um = np.linspace(0.0, frac, m)
        pts_c = np.stack([np.interp(um, uk, path[:, j]) for j in range(3)], 1)
        strands.append(pts_c)
        strand_t.append(np.interp(um, uk, w @ TT[idx]))

    # ------------------------------------------------------------------ colour and radius
    # Colours stay inside the hair's own palette: a strand whose sample lands on a stray
    # light patch of the shell texture would otherwise read as a blonde wisp.
    strand_cols = []
    counts = np.array([len(s) for s in strands])
    points = np.concatenate(strands).astype(np.float32)
    colours = np.zeros((len(points), 3), np.float32)
    radius = np.zeros(len(points), np.float32)
    for s in strands:
        m = len(s)
        mid = s[int(m * 0.65)]
        loc, _, fi, _ = shell_bvh.find_nearest(Vector(mid))
        if fi is None:
            col = np.array([0.25, 0.12, 0.06])
        else:
            w = barycentric(np.array(loc), hv[ht[fi]])
            uv = w @ huv[fi]
            x = int(np.clip(uv[0], 0, 1) * (tw - 1))
            y = int(np.clip(uv[1], 0, 1) * (th - 1))
            col = tex[y, x]
        strand_cols.append(col)
    strand_cols = np.array(strand_cols)
    lum = strand_cols @ np.array([0.2126, 0.7152, 0.0722])
    cap_lum = 1.25 * float(np.median(lum))
    strand_cols *= np.minimum(1.0, cap_lum / np.maximum(lum, 1e-6))[:, None]
    strand_cols *= BRIGHTEN   # the shell paint is baked under flat light; strands are shaded
    strand_cols *= WARM       # toward the painting's copper
    # ...and inside the hair's palette: a lock sampling a stray red or grey texel stays brown.
    strand_cols = 0.65 * strand_cols + 0.35 * np.median(strand_cols, 0)
    grey = (strand_cols @ np.array([0.2126, 0.7152, 0.0722]))[:, None]
    strand_cols = np.clip(grey + SATURATE * (strand_cols - grey), 0.0, None)
    # Each lock (a guide and its children) is a shade lighter or darker than its neighbours.
    lock_shade = rng.uniform(0.85, 1.18, n_g)
    strand_guide = np.r_[np.arange(n_g), owner]
    strand_cols *= lock_shade[strand_guide][:, None]
    start = 0
    for s, col, t in zip(strands, strand_cols, strand_t):
        m = len(s)
        u = np.linspace(0.0, 1.0, m)
        # Deep hair is in the shade of the hair over it: dark brown underneath, the painted
        # copper on the outer locks.
        shade = 0.42 + 0.72 * np.clip(t, 0.0, 1.0) ** 1.2
        # Dark at the root, the copper toward the tip.
        shade *= 0.72 + 0.4 * np.sqrt(u)
        colours[start:start + m] = col[None, :] * shade[:, None]
        radius[start:start + m] = 0.00034 * (1.0 - 0.7 * u)
        start += m
    # The scalp cap: scalp skin pushed out a little and darkened, so skin never shows
    # between strands (the dense under-layer real hair has).
    tri_c = sv[st].mean(1)
    tri_cov = np.array([shell_bvh.ray_cast(Vector(c + n * 0.001), Vector(n), 0.12)[0] is not None
                        for c, n in zip(tri_c, tn)])
    tri_face = ((tn[:, 1] < -0.35) | (tri_c[:, 1] < eye_y0 + TEMPLE_BEHIND_EYES)) & (tri_c[:, 2] < hairline_z)
    cap_sel = tri_cov & ~tri_face & (tri_c[:, 2] > ear_bottom)
    # Its edge sits well inside the hair, where strands are dense enough to hide it.
    cap_t = st[cap_sel]
    ce = np.sort(np.concatenate([cap_t[:, [0, 1]], cap_t[:, [1, 2]], cap_t[:, [2, 0]]]), axis=1)
    uniq, cnt = np.unique(ce, axis=0, return_counts=True)
    rim = np.unique(uniq[cnt == 1])
    rim_tree = KDTree(len(rim))
    for i, vi in enumerate(rim):
        rim_tree.insert(Vector(sv[vi]), i)
    rim_tree.balance()
    inner = np.array([rim_tree.find(Vector(c))[2] > CAP_INSET for c in tri_c[cap_sel]])
    # Where the strands part or thin out (in front of the ears, where the side hair goes
    # behind them) a dark cap would show as a painted patch: there the skin stays.
    sub = points[::12]
    pt_tree = KDTree(len(sub))
    for i, q in enumerate(sub):
        pt_tree.insert(Vector(q.tolist()), i)
    pt_tree.balance()
    dens = np.array([len(pt_tree.find_range(Vector((c + n * 0.006).tolist()), 0.01))
                     for c, n in zip(tri_c[cap_sel], tn[cap_sel])])
    dense = dens >= CAP_DENSITY * float(np.median(dens[inner])) if inner.any() else dens > 0
    cap_tris = cap_t[inner & dense]
    cap_verts = sv + sn * 0.0025
    cap_colour = np.median(strand_cols, 0) * 0.45
    np.savez_compressed(a.out, points=points, counts=counts, colours=colours, radius=radius,
                        cap_verts=cap_verts.astype(np.float32), cap_tris=cap_tris,
                        cap_colour=cap_colour.astype(np.float32))
    lengths = [len(gp) * STEP for gp in guides]
    print(json.dumps({"roots_scalp": int(scalp.sum()), "guides": n_g, "strands": int(len(strands)),
                      "points": int(len(points)), "hairline_z": hairline_z,
                      "cap_triangles": int(len(cap_tris)), "cap_thin_dropped": int((inner & ~dense).sum()),
                      "envelope_m": {"median": float(np.median(outer[outer > 0])),
                                     "max": float(outer.max())},
                      "guide_length_m": {"median": float(np.median(lengths)), "max": float(max(lengths))}}))


main()
