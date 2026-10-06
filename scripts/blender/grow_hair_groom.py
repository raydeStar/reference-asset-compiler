"""Grow a strand groom on a finished head, inside its hair envelope.

The hair shell taken from an acquisition is a good silhouette and a bad
surface: lumps, shards and painted smears. This grows real strands instead:
roots on the scalp, guide strands that rise off the head and fall with
gravity in waves, child strands clumped around each guide into locks, every
strand stopping where it leaves the shell (the envelope the pictures drew).
Colour comes from the painted hair texture, darker at the roots.

Deterministic (seeded); CPU; run with Blender for its BVH queries. Writes a
strands NPZ (points, per-strand point counts, per-point colour and radius)
that render_painted_head.py --strands draws as Cycles hair.

Usage:
  blender -b --factory-startup --python scripts/blender/grow_hair_groom.py -- \
      <template.npz> <head.npz> <hair_shell.npz> <hair_basecolor.png> <out_strands.npz> \
      [--guides 1500] [--children 30] [--seed 7]
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
BRIGHTEN = 1.5
WARM = np.array([1.1, 1.0, 0.86])
PART_SWEEP = 0.7
PART_RAMP = 0.035   # metres from the part over which the sideways sweep builds up
WHORL_CALM = 0.045  # metres from the crown within which hair lies flatter
TEMPLE_BEHIND_EYES = 0.03     # metres behind the eyes before hair may root at the temples
CAP_INSET = 0.03              # metres the dark scalp cap stays inside the hair's edge


def _args():
    argv = sys.argv[sys.argv.index("--") + 1:]
    p = argparse.ArgumentParser()
    for name in ("template", "head", "shell", "hair_tex", "out"):
        p.add_argument(name)
    p.add_argument("--guides", type=int, default=1200)
    p.add_argument("--children", type=int, default=65)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--wave-length", type=float, nargs=2, default=(0.045, 0.07),
                   help="range of wave lengths (metres); each lock draws its own")
    p.add_argument("--wave", type=float, default=0.55)
    p.add_argument("--fringe", type=float, default=0.25,
                   help="share of the front roots whose locks fall forward over the forehead")
    p.add_argument("--clump", type=float, default=0.85)
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
    centre = (sv[st].reshape(-1, 3).min(0) + sv[st].reshape(-1, 3).max(0)) / 2

    # ------------------------------------------------------------------ roots on the scalp
    tn, area = tri_normals(sv, st)
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
    for i, e in enumerate(ears):
        ear_tree.insert(Vector(e), i)
    ear_tree.balance()
    near_ear = np.array([ear_tree.find(Vector(p))[2] < 0.012 for p in pts])
    scalp = covered & ~face & ~near_ear & (pts[:, 2] > ear_bottom - 0.004)
    eye_z = float(eyes[:, 2].mean())
    eye_y = float(eyes[:, 1].mean())
    roots, root_n = pts[scalp], nrm[scalp]
    rng.shuffle(order := np.arange(len(roots)))
    roots, root_n = roots[order], root_n[order]
    n_g = min(a.guides, len(roots) // (a.children + 1))
    g_roots, g_n = roots[:n_g], root_n[:n_g]
    c_roots = roots[n_g:n_g * (a.children + 1)]
    # The crown: the scalp point highest towards the back.
    whorl = roots[np.argmax(roots[:, 2] + 0.35 * roots[:, 1])]

    def inside_shell(p):
        loc, nor, _, _ = shell_bvh.find_nearest(Vector(p))
        return loc is not None and (Vector(p) - loc).dot(nor) < 0

    def head_push(p):
        loc, nor, _, _ = head_bvh.find_nearest(Vector(p))
        if loc is None:
            return p, np.zeros(3)
        n = np.array(nor)
        gap = float(np.dot(p - np.array(loc), n))
        if gap < 0.003:
            p = p + n * (0.003 - gap)
        return p, n

    # ------------------------------------------------------------------ guides
    # The style: swept up and back off the forehead with volume on top, falling in waves
    # at the sides and the nape; a share of the front locks fall forward instead.
    front_y = float(g_roots[:, 1].min())
    fringe = (g_roots[:, 1] < front_y + 0.035) & (rng.random(n_g) < a.fringe)
    back_flow = np.array([0.0, 1.0, -0.55])
    fringe_flow = np.array([0.0, -1.0, -0.9])
    # The parting: front hair sweeps away from it to either side as it goes back.
    part_x = float(whorl[0]) + a.part
    front_half = g_roots[:, 1] < float(whorl[1]) - 0.02
    # The sweep grows with distance from the part, so locks either side never cross over it.
    sweep = np.where(front_half, np.clip((g_roots[:, 0] - part_x) / PART_RAMP, -1.0, 1.0), 0.0) * PART_SWEEP
    # Each lock rides the silhouette for 2.4-6.4 cm before it ends.
    ride_len = rng.integers(6, 17, n_g)
    side_fall = np.clip((np.abs(g_n[:, 0]) - 0.45) / 0.4, 0.0, 1.0)
    side_flow = np.array([0.0, 0.35, -1.0])
    ear_front_y = float(ears[:, 1].min())
    whorl_lift = np.clip(np.linalg.norm(g_roots - whorl, axis=1) / WHORL_CALM, 0.25, 1.0)
    crown_z = hairline_z + 0.05
    guides = []
    phase = rng.random(n_g) * 2 * np.pi
    wave_len = rng.uniform(a.wave_length[0], a.wave_length[1], n_g)
    for g in range(n_g):
        p = g_roots[g].copy()
        n0 = g_n[g]
        out = [p.copy()]
        entered = False
        ride = 0              # steps spent riding the silhouette
        ride_n = None         # the silhouette's normal where the strand rides it
        arc = 0.0
        for k in range(MAX_STEPS):
            p_safe, n = head_push(p)
            if not n.any():
                n = n0
            radial = p - whorl
            radial -= n * np.dot(radial, n)
            rl = np.linalg.norm(radial)
            radial = radial / rl if rl > 1e-6 else np.zeros(3)
            # On the sides of the head hair falls rather than sweeping back: it comes down
            # around the ears.
            flow = fringe_flow if fringe[g] else (back_flow + np.array([sweep[g], 0.0, 0.0])) * (1.0 - side_fall[g]) \
                + side_flow * side_fall[g]
            flow = flow - n * np.dot(flow, n)
            flow /= np.linalg.norm(flow) + 1e-12
            # The top stands up longer: the volume on the crown.
            lift = max(0.0, 1.0 - (0.021 if g_roots[g][2] > hairline_z + 0.03 else 0.035) * k)
            # At the crown itself hair has no direction to fall: it lies flat and fans out
            # instead of standing up in a tuft.
            lift *= whorl_lift[g]
            fall = min(1.0, 0.024 * k)
            # The very ends of falling locks flick outward (loose ends); on top of the head
            # "outward" is up, so there they just end.
            flick = 0.6 if ride >= ride_len[g] - 2 and p[2] < crown_z else 0.0
            d = (lift + flick) * n + 0.35 * radial + 0.8 * flow + fall * np.array([0.0, 0.0, -1.0])
            if ride_n is not None and not flick:
                # Riding the silhouette: turn along it instead of through it.
                through = float(np.dot(d, ride_n))
                if through > 0:
                    d = d - ride_n * through
            d /= np.linalg.norm(d) + 1e-12
            side = np.cross(d, n)
            sl = np.linalg.norm(side)
            if sl > 1e-6:
                # Waves loosen toward the ends, as tousled hair does.
                amp = a.wave * (0.4 + 0.6 * min(1.0, arc / 0.10))
                d = d + amp * np.sin(2 * np.pi * arc / wave_len[g] + phase[g]) * side / sl
                d /= np.linalg.norm(d)
            p = p_safe + d * STEP
            arc += STEP
            # Hair frames the face, it does not curtain it: in front of the temples a strand
            # ends before it falls past the eyes; behind them it may fall to the jaw
            # (sideburns, hair over the ears).
            if p[1] < eye_y + 0.02 and p[2] < eye_z + 0.012:
                break
            # In front of the ears it ends at the earlobes (sideburns), clear of the cheek.
            if p[1] < ear_front_y and p[2] < ear_bottom + 0.008:
                break
            # The shell is a layer over the scalp: a strand first crosses into it; where it
            # reaches the silhouette it bends and rides along it (held just inside) for the
            # rest of its length, as hair lies along the outside of a hairstyle. One that
            # never reaches the shell stays short.
            inside = inside_shell(p)
            if inside and ride == 0:
                entered = True
            elif entered or ride > 0:
                ride += 1
                loc, nor, _, _ = shell_bvh.find_nearest(Vector(p))
                if loc is not None:
                    ride_n = np.array(nor)
                    if not inside and not flick:
                        p = np.array(loc) - ride_n * 0.0015
            elif k >= 25:
                out.append(p.copy())
                break
            out.append(p.copy())
            if ride >= ride_len[g]:
                break
        guides.append(np.array(out))

    # ------------------------------------------------------------------ children, clumped
    g_tree = KDTree(n_g)
    for i, r in enumerate(g_roots):
        g_tree.insert(Vector(r), i)
    g_tree.balance()
    owner = np.array([g_tree.find(Vector(r))[1] for r in c_roots])
    strands = [*guides]
    for c, gi in enumerate(owner):
        gp = guides[gi]
        m = len(gp)
        u = np.linspace(0.0, 1.0, m)[:, None]
        off = (c_roots[c] - g_roots[gi])[None, :] * (1.0 - a.clump * u)
        jitter = 0.002 * u * np.sin(2 * np.pi * (u * rng.uniform(1.0, 2.5) + rng.random(3)[None, :]))
        keep = max(3, int(m * rng.uniform(0.75, 1.0)))
        strands.append((gp + off + jitter)[:keep])

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
            tri = hv[ht[fi]]
            # Barycentric of the nearest point on the shell triangle -> its UV.
            v0, v1 = tri[1] - tri[0], tri[2] - tri[0]
            v2 = np.array(loc) - tri[0]
            d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
            d20, d21 = v2 @ v0, v2 @ v1
            den = d00 * d11 - d01 * d01 + 1e-18
            bv = (d11 * d20 - d01 * d21) / den
            bw = (d00 * d21 - d01 * d20) / den
            uv = (1 - bv - bw) * huv[fi, 0] + bv * huv[fi, 1] + bw * huv[fi, 2]
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
    # Each lock (a guide and its children) is a shade lighter or darker than its neighbours.
    lock_shade = rng.uniform(0.82, 1.22, n_g)
    strand_guide = np.r_[np.arange(n_g), owner]
    strand_cols *= lock_shade[strand_guide][:, None]
    start = 0
    for s, col in zip(strands, strand_cols):
        m = len(s)
        u = np.linspace(0.0, 1.0, m)
        colours[start:start + m] = col[None, :] * (0.65 + 0.75 * np.sqrt(u))[:, None]
        radius[start:start + m] = 0.00034 * (1.0 - 0.7 * u)
        start += m
    # The scalp cap: scalp skin pushed out a little and darkened, so skin never shows
    # between strands (the dense under-layer real hair has).
    sn = np.zeros_like(sv)
    for k in range(3):
        np.add.at(sn, st[:, k], tn * area[:, None])
    sn /= np.linalg.norm(sn, axis=1, keepdims=True) + 1e-12
    tri_c = sv[st].mean(1)
    tri_cov = np.array([shell_bvh.ray_cast(Vector(c + n * 0.001), Vector(n), 0.12)[0] is not None
                        for c, n in zip(tri_c, tn)])
    tri_face = ((tn[:, 1] < -0.35) | (tri_c[:, 1] < eye_y0 + TEMPLE_BEHIND_EYES)) & (tri_c[:, 2] < hairline_z)
    cap_sel = tri_cov & ~tri_face & (tri_c[:, 2] > ear_bottom)
    # Its edge sits well inside the hair, where strands are dense enough to hide it.
    cap_t = st[cap_sel]
    e = np.sort(np.concatenate([cap_t[:, [0, 1]], cap_t[:, [1, 2]], cap_t[:, [2, 0]]]), axis=1)
    uniq, cnt = np.unique(e, axis=0, return_counts=True)
    rim = np.unique(uniq[cnt == 1])
    rim_tree = KDTree(len(rim))
    for i, vi in enumerate(rim):
        rim_tree.insert(Vector(sv[vi]), i)
    rim_tree.balance()
    inner = np.array([rim_tree.find(Vector(c))[2] > CAP_INSET for c in tri_c[cap_sel]])
    cap_tris = cap_t[inner]
    cap_verts = sv + sn * 0.0025
    cap_colour = np.median(strand_cols, 0) * 0.85
    np.savez_compressed(a.out, points=points, counts=counts, colours=colours, radius=radius,
                        cap_verts=cap_verts.astype(np.float32), cap_tris=cap_tris,
                        cap_colour=cap_colour.astype(np.float32))
    lengths = [len(gp) * STEP for gp in guides]
    print(json.dumps({"roots_scalp": int(scalp.sum()), "guides": n_g, "strands": int(len(strands)),
                      "points": int(len(points)), "hairline_z": hairline_z,
                      "guide_length_m": {"median": float(np.median(lengths)), "max": float(max(lengths))}}))


main()
