# SPDX-License-Identifier: MIT
"""Procedural poses for the UE5 Manny skeleton: FK from the reference pose, two-bone IK, grips.

Space: UE component space of SK_Mannequin, centimetres. The mannequin faces +Y, +X is its left, +Z is up.
The reference pose comes from scripts/ue5/dump_manny_reference.py (manny_refpose.json: component-space
position and xyzw quaternion per bone; Epic data, kept out of Git).

A pose never changes a bone length. Each bone's component rotation is G = D @ Gref, where D is a delta:
  * by default a bone inherits its parent's delta (rigid follow);
  * `rel[bone] = R`   rotates it, in the reference frame, on top of its parent's delta (D = Dparent @ R);
  * `world[bone] = D` sets the delta outright (IK results, aimed hands and feet);
  * `local[bone] = L` sets the rotation relative to the posed parent (G = Gparent @ L), used for finger curls.
A child sits at its parent's position plus the parent's delta applied to its reference offset; only the
pelvis can move (`pelvis_pos`). The ik_* bones are copied from the hands and feet they shadow, as in Epic's
clips, so the template's foot IK sees the posed feet.

Frames are written as {"pos", "quat" (component), "lquat" (parent-local)} per bone: the format
scripts/blender/pose_ue5_anim_test.py renders and the UE writer keys.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

LEFT = np.array([1.0, 0.0, 0.0])
FWD = np.array([0.0, 1.0, 0.0])
UP = np.array([0.0, 0.0, 1.0])
SHADOWS = {"ik_foot_l": "foot_l", "ik_foot_r": "foot_r", "ik_hand_gun": "hand_r",
           "ik_hand_l": "hand_l", "ik_hand_r": "hand_r"}
FINGERS = ("index", "middle", "ring", "pinky")


# ------------------------------------------------------------------------------------------- maths
def unit(v):
    v = np.asarray(v, float)
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else v


def qmat(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def matq(R):
    """Rotation matrix -> xyzw quaternion (w >= 0)."""
    t = np.trace(R)
    if t > 0:
        s = math.sqrt(t + 1.0) * 2
        q = [(R[2, 1] - R[1, 2]) / s, (R[0, 2] - R[2, 0]) / s, (R[1, 0] - R[0, 1]) / s, 0.25 * s]
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        q = [0.25 * s, (R[0, 1] + R[1, 0]) / s, (R[0, 2] + R[2, 0]) / s, (R[2, 1] - R[1, 2]) / s]
    elif R[1, 1] > R[2, 2]:
        s = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        q = [(R[0, 1] + R[1, 0]) / s, 0.25 * s, (R[1, 2] + R[2, 1]) / s, (R[0, 2] - R[2, 0]) / s]
    else:
        s = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        q = [(R[0, 2] + R[2, 0]) / s, (R[1, 2] + R[2, 1]) / s, 0.25 * s, (R[1, 0] - R[0, 1]) / s]
    q = np.array(q)
    q /= np.linalg.norm(q)
    return q if q[3] >= 0 else -q


def rot(axis, deg):
    """Rotation of `deg` degrees about `axis` (Rodrigues)."""
    a = unit(axis)
    t = math.radians(deg)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + math.sin(t) * K + (1 - math.cos(t)) * (K @ K)


def euler(pitch=0.0, roll=0.0, yaw=0.0):
    """Body-frame turn in mannequin terms: pitch > 0 tips the top forward (+Y), roll > 0 tips it to the
    character's left (+X), yaw > 0 turns the front to the left. Applied yaw, then pitch, then roll."""
    return rot(FWD, roll) @ rot(LEFT, -pitch) @ rot(UP, -yaw)


def frame(a, b):
    """Orthonormal frame whose first axis is a and whose second lies in the (a, b) plane."""
    a = unit(a)
    b = unit(np.asarray(b, float) - a * np.dot(a, b))
    return np.column_stack([a, b, np.cross(a, b)])


def align(a1, b1, a2, b2):
    """The rotation taking direction a1 to a2 while carrying b1's side of it onto b2's."""
    return frame(a2, b2) @ frame(a1, b1).T


def between(a, b):
    """Shortest rotation taking direction a to direction b."""
    a, b = unit(a), unit(b)
    c = np.cross(a, b)
    s = np.linalg.norm(c)
    d = float(np.dot(a, b))
    if s < 1e-9:
        if d > 0:
            return np.eye(3)
        perp = unit(np.cross(a, LEFT if abs(a[0]) < 0.9 else FWD))
        return rot(perp, 180.0)
    return rot(c, math.degrees(math.atan2(s, d)))


def slerp(R1, R2, t):
    q1, q2 = matq(R1), matq(R2)
    if np.dot(q1, q2) < 0:
        q2 = -q2
    d = float(np.clip(np.dot(q1, q2), -1, 1))
    if d > 0.9995:
        q = unit(q1 + t * (q2 - q1))
    else:
        th = math.acos(d)
        q = (math.sin((1 - t) * th) * q1 + math.sin(t * th) * q2) / math.sin(th)
    return qmat(q)


