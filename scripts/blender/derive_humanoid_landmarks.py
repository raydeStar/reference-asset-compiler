"""Derive a Manny-compatible (ue5_manny) joint set for an unrigged humanoid mesh.

The portable, licence-free rig route. Auto-Rig Pro remains the higher-quality
option when a machine has it; this exists so a clean clone can still rig a
humanoid and run every downstream gate.

Sources, in order of trust:

1. **The mesh.** Height, torso midline, cross-section centroids for the spine,
   the crotch, per-leg centerlines, per-arm centerlines (A-pose or T-pose), toe
   and fingertip reach. Every limb pivot that can be measured is measured.
2. **Epic's Manny reference pose** (`profiles/rigging/manny-reference-pose.json`,
   extracted from the UE 5.8 template mesh) for the proportions the mesh cannot
   disambiguate: where the spine joints sit along the torso, the twist-bone
   fractions, the IK helper bones, and the finger and metacarpal layout, which
   is transplanted onto the measured hand, rotated to the measured forearm and
   scaled to the measured forearm length.

Output is the same landmark schema `rig_from_landmarks.py` consumes for the
mascot, plus overlay renders for review. Fingers are a template fit, not a
measurement: review the overlay before trusting hand deformation.
`--no-overlays` writes the same landmarks without the overlays (they render
with EEVEE, which needs a GPU); the JSON then has no `overlay_sha256`.

`--arm-joints measured` finds the elbow and wrist on the arm instead of placing
them by template: the elbow where the arm's centreline bends, the wrist just
past the forearm's thinnest girth, the same share of the arm on both sides
(`arm_joints` in the JSON says how each was found; a straight arm falls back to
a body's proportion). The default, `template`, is the original placement, kept
so earlier rigs can be repeated; it put the elbow joint 8 cm below the elbow of
an A-pose character. The shoulder joint stays a template position in both.

`--arm-joints measured_shoulder` does the same and also finds the shoulder joint:
on the upper arm's own centreline, carried up into the shoulder to the point that
is as far under the top of the shoulder as it is in from its outer side, both
shoulders then at one height and depth, and the collarbones starting either side
of the middle of the shoulders. The template shoulder is a share of the height
and of Manny's width: on Remora it sat 2 cm below the middle of her shoulder and
2 to 5 cm outside it, so the cap of her shoulder stayed with the collarbone and
the arm hinged underneath it. This script's own default stays `template`; the
game review road asks for `measured_shoulder` unless a recipe says otherwise.

Usage:
  blender -b --factory-startup --python-exit-code 1 --python \
      scripts/blender/derive_humanoid_landmarks.py -- \
      <mesh.fbx|glb> <out_dir> [--profile profiles/skeletons/ue5_manny.json] \
      [--manny profiles/rigging/manny-reference-pose.json] [--no-overlays] \
      [--arm-joints template|measured|measured_shoulder]
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_device import use_render_device  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def arg(argv, name, default, cast=str):
    if name in argv:
        return cast(argv[argv.index(name) + 1])
    return default


def import_mesh(path: Path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if path.suffix.lower() == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path))
    elif path.suffix.lower() in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=str(path))
    else:
        raise RuntimeError("Unsupported mesh type {0}".format(path.suffix))
    for obj in [o for o in bpy.data.objects if o.type == "ARMATURE"]:
        bpy.data.objects.remove(obj, do_unlink=True)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if not meshes:
        raise RuntimeError("No mesh in {0}".format(path))
    return meshes


def all_points(meshes) -> np.ndarray:
    chunks = []
    for obj in meshes:
        co = np.empty(len(obj.data.vertices) * 3)
        obj.data.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        m = np.asarray(obj.matrix_world)
        chunks.append(co @ m[:3, :3].T + m[:3, 3])
    return np.vstack(chunks)


def slab(points, z, half):
    return points[np.abs(points[:, 2] - z) < half]


def centerline(points, axis_values, bins):
    """Bin points along a scalar coordinate and return bin centroids and arc."""
    order = np.argsort(axis_values)
    points = points[order]
    axis_values = axis_values[order]
    edges = np.linspace(axis_values[0], axis_values[-1] + 1e-9, bins + 1)
    centres = []
    for i in range(bins):
        sel = (axis_values >= edges[i]) & (axis_values < edges[i + 1])
        if sel.sum() >= 3:
            centres.append(points[sel].mean(axis=0))
    centres = np.asarray(centres)
    seg = np.linalg.norm(np.diff(centres, axis=0), axis=1)
    arc = np.concatenate([[0.0], np.cumsum(seg)])
    return centres, arc


def at_arc(centres, arc, fraction):
    target = fraction * arc[-1]
    return np.array([np.interp(target, arc, centres[:, k]) for k in range(3)])


# --- measured arm joints (--arm-joints measured) ------------------------------------------------------------------
# The template route above never looks for the elbow: it puts it halfway between a template shoulder and a wrist
# taken 10.5% of the height back from the far end of the arm. On an A-pose arm that landed the elbow joint 8 cm
# below the elbow of the first character through the game review road (Remora, 2026-11-10), so every animation
# bent her forearm. These helpers find both joints on the mesh instead.

ELBOW_BY_PROPORTION = 0.56      # shoulder joint to elbow, as a share of shoulder joint to wrist (0.186 H : 0.146 H)
WRIST_PAST_THINNEST = 0.018     # of the height: the wrist joint sits just beyond the forearm's thinnest girth


def sample_triangles(tri, spacing, seed=0):
    """Points spread over triangles (n, 3, 3), about one per spacing x spacing of area, the same on every run."""
    tri = np.asarray(tri, float)
    e1, e2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    area = 0.5 * np.linalg.norm(np.cross(e1, e2), axis=1)
    index = np.repeat(np.arange(len(tri)), np.ceil(area / (spacing * spacing)).astype(int))
    rng = np.random.default_rng(seed)
    r1, r2 = rng.random(len(index)), rng.random(len(index))
    fold = r1 + r2 > 1.0
    r1[fold], r2[fold] = 1.0 - r1[fold], 1.0 - r2[fold]
    return tri[index, 0] + e1[index] * r1[:, None] + e2[index] * r2[:, None]


def surface_points(meshes, spacing):
    """Every vertex plus samples over every face, in world space: slices of a low-poly limb need more than vertices."""
    chunks = []
    for obj in meshes:
        mesh = obj.data
        co = np.empty(len(mesh.vertices) * 3)
        mesh.vertices.foreach_get("co", co)
        m = np.asarray(obj.matrix_world)
        world = co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]
        mesh.calc_loop_triangles()
        corners = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int32)
        mesh.loop_triangles.foreach_get("vertices", corners)
        chunks += [world, sample_triangles(world[corners.reshape(-1, 3)], spacing)]
    return np.vstack(chunks)


def arm_slices(points, shoulder, tip, lateral, H, step=0.01):
    """Cross-sections of one arm, one per `step` metres from the shoulder joint to the fingertip.

    Each slice keeps the points joined to the arm's outer surface: walking in from the side away from the body, the
    first air gap ends the arm, so a torso or thigh beside it is left out. A slice with no gap before the body
    (above the armpit, or a hand resting on the thigh) is marked merged. Returns (slices, arm length); a slice is
    None where the mesh is too thin to measure.
    """
    shoulder, tip = np.asarray(shoulder, float), np.asarray(tip, float)
    axis = tip - shoulder
    total = float(np.linalg.norm(axis))
    axis /= total
    out = np.asarray(lateral, float) - (np.asarray(lateral, float) @ axis) * axis
    if np.linalg.norm(out) < 0.2:      # a level arm: nothing is beside it, any direction across it will do
        out = np.array([0.0, 0.0, 1.0]) - axis[2] * axis
    u = out / np.linalg.norm(out)
    v = np.cross(axis, u)
    rel = points - shoulder
    t = rel @ axis
    a, b = rel @ u, rel @ v
    near = (np.hypot(a, b) < 0.09 * H) & (t >= 0.0) & (t <= total)
    order = np.argsort(t[near])
    t, a, b = t[near][order], a[near][order], b[near][order]
    gap, slices = 0.007 * H, []
    for k in range(int(total / step)):
        first, last = np.searchsorted(t, [k * step, (k + 1) * step])
        if last - first < 12:
            slices.append(None)
            continue
        inward = np.argsort(-a[first:last])
        aa, bb = a[first:last][inward], b[first:last][inward]
        breaks = np.nonzero(-np.diff(aa) > gap)[0]
        end = int(breaks[0]) + 1 if len(breaks) else len(aa)
        aa, bb = aa[:end], bb[:end]
        wide, deep = float(aa[0] - aa[-1]), float(bb.max() - bb.min())
        centre = shoulder + axis * (k + 0.5) * step + u * (aa[0] + aa[-1]) / 2 + v * (bb.max() + bb.min()) / 2
        slices.append({"t": (k + 0.5) * step, "centre": centre, "wide": wide, "deep": deep, "merged": wide > 0.075 * H})
    return slices, total


def two_line_break(points):
    """Where a centreline bends: the split into two straight pieces that fits best.

    Returns (index of the point at the bend, the bend in degrees, the two-piece error over the one-piece error); a
    straight line comes back with a small bend and an error ratio near 1.
    """
    points = np.asarray(points, float)

    def fit(q):
        _, sv, vt = np.linalg.svd(q - q.mean(axis=0))
        return vt[0], float((sv[1:] ** 2).sum())
    whole = fit(points)[1]
    best = None
    for b in range(4, len(points) - 4):
        d1, e1 = fit(points[:b + 1])
        d2, e2 = fit(points[b:])
        if best is None or e1 + e2 < best[2]:
            best = (b, math.degrees(math.acos(min(1.0, abs(float(d1 @ d2))))), e1 + e2)
    if best is None:
        return None
    return best[0], best[1], (best[2] / whole if whole > 1e-12 else 1.0)


def measure_arm(points, shoulder, tip, lateral, H):
    """One arm's elbow and wrist, measured along the line from the shoulder joint to the fingertip.

    The elbow is where the arm's centreline bends (an A-pose or T-pose mesh is modelled with the elbow a little
    bent); a straight arm has none to find and says so. The wrist is a fixed step past the forearm's thinnest girth.
    """
    slices, total = arm_slices(points, shoulder, tip, lateral, H)
    clean = [s for s in slices if s and not s["merged"]]
    out = {"total": total, "slices": clean, "elbow_measured": False, "wrist_measured": False, "notes": []}
    # from below the shoulder's own bulge to short of the wrist, so neither is taken for the elbow
    line = [s for s in clean if 0.15 * total <= s["t"] <= 0.60 * total]
    found = two_line_break([s["centre"] for s in line]) if len(line) >= 12 else None
    if found and found[1] >= 5.0 and found[2] <= 0.6:
        out.update(elbow_measured=True, elbow_t=line[found[0]]["t"], elbow_bend_deg=round(found[1], 1),
                   elbow_error_ratio=round(found[2], 3))
    else:
        out["notes"].append("no bend found in the arm's centreline" if found else "too little of the arm is clear of the body")
        if found:
            out.update(elbow_bend_deg=round(found[1], 1), elbow_error_ratio=round(found[2], 3))
    start = out.get("elbow_t", 0.33 * total)
    window = [s for s in clean if start + 0.40 * (total - start) <= s["t"] <= start + 0.62 * (total - start)]
    if len(window) >= 5:
        girth = np.array([s["wide"] + s["deep"] for s in window])
        smooth = np.convolve(np.pad(girth, 1, mode="edge"), np.ones(3) / 3, mode="valid")
        thin = window[int(np.argmin(smooth))]["t"]
        out.update(wrist_measured=True, thinnest_t=thin, wrist_t=min(thin + WRIST_PAST_THINNEST * H, total - 0.07 * H))
    else:
        out["notes"].append("the forearm near the wrist is not clear of the body")
    return out


def reconcile_arms(arms):
    """One elbow and one wrist position for both arms, as shares of each arm's own length.

    A body's two arms match; two separate measurements never quite do, and a rig with different left and right bone
    lengths plays every animation lopsided. The elbow counts for more on the side where the bend was clearer.
    """
    for key in ("elbow", "wrist"):
        got = [(m[key + "_t"] / m["total"], 1.0 - m.get(key + "_error_ratio", 0.0))
               for m in arms.values() if m and m[key + "_measured"]]
        share = sum(f * w for f, w in got) / sum(w for _, w in got) if got else None
        for m in arms.values():
            if m:
                m[key + "_share"] = share
    return arms


def centre_at(slices, t):
    """The arm's centre at a distance t from the shoulder joint, between the measured slices."""
    ts = np.array([s["t"] for s in slices])
    return np.array([np.interp(t, ts, [s["centre"][k] for s in slices]) for k in range(3)])


