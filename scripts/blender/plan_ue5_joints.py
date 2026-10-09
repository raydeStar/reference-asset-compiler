"""Plan Manny joints for a T-posed character from DWPose keypoints and mesh slices.

blender -b <character.blend> --python plan_ue5_joints.py -- \
    --front-kp front_kp.json --side-kp left_kp.json --ortho ortho.json --out plan.json \
    [--template hm08.npz --head-npz head.npz] [--arm-ratio 0.42] [--sole 0.015] [--ignore OBJECT ...]

Every joint comes from a measurement, with the proportion rule written beside it:

* DWPose (open weights) on calibrated orthographic renders gives the joints'
  heights and spreads: knees, hips, shoulders, elbows, wrists, ears.
* Cross-section centroids of the mesh put each joint inside its limb. Legs are
  measured on the side whose slices agree best with the keypoints, then
  mirrored, so a sash or holster on one hip cannot drag a joint sideways.
* Fingers are traced in slices across the flat T-pose hand: each finger is a
  separate cross-section beyond the web; its knuckles follow phalanx ratios.
* With a MakeHuman-conformed head, its anatomical joint helpers place the neck
  and head pivots; otherwise the ears do.
* Arms longer than ``--arm-ratio`` of the height (shoulder to fingertip) are
  remapped shorter so hanging hands land mid-thigh, as Manny's do; the forearm
  and hand take most of the change. 0 disables the remap.

Objects named by --ignore are left out of every measurement (the height, the
ground, the choice of body): mesh hair is no part of the anatomy, stands above
the crown and can have more vertices than the body.

The output is the plan consumed by fit_ue5_manny_rig.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy
import numpy as np

MANNY_SPINE = {"pelvis": 95.9, "spine_01": 99.57, "spine_02": 106.24, "spine_03": 113.42, "spine_04": 121.93,
               "spine_05": 141.1, "neck_01": 152.8}
# Manny's forward bow of each spine joint off the pelvis-neck line (cm, +forward).
MANNY_BOW = {"spine_01": 0.02, "spine_02": 1.74, "spine_03": 3.16, "spine_04": 3.2, "spine_05": 1.31}
MANNY_HEIGHT_CM = 180.5


def mesh_world(ob):
    mw = np.array(ob.matrix_world)
    co = np.empty(len(ob.data.vertices) * 3)
    ob.data.vertices.foreach_get("co", co)
    return co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]


class Slicer:
    def __init__(self, ob):
        me = ob.data
        me.calc_loop_triangles()
        tri = np.empty(len(me.loop_triangles) * 3, int)
        me.loop_triangles.foreach_get("vertices", tri)
        self.T = tri.reshape(-1, 3)
        self.V = mesh_world(ob)
        self.TV = self.V[self.T]

    def segments(self, axis, value, box=None):
        d = self.TV[:, :, axis] - value
        s = np.sign(d)
        cut = ~((s > 0).all(1) | (s < 0).all(1))
        P, D = self.TV[cut], d[cut]
        out = []
        for i, j in ((0, 1), (1, 2), (2, 0)):
            cross = (D[:, i] > 0) != (D[:, j] > 0)
            t = D[cross, i] / (D[cross, i] - D[cross, j])
            out.append((np.nonzero(cross)[0], P[cross, i] + t[:, None] * (P[cross, j] - P[cross, i])))
        pts = {}
        for idx, p in out:
            for k, q in zip(idx, p):
                pts.setdefault(int(k), []).append(q)
        segs = np.array([v[:2] for v in pts.values() if len(v) >= 2])
        if len(segs) and box:
            mid = segs.mean(1)
            keep = np.ones(len(segs), bool)
            for ax, (lo, hi) in box.items():
                keep &= (mid[:, ax] >= lo) & (mid[:, ax] <= hi)
            segs = segs[keep]
        return segs

    def centroid(self, axis, value, box):
        S = self.segments(axis, value, box)
        if not len(S):
            return None
        L = np.linalg.norm(S[:, 0] - S[:, 1], axis=1)
        return (S.mean(1) * L[:, None]).sum(0) / max(L.sum(), 1e-9)

    def islands(self, axis, value, box, gap):
        """Connected cross-section loops (by endpoint proximity) as point arrays."""
        S = self.segments(axis, value, box)
        if not len(S):
            return []
        P = S.reshape(-1, 3)
        n = len(S)
        parent = list(range(n))

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        # Quantise endpoints to the gap and join segments sharing a cell.
        cells = {}
        for k, p in enumerate(P):
            key = tuple(np.floor(p / gap).astype(int))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        other = cells.get((key[0] + dx, key[1] + dy, key[2] + dz))
                        if other is not None:
                            ra, rb = find(k // 2), find(other // 2)
                            if ra != rb:
                                parent[ra] = rb
            cells.setdefault(key, k)
        groups = {}
        for s in range(n):
            groups.setdefault(find(s), []).append(s)
        return [S[g].reshape(-1, 3) for g in groups.values()]


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    p = argparse.ArgumentParser()
    p.add_argument("--front-kp", required=True)
    p.add_argument("--side-kp")
    p.add_argument("--ortho", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--body", default=None)
    p.add_argument("--head", default=None)
    p.add_argument("--template")
    p.add_argument("--head-npz")
    p.add_argument("--arm-ratio", type=float, default=0.42)
    p.add_argument("--sole", type=float, default=0.015)
    p.add_argument("--ignore", nargs="*", default=[], help="objects left out of the measurements (mesh hair)")
    a = p.parse_args(argv)
    missing = [name for name in a.ignore if name not in bpy.data.objects]
    if missing:
        raise RuntimeError(f"--ignore names no object in the blend: {missing}")
    meshes = sorted([o for o in bpy.data.objects if o.type == "MESH" and o.name not in a.ignore],
                    key=lambda o: -len(o.data.vertices))
    body = bpy.data.objects[a.body] if a.body else meshes[0]
    head = bpy.data.objects[a.head] if a.head else next((o for o in meshes if "head" in o.name.lower()), None)
    ortho = json.loads(Path(a.ortho).read_text())
    c = np.array(ortho["center"])
    px = ortho["ortho_scale"] / ortho["res"]
    R = ortho["res"]
    kp = json.loads(Path(a.front_kp).read_text())["body"]
    side = json.loads(Path(a.side_kp).read_text())["body"] if a.side_kp else None

    def front(name):  # world (x, z)
        u, v, _ = kp[name]
        return np.array([c[0] + (u - R / 2) * px, c[2] + (R / 2 - v) * px])

    def side_y(name):
        u, v, _ = side[name]
        return c[1] + (u - R / 2) * px

    allv = np.concatenate([mesh_world(o) for o in meshes])
    H = float(allv[:, 2].max() - allv[:, 2].min())
    ground = float(allv[:, 2].min())
    sl = Slicer(body)
    notes = {"height_m": H}
    J = {}

    # --- legs ------------------------------------------------------------
    knee_z = float(np.mean([front("l_knee")[1], front("r_knee")[1]]))
    hip_kp_z = float(np.mean([front("l_hip")[1], front("r_hip")[1]]))
    # Crotch from the front silhouette: scanning up the midline column from the
    # ground, the first covered pixel. Ignored when a coat hides it.
    crotch = None
    front_png = Path(a.ortho).with_name("front.png")
    if front_png.exists():
        img = bpy.data.images.load(str(front_png))
        w, h = img.size
        pix = np.array(img.pixels[:]).reshape(h, w, 4)[::-1, :, :3]  # row 0 = top
        bg = pix[2, 2]
        col = int(round(R / 2 + (0.0 - c[0]) / px))
        mask = (np.abs(pix[:, col - 2:col + 3] - bg).sum(2) > 0.08).any(1)
        ground_row = int(round(R / 2 - (ground - c[2]) / px))
        rows = [r for r in range(min(ground_row, h - 1), 0, -1) if mask[r]]
        if rows:
            z = c[2] + (R / 2 - rows[0]) * px
            if hip_kp_z - 0.12 * H < z < hip_kp_z - 0.02 * H:
                crotch = float(z)
    # Median of three estimates: the hip keypoint, the knee plus MakeHuman's
    # thigh (0.249 H) and the crotch plus 0.05 H. Loose trousers drop the crotch
    # and long coats hide it; neither moves the median far.
    estimates = [hip_kp_z, knee_z + 0.249 * H] + ([crotch + 0.05 * H] if crotch else [])
    hip_z = float(np.median(estimates))
    ankle_z = ground + 0.0457 * H + a.sole
    best = None
    for s, sign in (("r", -1.0), ("l", 1.0)):
        cen = sl.centroid(2, knee_z, {0: (sign * 0.01, sign * 0.4)} if sign > 0 else {0: (-0.4, -0.01)})
        err = abs(abs(cen[0]) - abs(front(f"{s}_knee")[0]))
        if best is None or err < best[0]:
            best = (err, s, sign)
    _, leg_side, sign = best
    lbox = {0: (0.01, 0.4)} if sign > 0 else {0: (-0.4, -0.01)}
    knee = sl.centroid(2, knee_z, lbox)
    shaft = sl.centroid(2, ground + 0.085 * H, lbox)
    upper = sl.centroid(2, hip_z - 0.06 * H, lbox)
    hip_x = 0.9 * float(np.mean([abs(front("l_hip")[0]), abs(front("r_hip")[0])]))
    low = allv[(allv[:, 2] < ground + 0.02) & (np.sign(allv[:, 0]) == sign)]
    toe_y, heel_y = float(low[:, 1].min()), float(low[:, 1].max())
    fore = low[low[:, 1] < toe_y + 0.35 * (heel_y - toe_y)]
    J["thigh_l"] = [hip_x, float(upper[1]), hip_z]
    J["calf_l"] = [abs(float(knee[0])), float(knee[1]), knee_z]
    J["foot_l"] = [abs(float(shaft[0])), float(shaft[1]), ankle_z]
    J["ball_l"] = [abs(float(fore[:, 0].mean())), toe_y + 0.30 * (heel_y - toe_y), ground + 0.012 * H]
    notes["legs"] = {"measured_side": leg_side, "crotch_z": crotch, "hip_keypoint_z": hip_kp_z}

    # --- head and neck ---------------------------------------------------
    shoulder_top = float(np.mean([front("l_shoulder")[1], front("r_shoulder")[1]]))
    if a.template and a.head_npz and head is not None:
        tmpl = np.load(a.template)
        hn = np.load(a.head_npz)
        mw = head.matrix_world
        sc, loc = np.array(mw.to_scale()), np.array(mw.translation)
        helper = lambda n: hn["verts"][tmpl["vg__" + n]].mean(0) * sc + loc  # noqa: E731
        neck, skull = helper("joint-neck"), helper("joint-head")
        notes["head_source"] = "MakeHuman joint helpers"
    else:
        ear_z = float(np.mean([front("l_ear")[1], front("r_ear")[1]]))
        ear_y = float(np.mean([side_y("l_ear"), side_y("r_ear")])) if side else 0.0
        skull = np.array([0.0, ear_y + 0.008 * H, ear_z - 0.011 * H])
        nz = shoulder_top + 0.0525 * H
        cen = sl.centroid(2, nz, {0: (-0.08, 0.08)})
        neck = np.array([0.0, float(cen[1]) if cen is not None else skull[1], nz])
        notes["head_source"] = "DWPose ears"
    J["neck_01"] = [0.0, float(neck[1]), float(neck[2])]
    J["head"] = [0.0, float(skull[1]), float(skull[2])]
    J["neck_02"] = list((np.array(J["neck_01"]) + np.array(J["head"])) / 2)

    # --- spine: Manny's heights and bow between pelvis and neck -----------
    pelvis_z = hip_z + 0.0133 * H
    pc = sl.centroid(2, pelvis_z, {0: (-0.2, 0.2)})
    pelvis_y = float(np.mean([J["thigh_l"][1], pc[1]]))
    J["pelvis"] = [0.0, pelvis_y, pelvis_z]
    span = J["neck_01"][2] - pelvis_z
    for name in ("spine_01", "spine_02", "spine_03", "spine_04", "spine_05"):
        t = (MANNY_SPINE[name] - MANNY_SPINE["pelvis"]) / (MANNY_SPINE["neck_01"] - MANNY_SPINE["pelvis"])
        y = pelvis_y + t * (J["neck_01"][1] - pelvis_y) - MANNY_BOW[name] * span / (MANNY_SPINE["neck_01"] - MANNY_SPINE["pelvis"])
        J[name] = [0.0, float(y), float(pelvis_z + t * span)]

    # --- arms ------------------------------------------------------------
    sh_x = 0.965 * float(np.mean([abs(front("l_shoulder")[0]), abs(front("r_shoulder")[0])]))
    el_x = float(np.mean([abs(front("l_elbow")[0]), abs(front("r_elbow")[0])]))
    wr_kp = float(np.mean([abs(front("l_wrist")[0]), abs(front("r_wrist")[0])]))
    arm_z = float(np.mean([front("l_elbow")[1], front("r_elbow")[1]]))
    abox = {2: (arm_z - 0.12 * H, arm_z + 0.12 * H)}

    def arm_c(x):
        cs = [sl.centroid(0, s * x, abox) for s in (1.0, -1.0)]
        cs = [v for v in cs if v is not None]
        return np.mean(cs, 0)

    # Palm start: the first slice beyond the wrist keypoint that widens by 20 %.
    widths = []
    xs = np.arange(el_x + 0.05, wr_kp + 0.12, 0.005)
    for x in xs:
        S = sl.segments(0, x, abox)
        widths.append(float(np.ptp(S.reshape(-1, 3)[:, 1])) if len(S) else 0.0)
    widths = np.array(widths)
    narrow = int(np.argmin(np.where(xs < wr_kp + 0.03, widths, np.inf)))
    palm = next((float(xs[i]) for i in range(narrow, len(xs)) if widths[i] > 1.2 * widths[narrow]), wr_kp)
    wr_x = float(np.mean([wr_kp, palm]))
    tip_x = float(np.abs(allv[:, 0]).max())
    shoulder = arm_c(sh_x + 0.08)
    J["clavicle_l"] = [0.015 * H / 1.77, J["spine_05"][1] + 0.022 * H / 1.77, float(shoulder[2]) + 0.042 * H / 1.77]
    J["upperarm_l"] = [sh_x, float(shoulder[1]), float(shoulder[2])]
    e = arm_c(el_x)
    J["lowerarm_l"] = [el_x, float(e[1]), float(e[2])]
    w = arm_c(wr_x - 0.02)
    J["hand_l"] = [wr_x, float(w[1]), float(w[2])]
    notes["arms"] = {"wrist_keypoint": wr_kp, "palm_start": palm, "fingertip": tip_x,
                     "shoulder_to_tip_ratio": (tip_x - sh_x) / H}

    # --- fingers: slices across the flat hand ------------------------------
    try:
        J.update(trace_fingers(sl, wr_x, tip_x, J["hand_l"], H))
        notes["fingers"] = "traced from x-slices of the hand"
    except RuntimeError as error:
        # Fused or mitten-like scanned fingers: place the knuckles by hand proportions instead, so the rig
        # stays complete (the hand then bends as one piece). Recorded, for review.
        J.update(proportional_fingers(wr_x, tip_x, J["hand_l"]))
        notes["fingers"] = f"proportional fallback ({error})"

    # --- proportion remap ------------------------------------------------
    plan = {"schema": "rac.ue5-joint-plan.v1", "units": "Blender metres; facing -Y; character left = +X",
            "body_object": body.name, "head_object": head.name if head else None, "ignored_objects": list(a.ignore),
            "joints": {k: [round(float(x), 5) for x in v] for k, v in J.items()}, "derivation": notes}
    ratio = (tip_x - sh_x) / H
    if a.arm_ratio > 0 and ratio > a.arm_ratio + 0.015:
        target = a.arm_ratio * H
        cut = (tip_x - sh_x) - target
        upper_len, fore_len, hand_len = el_x - sh_x, wr_x - el_x, tip_x - wr_x
        # Give each segment a share that brings it toward Manny's 0.38/0.37/0.25 split.
        want = np.array([0.38, 0.37, 0.25]) * target
        have = np.array([upper_len, fore_len, hand_len])
        excess = np.maximum(have - want, 0)
        share = excess / excess.sum() * cut if excess.sum() > 0 else have / have.sum() * cut
        new = have - share
        start = max(sh_x + 0.06, 0.1525 * H)  # leave the shoulder and jacket body untouched
        src = [start, el_x, wr_x, tip_x]
        dst = [start, sh_x + new[0], sh_x + new[0] + new[1], sh_x + new.sum()]
        plan["arm_remap"] = {"source": [round(v, 4) for v in src], "target": [round(float(v), 4) for v in dst],
                             "blend": 0.015 * H / 1.77}
        plan["arm_zmin"] = float(arm_z - 0.2 * H)
        notes["arm_remap"] = {"from_ratio": ratio, "to_ratio": a.arm_ratio}
    Path(a.out).write_text(json.dumps(plan, indent=1))
    print("PLAN DONE", a.out, json.dumps(notes, indent=1))


def proportional_fingers(wr_x, tip_x, hand, spread=(-0.024, -0.008, 0.008, 0.022), length=(0.95, 1.0, 0.95, 0.8)):
    """Knuckles of the left hand from proportions alone (palm 48% of the wrist-to-tip length; fingers fanned
    front (-Y) to back (+Y) across the palm; thumb forward), for hands whose fingers do not separate in slices."""
    hand = np.array(hand, float)
    span = tip_x - wr_x
    mcp_x = wr_x + 0.48 * span
    out = {}
    for n, dy, k in zip(["index", "middle", "ring", "pinky"], spread, length):
        finger = (tip_x - mcp_x) * k
        def at(x, dy=dy):
            return [float(x), float(hand[1] + dy), float(hand[2])]
        out[f"{n}_01_l"] = at(mcp_x)
        out[f"{n}_02_l"] = at(mcp_x + 0.45 * finger)
        out[f"{n}_03_l"] = at(mcp_x + 0.73 * finger)
        out[f"{n}_metacarpal_l"] = list(hand + 0.15 * (np.array(out[f"{n}_01_l"]) - hand))
    out["thumb_01_l"] = [float(wr_x + 0.08 * span), float(hand[1] - 0.02), float(hand[2] - 0.005)]
    out["thumb_02_l"] = [float(wr_x + 0.25 * span), float(hand[1] - 0.034), float(hand[2] - 0.01)]
    out["thumb_03_l"] = [float(wr_x + 0.40 * span), float(hand[1] - 0.044), float(hand[2] - 0.012)]
    return out


def trace_fingers(sl, wr_x, tip_x, hand, H):
    """Knuckles of the left hand (mirrored later) from x-slices of the T-pose hand."""
    box = {2: (hand[2] - 0.08, hand[2] + 0.08)}
    gap = 0.0025
    tracks = []
    for x in np.arange(wr_x + 0.02, tip_x, 0.003):
        isl = [i for i in sl.islands(0, x, box, gap) if len(i) >= 6]
        cents = [(float(i[:, 1].mean()), float(i[:, 2].mean()), float(np.ptp(i[:, 1]))) for i in isl]
        tracks.append((float(x), sorted(cents)))
    names = ["index", "middle", "ring", "pinky"]  # front (-Y) to back (+Y) for a palm-down left hand
    lines = None
    thumb_pts = []
    thumb_open = True
    out = {}
    for x, cs in tracks:
        # The thumb is the island well forward (-Y) of the palm or of the index finger.
        # The thumb parts from the palm first (palm + thumb = 2 islands), then is
        # followed by continuity as the most forward (-Y) island until it ends.
        if thumb_open and cs:
            last = thumb_pts[-1][1][0] if thumb_pts else None
            if last is None and len(cs) == 2 and cs[1][0] - cs[0][0] > 0.015:
                thumb_pts.append((x, cs[0]))
                cs = cs[1:]
            elif last is not None:
                if abs(cs[0][0] - last) < 0.012 and len(cs) >= 2:
                    thumb_pts.append((x, cs[0]))
                    cs = cs[1:]
                else:
                    thumb_open = False
        if lines is None:
            if len(cs) >= 4:
                lines = {n: [(x, cc[0], cc[1])] for n, cc in zip(names, cs[-4:])}
            continue
        # Follow each finger by continuity, so a short pinky does not end the others.
        for n in names:
            lx, ly, lz = lines[n][-1]
            if x - lx > 0.012 or not cs:
                continue
            best = min(cs, key=lambda cc: abs(cc[0] - ly))
            if abs(best[0] - ly) < 0.01:
                lines[n].append((x, best[0], best[1]))
    if lines is None:
        raise RuntimeError("Could not separate four fingers in the hand slices")
    for n in names:
        L = np.array(lines[n])
        if len(L) < 3:
            raise RuntimeError(f"Finger {n} not traced")
        d = np.polyfit(L[:, 0], L[:, 1:], 1)
        total = (L[-1, 0] + 0.004 - L[0, 0]) / 0.82
        mcp_x = L[0, 0] - 0.18 * total

        def at(x):
            return [float(x), float(np.polyval(d[:, 0], x)), float(np.polyval(d[:, 1], x))]
        out[f"{n}_01_l"] = at(mcp_x)
        out[f"{n}_02_l"] = at(mcp_x + 0.45 * total)
        out[f"{n}_03_l"] = at(mcp_x + 0.73 * total)
        out[f"{n}_metacarpal_l"] = list(np.array(hand) + 0.15 * (np.array(out[f"{n}_01_l"]) - np.array(hand)))
    if thumb_pts:
        T = np.array([[x, cc[0], cc[1]] for x, cc in thumb_pts])
        mcp, tip = T[0], T[-1] + np.r_[0.004, 0, 0]
        out["thumb_02_l"] = list(mcp)
        out["thumb_03_l"] = list(mcp + 0.55 * (tip - mcp))
        out["thumb_01_l"] = list(np.array(hand) + 0.43 * (mcp - np.array(hand)))  # Manny's CMC fraction
    return out


if __name__ == "__main__":
    main()