def smooth(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return np.asarray(a, float) + (np.asarray(b, float) - np.asarray(a, float)) * t


# ------------------------------------------------------------------------------------------- skeleton
class Manny:
    def __init__(self, refpose_path):
        data = json.loads(Path(refpose_path).read_text())
        bones = data["bones"]
        self.parent = {b["name"]: b["parent"] for b in bones}
        self.G = {b["name"]: qmat(b["quat"]) for b in bones}
        self.P = {b["name"]: np.array(b["pos"], float) for b in bones}
        self.order = []
        for n in self.parent:
            self._visit(n)
        self.L = {n: (self.G[p].T @ self.G[n] if p else self.G[n]) for n, p in self.parent.items()}
        self.palm = {s: self._palm_normal(s) for s in "lr"}

    def _visit(self, n):
        if n in self.order:
            return
        if self.parent[n]:
            self._visit(self.parent[n])
        self.order.append(n)

    def seg(self, a, b):
        return float(np.linalg.norm(self.P[b] - self.P[a]))

    def _palm_normal(self, side):
        """Out of the palm: the side curled fingertips travel toward (measured, so mirrored axes don't matter)."""
        pose = Pose(self)
        pose.grip(side, 60.0, thumb=0.0)
        G, P = pose.fk()
        hand, tip = f"hand_{side}", f"middle_03_{side}"
        fwd = unit(self.P[f"middle_01_{side}"] - self.P[hand])
        moved = P[tip] - self.P[tip]
        return unit(moved - fwd * np.dot(moved, fwd))

    def hand_axes(self, side):
        """(finger direction, palm normal) of the reference hand."""
        return unit(self.P[f"middle_01_{side}"] - self.P[f"hand_{side}"]), self.palm[side]

    def foot_axes(self, side):
        """(toe direction, sole-up) of the reference foot."""
        toe = unit(self.P[f"ball_{side}"] - self.P[f"foot_{side}"])
        return toe, unit(UP - toe * np.dot(UP, toe))


class Pose:
    def __init__(self, manny: Manny):
        self.m = manny
        self.rel, self.world, self.local = {}, {}, {}
        self.pelvis_pos = manny.P["pelvis"].copy()

    # ---- forward kinematics
    def fk(self):
        m = self.m
        G, P, D = {}, {}, {}
        for n in m.order:
            p = m.parent[n]
            if p is None:
                G[n], P[n], D[n] = m.G[n].copy(), m.P[n].copy(), np.eye(3)
                continue
            if n in self.local:
                G[n] = G[p] @ self.local[n]
                D[n] = G[n] @ m.G[n].T
            else:
                D[n] = self.world[n] if n in self.world else D[p] @ self.rel.get(n, np.eye(3))
                G[n] = D[n] @ m.G[n]
            P[n] = self.pelvis_pos.copy() if n == "pelvis" else P[p] + D[p] @ (m.P[n] - m.P[p])
        for n, src in SHADOWS.items():
            if n in G:
                G[n], P[n] = G[src].copy(), P[src].copy()
        return G, P

    def delta(self, bone):
        G, _ = self.fk()
        return G[bone] @ self.m.G[bone].T

    # ---- body
    def spine(self, pitch=0.0, roll=0.0, yaw=0.0, weights=(0.15, 0.2, 0.2, 0.25, 0.2)):
        """Bend the five spine bones by a total pitch/roll/yaw, distributed by `weights`."""
        for i, w in enumerate(weights):
            self.rel[f"spine_0{i + 1}"] = euler(pitch * w, roll * w, yaw * w)

    def head(self, pitch=0.0, roll=0.0, yaw=0.0):
        """Neck and head (pitch > 0 looks down)."""
        self.rel["neck_01"] = euler(pitch * 0.3, roll * 0.3, yaw * 0.3)
        self.rel["neck_02"] = euler(pitch * 0.3, roll * 0.3, yaw * 0.3)
        self.rel["head"] = euler(pitch * 0.4, roll * 0.4, yaw * 0.4)

    def shrug(self, side, up_deg=0.0, fwd_deg=0.0):
        """Raise (up_deg) and bring forward (fwd_deg) a clavicle's outer end."""
        s = 1.0 if side == "l" else -1.0
        self.rel[f"clavicle_{side}"] = rot(FWD, -s * up_deg) @ rot(UP, s * fwd_deg)

    # ---- limbs
    def _two_bone(self, root, mid, end, target, pole):
        m = self.m
        G, P = self.fk()
        S = P[root]
        a, b = m.seg(root, mid), m.seg(mid, end)
        d = np.asarray(target, float) - S
        dist = float(np.clip(np.linalg.norm(d), abs(a - b) + 1e-3, a + b - 1e-3))
        dn = unit(d)
        T = S + dn * dist
        cos_a = (a * a + dist * dist - b * b) / (2 * a * dist)
        sin_a = math.sqrt(max(0.0, 1 - cos_a * cos_a))
        pp = unit(np.asarray(pole, float) - dn * np.dot(pole, dn))
        E = S + dn * (a * cos_a) + pp * (a * sin_a)
        u1, f1 = unit(m.P[mid] - m.P[root]), unit(m.P[end] - m.P[mid])
        u2, f2 = unit(E - S), unit(T - E)
        n1 = unit(np.cross(u1, f1))
        n2 = np.cross(u2, f2)
        n2 = unit(n2) if np.linalg.norm(n2) > 1e-6 else unit(np.cross(dn, pp))
        self.world[root] = align(u1, n1, u2, n2)
        self.world[mid] = align(f1, n1, f2, n2)
        return float(np.linalg.norm(np.asarray(target, float) - S)) - (a + b)   # > 0: target out of reach

    def arm(self, side, wrist, pole, fingers=None, palm=None, twist=True):
        """Put the wrist at `wrist` (elbow toward `pole`); aim the fingers/palm if given."""
        short = self._two_bone(f"upperarm_{side}", f"lowerarm_{side}", f"hand_{side}", wrist, pole)
        hand = f"hand_{side}"
        if fingers is not None:
            f0, p0 = self.m.hand_axes(side)
            self.world[hand] = align(f0, p0, fingers, palm if palm is not None else p0)
        else:
            self.world.pop(hand, None)
        if twist and fingers is not None:
            self._forearm_twist(side)
        return short

    def _forearm_twist(self, side):
        """Share the wrist's roll with the forearm twist bones (01 sits near the hand), so the hand can turn
        without candy-wrapping the wrist."""
        G, _ = self.fk()
        lo, hand = f"lowerarm_{side}", f"hand_{side}"
        axis = unit(self.m.P[hand] - self.m.P[lo])
        Dlo = G[lo] @ self.m.G[lo].T
        q = matq(Dlo.T @ (G[hand] @ self.m.G[hand].T))   # the hand's turn in the forearm's reference frame
        ang = 2 * math.degrees(math.atan2(float(np.dot(q[:3], axis)), q[3]))
        for bone, k in ((f"lowerarm_twist_01_{side}", 0.6), (f"lowerarm_twist_02_{side}", 0.3)):
            self.world[bone] = Dlo @ rot(axis, ang * k)

    def leg(self, side, ankle, pole, toe=None, sole=None):
        short = self._two_bone(f"thigh_{side}", f"calf_{side}", f"foot_{side}", ankle, pole)
        foot = f"foot_{side}"
        if toe is not None:
            t0, s0 = self.m.foot_axes(side)
            self.world[foot] = align(t0, s0, toe, sole if sole is not None else UP)
        else:
            self.world.pop(foot, None)
        return short

    def grip(self, side, curl, thumb=None, spread=0.0):
        """Curl the fingers (degrees per joint; the first knuckle takes 70%) and the thumb."""
        m = self.m
        thumb = curl * 0.5 if thumb is None else thumb
        for f in FINGERS:
            for j, k in (("01", 0.7), ("02", 1.0), ("03", 0.8)):
                n = f"{f}_{j}_{side}"
                self.local[n] = m.L[n] @ rot([0, 0, -1], curl * k)
        for j, k in (("02", 0.8), ("03", 1.0)):
            n = f"thumb_{j}_{side}"
            self.local[n] = m.L[n] @ rot([0, 0, -1], thumb * k)

    # ---- output
    def frame_dict(self):
        G, P = self.fk()
        out = {}
        for n in self.m.order:
            p = self.m.parent[n]
            lq = G[p].T @ G[n] if p else G[n]
            out[n] = {"pos": [round(float(v), 4) for v in P[n]], "quat": [round(float(v), 6) for v in matq(G[n])],
                      "lquat": [round(float(v), 6) for v in matq(lq)]}
        return out


def with_locals(frame, parent):
    """Add parent-local rotations ("lquat") to a frame that has component rotations."""
    for n, v in frame.items():
        p = parent[n]
        R = qmat(v["quat"])
        v["lquat"] = [round(float(x), 6) for x in matq(qmat(frame[p]["quat"]).T @ R if p else R)]
    return frame


def blend_frames(a, b, t, parent):
    """Blend two frames: component rotations slerped, positions lerped (only the pelvis position is
    authored; the others follow from rotations and bone lengths downstream)."""
    out = {}
    for n in a:
        out[n] = {"pos": lerp(a[n]["pos"], b[n]["pos"], t).round(4).tolist(),
                  "quat": matq(slerp(qmat(a[n]["quat"]), qmat(b[n]["quat"]), t)).round(6).tolist()}
    return with_locals(out, parent)