# --- measured shoulder joint (--arm-joints measured_shoulder) -------------------------------------------------------
# The template shoulder is a share of the height and of Manny's width. On Remora (2026-11-10) that put the joint 2 cm
# below the middle of her shoulder and 2 cm (right) to 5 cm (left) outside it, the left one 1.5 cm under her skin. The
# whole cap of the shoulder was then weighted to the collarbone and the arm hinged underneath it, and the upper arm
# bone (20 cm) came out shorter than the forearm (24 cm).

def clearance(points, origin, direction, radius):
    """How far it is from `origin` to the nearest surface along `direction`, among points within `radius` of that line."""
    rel = points - origin
    along = rel @ direction
    across = np.linalg.norm(rel - np.outer(along, direction), axis=1)
    hit = along[(across < radius) & (along > 0.002)]
    return float(hit.min()) if len(hit) else None


def measure_shoulder(points, got, template, sign, H):
    """The middle of one shoulder: on the upper arm's own centreline, carried up into the shoulder to the point that
    is as far under the top of the shoulder as it is in from its outer side.

    `got` is that arm's measure_arm result (its slices run from the template shoulder). Returns (point, facts) or
    (None, why not).
    """
    template = np.asarray(template, float)
    elbow_t = (got.get("elbow_share") or 0.33) * got["total"]
    line = [s["centre"] for s in got["slices"] if 0.30 * elbow_t <= s["t"] <= 0.92 * elbow_t]
    if len(line) < 5:
        return None, "too little of the upper arm is clear of the body"
    line = np.asarray(line)
    middle = line.mean(axis=0)
    along = np.linalg.svd(line - middle)[2][0]
    if along @ (line[-1] - line[0]) < 0:
        along = -along                                 # towards the hand
    foot = middle + along * float((template - middle) @ along)
    near = points[np.linalg.norm(points - template, axis=1) < 0.25 * H]
    up, out = np.array([0.0, 0.0, 1.0]), np.array([sign, 0.0, 0.0])
    radius, step = 0.006 * H, 0.0025 * H
    before = None
    for k in range(-8, 41):                            # from a little down the arm, up into the shoulder
        q = foot - along * (k * step)
        above, beside = clearance(near, q, up, radius), clearance(near, q, out, radius)
        if above is None or beside is None:
            break
        if above <= beside:
            if before is None:
                return None, "the template shoulder is already at the top of the shoulder"
            q0, d0 = before
            d1 = above - beside
            q = q0 + (q - q0) * (d0 / (d0 - d1)) if d0 > d1 else q
            above, beside = clearance(near, q, up, radius) or above, clearance(near, q, out, radius) or beside
            moved = float(np.linalg.norm(q - template))
            if not (0.012 * H <= above <= 0.06 * H) or moved > 0.08 * H:
                return None, "the shoulder found is not believable ({0:.1f} cm under the top, {1:.1f} cm from the template)".format(
                    above * 100, moved * 100)
            return q, {"under_top_cm": round(above * 100, 1), "in_from_side_cm": round(beside * 100, 1),
                       "from_template_cm": round(moved * 100, 1)}
        before = (q, above - beside)
    return None, "no point in the shoulder is as deep as it is far in from the side"


def reconcile_shoulders(found, templates):
    """Both shoulder joints at one height and one depth, each at its own width. `found` and `templates` map a side to
    a point (found: or None). One shoulder that could not be measured takes the other's move from its template."""
    got = {side: np.asarray(p, float) for side, p in found.items() if p is not None}
    if not got:
        return {}
    out = {}
    for side in found:
        if side in got:
            out[side] = got[side].copy()
        else:
            other = next(iter(got))
            move = got[other] - np.asarray(templates[other], float)
            out[side] = np.asarray(templates[side], float) + move * np.array([-1.0, 1.0, 1.0])
    for axis in (1, 2):
        level = float(np.mean([p[axis] for p in out.values()]))
        for p in out.values():
            p[axis] = level
    return out


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:]
    mesh_path, out_dir = (Path(a).resolve() for a in argv[:2])
    arm_mode = arg(argv, "--arm-joints", "template")
    if arm_mode not in ("template", "measured", "measured_shoulder"):
        raise RuntimeError("--arm-joints is template, measured or measured_shoulder, not {0}".format(arm_mode))
    shoulder_mode, arm_mode = arm_mode == "measured_shoulder", "template" if arm_mode == "template" else "measured"
    profile_path = Path(arg(argv, "--profile", str(ROOT / "profiles/skeletons/ue5_manny.json"))).resolve()
    manny_path = Path(arg(argv, "--manny", str(ROOT / "profiles/rigging/manny-reference-pose.json"))).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    landmarks_path = out_dir / "humanoid-landmarks.json"
    if landmarks_path.exists():
        raise RuntimeError("Refusing to overwrite landmark evidence: {0}".format(landmarks_path))
    profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    manny = json.loads(manny_path.read_text(encoding="utf-8-sig"))

    meshes = import_mesh(mesh_path)
    pts = all_points(meshes)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    H = float(hi[2] - lo[2])
    if H < 0.3:
        raise RuntimeError("Mesh is {0:.3f} m tall; expected metres".format(H))

    # Manny template in the Blender frame: UE component (x, y, z) cm, +Y forward
    # -> Blender (x, -y, z) m, -Y forward, normalized by Manny's height.
    MH = float(manny["height_cm"])
    T = {name: np.array([b["position_cm"][0], -b["position_cm"][1], b["position_cm"][2]]) / MH
         for name, b in manny["bones"].items()}
    parents = {name: b["parent"] for name, b in manny["bones"].items()}

    # Torso midline: central cluster at hip and chest heights.
    def central(z, half, window):
        s = slab(pts, z, half)
        s = s[np.abs(s[:, 0] - (lo[0] + hi[0]) * 0.5) < window]
        return s
    hip_band = central(lo[2] + 0.55 * H, 0.03 * H, 0.16 * H)
    mid_x = float(np.median(hip_band[:, 0]))
    # Gear worn on one side (pouches, a shoulder plate, a holster) drags the hip median sideways: CH-03 Raider's
    # read 3.7 cm off and shifted both shoulders. The feet are a symmetric pair; take the midline between them
    # when both are found.
    soles = pts[pts[:, 2] < lo[2] + 0.04 * H]
    left_f, right_f = soles[soles[:, 0] > mid_x], soles[soles[:, 0] < mid_x]
    if len(left_f) > 20 and len(right_f) > 20:
        mid_x = float(0.5 * (left_f[:, 0].mean() + right_f[:, 0].mean()))

    def torso_centroid(z, window=0.12 * H):
        s = slab(pts, z, 0.02 * H)
        s = s[np.abs(s[:, 0] - mid_x) < window]
        return s.mean(axis=0) if len(s) >= 8 else None

    joints = {}
    notes = []

    # Spine chain at Manny's height fractions, y from the mesh cross-section.
    for name in ("pelvis", "spine_01", "spine_02", "spine_03", "spine_04", "spine_05", "neck_01", "neck_02", "head"):
        z = lo[2] + T[name][2] * H
        c = torso_centroid(z, 0.12 * H if not name.startswith("neck") and name != "head" else 0.10 * H)
        y = float(c[1]) if c is not None else float(T[name][1] * H)
        joints[name] = [mid_x, y, float(z)]
    head_top = float(hi[2])

    # Crotch: highest z below the hips where the centre column is nearly empty. "Nearly" is relative to the
    # hips' own column: a few stray cloth vertices between the legs (inner skirts, a sagging seam) kept the
    # strict empty test running down to the knees on CH-03 Raider (2026-11-01).
    def column(z):
        s = slab(pts, z, 0.01 * H)
        return np.count_nonzero(np.abs(s[:, 0] - mid_x) < 0.015 * H)
    hips_column = np.median([column(z) for z in np.arange(lo[2] + 0.47 * H, lo[2] + 0.55 * H, 0.01 * H)])
    # The gap must hold for a run of levels: a belt hem or jacket edge leaves a thin empty band at the waist
    # (CH-03 Raider again, 0.91 m), while the real crotch opens into the gap between the legs and stays open.
    levels = np.arange(lo[2] + 0.55 * H, lo[2] + 0.25 * H, -0.005 * H)
    low = [column(z) <= max(0, 0.15 * hips_column) for z in levels]
    run = 8
    crotch_z = None
    for i in range(len(levels) - run):
        if all(low[i:i + run]):
            crotch_z = float(levels[i])
            break
    if crotch_z is None:
        crotch_z = lo[2] + 0.47 * H
        notes.append("crotch not detected; Manny proportion used")

    # Legs: per side, centreline from just below the crotch to the ankle.
    ankle_z = lo[2] + 0.046 * H
    for side, sign in (("l", 1.0), ("r", -1.0)):
        leg = pts[(pts[:, 2] < crotch_z) & (pts[:, 2] > ankle_z - 0.01 * H) & (sign * (pts[:, 0] - mid_x) > 0)]
        if len(leg) < 50:
            raise RuntimeError("leg_{0}: too few vertices below the crotch".format(side))
        centres, _arc = centerline(leg, -leg[:, 2], 24)
        # centres run top (high z) to bottom; interpolate on z directly.
        zs = centres[:, 2]
        def leg_xy(z):
            idx = np.argsort(zs)
            return np.array([np.interp(z, zs[idx], centres[idx, k]) for k in (0, 1)])
        hip_z = crotch_z + 0.04 * H
        knee_z = ankle_z + 0.5 * (hip_z - ankle_z)
        hx, hy = leg_xy(crotch_z - 0.02 * H)
        kx, ky = leg_xy(knee_z)
        ax_, ay = leg_xy(ankle_z + 0.02 * H)
        joints["thigh_" + side] = [float(hx), float(hy), float(hip_z)]
        joints["calf_" + side] = [float(kx), float(ky), float(knee_z)]
        joints["foot_" + side] = [float(ax_), float(ay), float(ankle_z)]
        foot = pts[(pts[:, 2] < lo[2] + 0.06 * H) & (np.abs(pts[:, 0] - ax_) < 0.08 * H)]
        toe_y = float(foot[:, 1].min()) if len(foot) else ay - 0.14 * H
        joints["ball_" + side] = [float(ax_), toe_y + 0.4 * (ay - toe_y), float(lo[2] + 0.005 * H)]
        joints["toe_end_" + side] = [float(ax_), toe_y, float(lo[2] + 0.005 * H)]

    def beyond_torso(side_sign, cloud):
        # Below the chest an arm point must reach further out, so gear on the hips and thighs (a thigh pouch,
        # a holster) is not read as arm; hands in A- or T-pose are well beyond it.
        lat_ = side_sign * (cloud[:, 0] - mid_x)
        return cloud[(lat_ > np.where(cloud[:, 2] > lo[2] + 0.62 * H, 0.14 * H, 0.18 * H))
                     & (cloud[:, 2] > lo[2] + 0.40 * H) & (cloud[:, 2] < lo[2] + 0.90 * H)]

    def template_shoulder(side_sign):
        return np.array([mid_x + side_sign * T["upperarm_l"][0] * H,
                         joints["spine_05"][1] + (T["upperarm_l"][1] - T["spine_05"][1]) * H,
                         lo[2] + T["upperarm_l"][2] * H])

    # Measured arm joints: both arms first, so they can be made to agree.
    measured_arms, arm_report = {}, None
    if arm_mode == "measured":
        dense = surface_points(meshes, 0.0018 * H)
        for side, sign in (("l", 1.0), ("r", -1.0)):
            far = beyond_torso(sign, dense)
            shoulder = template_shoulder(sign)
            if len(far) < 50:
                measured_arms[side] = None
                continue
            tip = far[np.argmax(np.linalg.norm(far - shoulder, axis=1))]
            measured_arms[side] = dict(measure_arm(dense, shoulder, tip, np.array([sign, 0.0, 0.0]), H), tip=tip)
        reconcile_arms(measured_arms)
        arm_report = {"mode": "measured"}

    # Measured shoulder joints: each on its own arm's centreline, then both at one height and depth.
    measured_shoulders, shoulder_facts = {}, {}
    if shoulder_mode:
        found = {}
        for side, sign in (("l", 1.0), ("r", -1.0)):
            got = measured_arms.get(side)
            point, facts = measure_shoulder(dense, got, template_shoulder(sign), sign, H) if got else (None, "the arm could not be measured")
            found[side], shoulder_facts[side] = point, facts
        measured_shoulders = reconcile_shoulders(found, {"l": template_shoulder(1.0), "r": template_shoulder(-1.0)})
        for side in "lr":
            if found[side] is None:
                notes.append("shoulder_{0}: {1}; {2}".format(side, shoulder_facts[side],
                             "placed as the other shoulder was" if measured_shoulders else "template shoulder kept"))
                shoulder_facts[side] = {"shoulder": "from the other arm" if measured_shoulders else "template"}
            else:
                shoulder_facts[side] = dict(shoulder_facts[side], shoulder="measured")
        arm_report["mode"] = "measured_shoulder"
    # the collarbones start either side of the middle of the shoulders, so they come out the same length
    collar_x = float(np.mean([p[0] for p in measured_shoulders.values()])) if len(measured_shoulders) == 2 else mid_x

    # Arms: points outside the torso width between hip and head height.
    for side, sign in (("l", 1.0), ("r", -1.0)):
        arm = beyond_torso(sign, pts)
        if len(arm) < 50:
            raise RuntimeError("arm_{0}: too few vertices beyond the torso".format(side))
        shoulder_template = template_shoulder(sign)
        # Order the arm by distance from the shoulder, not by sideways reach: in an A-pose the thumb sticks out
        # further sideways than the fingertips hang, which ended the chain at the thumb and put the wrist 0.2 m
        # high on CH-03 Raider (2026-11-01).
        reach = np.linalg.norm(arm - shoulder_template, axis=1)
        centres, arc = centerline(arm, reach, 20)
        hand_len = 0.105 * H
        total = arc[-1]
        if total < 0.3 * H:
            notes.append("arm_{0}: short arc {1:.2f} m; sleeve or pose may be tight to the body".format(side, total))
        wrist = at_arc(centres, arc, max(0.0, (total - hand_len) / total))
        shoulder = shoulder_template
        elbow = 0.5 * (shoulder + wrist)
        # Bend the elbow toward the measured centreline at its mid arc.
        mid_c = at_arc(centres, arc, 0.5 * (total - hand_len) / total)
        elbow = 0.5 * elbow + 0.5 * mid_c
        hand_end = at_arc(centres, arc, 1.0)
        got = measured_arms.get(side)
        if arm_mode == "measured":
            if got and len(got["slices"]) >= 8:
                # the wrist: the share both arms agree on, else Manny's hand length back from the fingertip
                wrist_t = got["wrist_share"] * got["total"] if got["wrist_share"] else got["total"] - hand_len
                # the elbow: the share both arms agree on, else the proportion of a body (a straight arm has no bend)
                elbow_t = got["elbow_share"] * got["total"] if got["elbow_share"] else ELBOW_BY_PROPORTION * wrist_t
                wrist, elbow, hand_end = centre_at(got["slices"], wrist_t), centre_at(got["slices"], elbow_t), got["tip"]
                for note in got["notes"]:
                    notes.append("arm_{0}: {1}".format(side, note))
                arm_report[side] = {
                    "shoulder_joint_to_fingertip_cm": round(got["total"] * 100, 1),
                    "elbow": "measured" if got["elbow_measured"] else ("from the other arm" if got["elbow_share"] else "by proportion"),
                    "wrist": "measured" if got["wrist_measured"] else ("from the other arm" if got["wrist_share"] else "by hand length"),
                    "own_elbow_at_cm": round(got["elbow_t"] * 100, 1) if got["elbow_measured"] else None,
                    "own_elbow_bend_deg": got.get("elbow_bend_deg"), "own_elbow_error_ratio": got.get("elbow_error_ratio"),
                    "own_thinnest_at_cm": round(got["thinnest_t"] * 100, 1) if got["wrist_measured"] else None,
                    "elbow_at_cm": round(elbow_t * 100, 1), "wrist_at_cm": round(wrist_t * 100, 1),
                    "upper_arm_cm": round(float(np.linalg.norm(elbow - shoulder)) * 100, 1),
                    "forearm_cm": round(float(np.linalg.norm(wrist - elbow)) * 100, 1),
                }
            else:
                notes.append("arm_{0}: could not be measured; template elbow and wrist kept".format(side))
                arm_report[side] = {"elbow": "template", "wrist": "template"}
        if side in measured_shoulders:      # the elbow and wrist above stay where they were found on the arm
            arm_report[side]["template_upper_arm_cm"] = round(float(np.linalg.norm(elbow - shoulder)) * 100, 1)
            shoulder = measured_shoulders[side]
            arm_report[side].update(shoulder_facts[side], upper_arm_cm=round(float(np.linalg.norm(elbow - shoulder)) * 100, 1))
        elif shoulder_mode:
            arm_report[side].update(shoulder_facts[side])
        joints["clavicle_" + side] = [collar_x + sign * T["clavicle_l"][0] * H, joints["spine_05"][1] + (T["clavicle_l"][1] - T["spine_05"][1]) * H, lo[2] + T["clavicle_l"][2] * H]
        joints["upperarm_" + side] = shoulder.tolist()
        joints["lowerarm_" + side] = elbow.tolist()
        joints["hand_" + side] = wrist.tolist()
        joints["hand_end_" + side] = hand_end.tolist()

        # Fingers and metacarpals: Manny's hand layout rotated onto the measured
        # forearm and scaled to the measured forearm length.
        manny_fore = T["hand_l"] - T["lowerarm_l"]
        mesh_fore = wrist - elbow
        scale = float(np.linalg.norm(mesh_fore) / np.linalg.norm(manny_fore))
        mirror = np.array([sign, 1.0, 1.0])
        rot = Vector(manny_fore * mirror).rotation_difference(Vector(mesh_fore)).to_matrix()
        R = np.asarray(rot)
        for name in T:
            if not name.endswith("_l"):
                continue
            base = name[:-2]
            if not any(base.startswith(d) for d in ("thumb", "index", "middle", "ring", "pinky")):
                continue
            offset = (T[name] - T["hand_l"]) * mirror * scale
            joints[base + "_" + side] = (wrist + R @ offset).tolist()

    # Twist bones by Manny's fraction along each limb segment.
    def frac(a, b, f):
        a = np.asarray(joints[a])
        b = np.asarray(joints[b])
        return (a + (b - a) * f).tolist()
    for side in "lr":
        joints["upperarm_twist_01_" + side] = frac("upperarm_" + side, "lowerarm_" + side, 1 / 3)
        joints["upperarm_twist_02_" + side] = frac("upperarm_" + side, "lowerarm_" + side, 2 / 3)
        joints["lowerarm_twist_01_" + side] = frac("lowerarm_" + side, "hand_" + side, 1 / 3)
        joints["lowerarm_twist_02_" + side] = frac("lowerarm_" + side, "hand_" + side, 2 / 3)
        joints["thigh_twist_01_" + side] = frac("thigh_" + side, "calf_" + side, 1 / 3)
        joints["thigh_twist_02_" + side] = frac("thigh_" + side, "calf_" + side, 2 / 3)
        joints["calf_twist_01_" + side] = frac("calf_" + side, "foot_" + side, 1 / 3)
        joints["calf_twist_02_" + side] = frac("calf_" + side, "foot_" + side, 2 / 3)
    joints["root"] = [0.0, 0.0, float(lo[2])]
    joints["ik_foot_root"] = joints["root"]
    joints["ik_hand_root"] = joints["root"]
    joints["ik_foot_l"] = joints["foot_l"]
    joints["ik_foot_r"] = joints["foot_r"]
    joints["ik_hand_gun"] = joints["hand_r"]
    joints["ik_hand_l"] = joints["hand_l"]
    joints["ik_hand_r"] = joints["hand_r"]
    joints["head_end"] = [mid_x, joints["head"][1], head_top - 0.02 * H]
    joints["ik_root_end"] = [0.0, 0.0, float(lo[2]) + 0.05 * H]

    required = list(profile["required_bones"])
    optional = list(profile.get("optional_bones", []))
    # Manny's interaction and center_of_mass helpers (optional in the profile since
    # 2026-10-07, for the game export's gate) have no joint here; the proxy rig
    # leaves them out, as the first character's measured landmarks do.
    wanted = [b for b in required + optional
              if (b in T or b == "root") and b not in ("interaction", "center_of_mass")]
    if profile.get("root_bone") and profile["root_bone"] not in wanted:
        wanted.insert(0, profile["root_bone"])
    missing = [b for b in required if b not in joints]
    if missing:
        raise RuntimeError("Derivation left required bones without joints: {0}".format(missing))

    # Tails: the designated child, else a short continuation of the parent's direction.
    chain_child = {"pelvis": "spine_01", "spine_01": "spine_02", "spine_02": "spine_03", "spine_03": "spine_04",
                   "spine_04": "spine_05", "spine_05": "neck_01", "neck_01": "neck_02", "neck_02": "head", "head": "head_end",
                   "root": "ik_root_end", "ik_foot_root": "ik_root_end", "ik_hand_root": "ik_root_end"}
    for side in "lr":
        chain_child.update({
            "clavicle_" + side: "upperarm_" + side, "upperarm_" + side: "lowerarm_" + side,
            "lowerarm_" + side: "hand_" + side, "hand_" + side: "middle_01_" + side,
            "thigh_" + side: "calf_" + side, "calf_" + side: "foot_" + side, "foot_" + side: "ball_" + side,
            "ball_" + side: "toe_end_" + side,
            "upperarm_twist_01_" + side: "upperarm_twist_02_" + side, "upperarm_twist_02_" + side: "lowerarm_" + side,
            "lowerarm_twist_01_" + side: "lowerarm_twist_02_" + side, "lowerarm_twist_02_" + side: "hand_" + side,
            "thigh_twist_01_" + side: "thigh_twist_02_" + side, "thigh_twist_02_" + side: "calf_" + side,
            "calf_twist_01_" + side: "calf_twist_02_" + side, "calf_twist_02_" + side: "foot_" + side,
        })
        for digit in ("thumb", "index", "middle", "ring", "pinky"):
            if digit != "thumb":
                chain_child["{0}_metacarpal_{1}".format(digit, side)] = "{0}_01_{1}".format(digit, side)
            chain_child["{0}_01_{1}".format(digit, side)] = "{0}_02_{1}".format(digit, side)
            chain_child["{0}_02_{1}".format(digit, side)] = "{0}_03_{1}".format(digit, side)
            # fingertip: continue the last phalanx by its own length
            p2 = np.asarray(joints["{0}_02_{1}".format(digit, side)])
            p3 = np.asarray(joints["{0}_03_{1}".format(digit, side)])
            joints["{0}_tip_{1}".format(digit, side)] = (p3 + (p3 - p2)).tolist()
            chain_child["{0}_03_{1}".format(digit, side)] = "{0}_tip_{1}".format(digit, side)
    for side in "lr":
        for name in ("ik_foot_", "ik_hand_"):
            b = np.asarray(joints[name + side])
            joints[name + side + "_end"] = (b + np.array([0, 0, 0.05 * H])).tolist()
            chain_child[name + side] = name + side + "_end"
    joints["ik_hand_gun_end"] = (np.asarray(joints["ik_hand_gun"]) + np.array([0, 0, 0.05 * H])).tolist()
    chain_child["ik_hand_gun"] = "ik_hand_gun_end"

    bones = {}
    for name in wanted:
        parent = parents.get(name)
        if name == "root":
            parent = None
        elif parent not in wanted:
            parent = "root"
        tail = chain_child.get(name)
        if tail is None or tail not in joints:
            raise RuntimeError("No tail rule for bone {0}".format(name))
        bones[name] = {"head": name, "tail": tail, "parent": parent,
                       "deform": not (name == "root" or name.startswith("ik_"))}

    payload = {
        "schema": "reference-asset-compiler.humanoid-landmarks.v1",
        "skeleton_profile": profile["profile_id"],
        "payload_fbx": str(mesh_path), "payload_fbx_sha256": sha256(mesh_path),
        "manny_reference": str(manny_path), "manny_reference_sha256": sha256(manny_path),
        "coordinate_space": "mesh_world_meters_blender_minus_y_forward",
        "height_m": H, "midline_x": mid_x, "crotch_z": crotch_z,
        "method": ("Spine, neck and head at Manny's height fractions with y from mesh cross-sections; crotch and per-leg centrelines "
                   "from the mesh; arm centrelines from the mesh beyond the torso with the hand as the outer 10.5% of height; "
                   "fingers and metacarpals are Manny's layout rotated onto the measured forearm and scaled to it; twist bones at thirds; "
                   "IK helpers at Manny's parents."),
        "measured_bones": sorted(b for b in bones if any(b.startswith(p) for p in ("thigh_", "calf_", "foot_", "ball_", "lowerarm_", "hand_"))
                                 and "twist" not in b),
        "template_bones": sorted(b for b in bones if any(b.startswith(p) for p in ("thumb", "index", "middle", "ring", "pinky", "ik_", "clavicle", "upperarm_")) or "twist" in b),
        "notes": notes,
        "joints": joints,
        "bones": bones,
        "reviewed_by": None,
        "review_status": "derived_pending_overlay_review",
    }
    if arm_report:
        payload["arm_joints"] = arm_report
        payload["method"] = payload["method"].replace(
            "arm centrelines from the mesh beyond the torso with the hand as the outer 10.5% of height",
            "arms sliced from the template shoulder to the fingertip, the elbow where the arm's centreline bends and the wrist "
            "just past the forearm's thinnest girth, the same share of the arm on both sides (arm_joints says how each was found)")
        if shoulder_mode:
            payload["method"] += (" Shoulder joints on the upper arm's centreline, as far under the top of the shoulder as in from "
                                  "its side, both at one height and depth; collarbones start either side of the middle of the shoulders.")
            if measured_shoulders:
                payload["measured_bones"] = sorted(payload["measured_bones"] + ["upperarm_l", "upperarm_r"])
                payload["template_bones"] = [b for b in payload["template_bones"] if b not in ("upperarm_l", "upperarm_r")]
    landmarks_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    summary = "[LANDMARKS] {0} bones={1} height={2:.3f} crotch_z={3:.3f} notes={4}".format(
        landmarks_path, len(bones), H, crotch_z, notes)
    if "--no-overlays" in argv:
        # The overlays render with EEVEE, which needs a GPU; the landmarks above are complete without them.
        print(summary + " overlays=skipped")
        return 0

    # Overlay renders.
    scene = bpy.context.scene
    use_render_device(scene)
    ghost = bpy.data.materials.new("Ghost")
    ghost.use_nodes = True
    g = ghost.node_tree.nodes["Principled BSDF"]
    g.inputs["Base Color"].default_value = (0.75, 0.75, 0.78, 1.0)
    g.inputs["Alpha"].default_value = 0.28
    if hasattr(ghost, "surface_render_method"):
        ghost.surface_render_method = "BLENDED"
    for m in meshes:
        m.data.materials.clear()
        m.data.materials.append(ghost)

    def emissive(name, rgb):
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        b = m.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (*rgb, 1.0)
        emission = b.inputs.get("Emission Color") or b.inputs.get("Emission")
        emission.default_value = (*rgb, 1.0)
        if "Emission Strength" in b.inputs:
            b.inputs["Emission Strength"].default_value = 3.0
        return m
    mats = {"l": emissive("L", (1.0, 0.45, 0.05)), "r": emissive("R", (0.1, 0.5, 1.0)), "c": emissive("C", (0.2, 1.0, 0.3))}
    radius = 0.010 * H
    for name, spec in bones.items():
        if name.startswith("ik_"):
            continue
        s = "l" if name.endswith("_l") else "r" if name.endswith("_r") else "c"
        a = Vector(joints[spec["head"]])
        b = Vector(joints[spec["tail"]])
        r = radius * (0.5 if any(name.startswith(d) for d in ("thumb", "index", "middle", "ring", "pinky")) else 1.0)
        bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=a)
        bpy.context.object.data.materials.append(mats[s])
        d = b - a
        if d.length > 1e-6:
            bpy.ops.mesh.primitive_cylinder_add(radius=r * 0.4, depth=d.length, location=(a + b) * 0.5)
            cyl = bpy.context.object
            cyl.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
            cyl.data.materials.append(mats[s])
    world = bpy.data.worlds.new("W")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.18, 0.18, 0.18, 1.0)
    scene.world = world
    scene.view_settings.view_transform = "Standard"
    scene.render.resolution_x = scene.render.resolution_y = 1024
    scene.render.image_settings.file_format = "PNG"
    if hasattr(scene, "eevee"):
        scene.eevee.taa_render_samples = 16
    centre = Vector((lo + hi) * 0.5)
    extent = float(max(hi - lo))
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 85.0
    cam = bpy.data.objects.new("Cam", cam_data)
    bpy.context.collection.objects.link(cam)
    scene.camera = cam
    fov = 2.0 * math.atan(0.5 * cam_data.sensor_width / cam_data.lens)
    distance = (extent * 1.25) / (2.0 * math.tan(fov * 0.5))
    views = {}
    for view, angle in (("front", 0.0), ("three-quarter", 45.0), ("side", 90.0)):
        a = math.radians(angle)
        cam.location = centre + Vector((math.sin(a) * distance, -math.cos(a) * distance, extent * 0.08))
        cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
        path = out_dir / "overlay-{0}.png".format(view)
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        views[view] = sha256(path)
    # hand close-up
    hand = Vector(joints["hand_l"])
    cam_data.lens = 135.0
    cam.location = hand + Vector((0.0, -0.45 * H, 0.05 * H))
    cam.rotation_euler = (hand - cam.location).to_track_quat("-Z", "Y").to_euler()
    path = out_dir / "overlay-hand-left.png"
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    views["hand-left"] = sha256(path)
    payload["overlay_sha256"] = views
    landmarks_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
