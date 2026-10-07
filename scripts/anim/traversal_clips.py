# SPDX-License-Identifier: MIT
"""Author climbing, ledge-hang, mantle, climb-leap and glide clips on the UE5 Manny skeleton.

  python scripts/anim/traversal_clips.py <manny_refpose.json> <out_dir> [--idle-pose manny_anim_poses.json]

Writes <out_dir>/traversal_clips.json (every frame of every clip, Manny component space) and
<out_dir>/preview_poses.json (a few frames per clip, for scripts/blender/pose_ue5_anim_test.py).
The UE side keys them into AnimSequences (TheAetherWars Tools/TraversalAnims.py); any Manny-conformant
character then gets them through its IK retargeter.

Clips are in place (no root motion): the game moves the capsule. Distances match TheAetherWars'
UClimbingComponent: on a wall the capsule centre sits 62 cm off the wall (radius 42 + IdealWallOffset 20);
hanging, the lip is 207 cm above the feet and 82 cm out. Pass --wall/--lip-y/--lip-z for other setups.
Climb cycles cover 90 cm per second up/down and 70 cm per second sideways at play rate 1, so the game
sets play rate = climb speed / that.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

import manny_poser as mp
from manny_poser import UP, Pose, euler, lerp, smooth, unit

FPS = 30
CLIMB_STRIDE = 45.0      # cm a planted hold travels per half cycle (90 cm per 1 s cycle)
SIDE_STRIDE = 35.0       # sideways: 70 cm per 1 s cycle
HANG_STRIDE = 25.0       # ledge shimmy: 50 cm per 1 s cycle
SIDES = {"l": 1.0, "r": -1.0}


class Clips:
    def __init__(self, manny, wall=62.0, lip_y=82.0, lip_z=207.0, idle=None):
        self.m, self.W, self.LY, self.LZ = manny, wall, lip_y, lip_z
        self.idle = idle

    # ------------------------------------------------------------------ shared poses
    def on_wall(self, hands, feet, pelvis=(0.0, 0.0, 0.0), lean=(0.0, 0.0, 0.0), look=(0.0, 0.0), breathe=0.0):
        """Climbing on a vertical wall in front (+Y = self.W).
        hands/feet: side -> (x, z, off_wall_cm, grip 0..1). lean = spine (pitch, roll, yaw)."""
        m, W = self.m, self.W
        p = Pose(m)
        p.pelvis_pos = np.array([pelvis[0], W - 25.0 + pelvis[1], 86.0 + pelvis[2]])
        p.rel["pelvis"] = euler(pitch=4.0, roll=-lean[1] * 0.3, yaw=-lean[2] * 0.4)
        p.spine(pitch=9.0 + lean[0] + breathe, roll=lean[1], yaw=lean[2])
        p.head(pitch=-16.0 - look[0], yaw=look[1])
        for s, (x, z, off, grip) in hands.items():
            p.shrug(s, up_deg=float(np.clip((z - 150.0) * 0.35, 0.0, 16.0)), fwd_deg=6.0)
        for s, (x, z, off, grip) in hands.items():
            o = SIDES[s]
            fingers = unit((0.18 * o, -0.05 * off / 10.0, 1.0))
            palm = unit((0.0, 1.0, -0.25 * off / 10.0))
            p.arm(s, (x, W - 5.0 - off, z), pole=(o * 0.9, -0.5, -1.0), fingers=fingers, palm=palm)
            p.grip(s, 18.0 + 42.0 * grip, thumb=10.0 + 25.0 * grip)
        for s, (x, z, off, _grip) in feet.items():
            o = SIDES[s]
            p.leg(s, (x, W - 17.0 - off, z), pole=(o * 0.7, 0.55, 0.1), toe=unit((0.12 * o, 1.0, -0.35)),
                  sole=unit((0.0, 0.35, 1.0)))
        return p

    def hanging(self, hands, feet, pelvis=(0.0, 0.0, 0.0), lean=(0.0, 0.0, 0.0), look=(0.0, 0.0)):
        """Hanging from a lip at (LY, LZ). hands: side -> (x along the lip, lift_cm, grip 0..1);
        feet: side -> (x, z, off_wall_cm)."""
        m, LY, LZ = self.m, self.LY, self.LZ
        p = Pose(m)
        p.pelvis_pos = np.array([pelvis[0], LY - 27.0 + pelvis[1], LZ - 98.0 + pelvis[2]])
        p.rel["pelvis"] = euler(pitch=-3.0, roll=-lean[1] * 0.4)
        p.spine(pitch=6.0 + lean[0], roll=lean[1], yaw=lean[2])
        p.head(pitch=-22.0 - look[0], yaw=look[1])
        for s in hands:
            p.shrug(s, up_deg=14.0, fwd_deg=8.0)
        for s, (x, lift, grip) in hands.items():
            o = SIDES[s]
            p.arm(s, (x, LY - 6.0, LZ + 3.0 + lift), pole=(o * 0.8, -0.6, -0.4),
                  fingers=unit((0.1 * o, 1.0, -0.15 - 0.03 * lift)), palm=(0.0, 0.0, -1.0))
            p.grip(s, 30.0 + 45.0 * grip, thumb=20.0)
        for s, (x, z, off) in feet.items():
            o = SIDES[s]
            p.leg(s, (x, LY - 17.0 - off, z), pole=(o * 0.4, 1.0, 0.1), toe=unit((0.1 * o, 1.0, -0.6)),
                  sole=unit((0.0, 0.6, 1.0)))
        return p

    # ------------------------------------------------------------------ climbing
    def climb_idle(self, ph):
        w = 2 * math.pi * ph
        return self.on_wall(
            hands={"l": (21.0 + 0.8 * math.sin(w), 192.0, 0.0, 1.0), "r": (-23.0, 168.0 + 0.8 * math.cos(w), 0.0, 1.0)},
            feet={"l": (15.0, 44.0, 0.0, 1.0), "r": (-16.0, 22.0, 0.0, 1.0)},
            pelvis=(1.5 * math.sin(w), 0.0, 0.8 * math.sin(2 * w)), lean=(0.0, -2.0, -3.0),
            look=(4.0 * math.sin(w), 6.0), breathe=1.5 * math.sin(2 * w))

    def _cycle_limb(self, ph, lo, hi, off_max):
        """One limb over a cycle: reach lo->hi in the first half (arcing off the wall), then planted,
        travelling hi->lo with the body. Returns (value, off_wall, grip)."""
        if ph < 0.5:
            u = ph / 0.5
            return lerp(lo, hi, smooth(u)), off_max * math.sin(math.pi * u), 0.15 + 0.85 * smooth(2 * u - 1.0)
        u = (ph - 0.5) / 0.5
        return lerp(hi, lo, u), 0.0, 1.0

    def climb_up(self, ph):
        lo_h, hi_h = 152.0, 152.0 + CLIMB_STRIDE
        lo_f, hi_f = 6.0, 6.0 + CLIMB_STRIDE
        hl, ol, gl = self._cycle_limb(ph % 1.0, lo_h, hi_h, 11.0)
        hr, orr, gr = self._cycle_limb((ph + 0.5) % 1.0, lo_h, hi_h, 11.0)
        fr, ofr, _ = self._cycle_limb(ph % 1.0, lo_f, hi_f, 12.0)          # diagonal: right foot with left hand
        fl, ofl, _ = self._cycle_limb((ph + 0.5) % 1.0, lo_f, hi_f, 12.0)
        w = 2 * math.pi * ph
        return self.on_wall(
            hands={"l": (21.0, float(hl), ol, gl), "r": (-21.0, float(hr), orr, gr)},
            feet={"l": (15.0, float(fl), ofl, 1.0), "r": (-15.0, float(fr), ofr, 1.0)},
            pelvis=(2.5 * math.cos(w), 0.0, 2.0 * math.cos(2 * w)), lean=(0.0, 3.5 * math.sin(w), -4.0 * math.sin(w)),
            look=(4.0, 9.0 * math.sin(w)))

    def climb_side(self, ph, to_left):
        """Sideways: the leading hand and foot reach out, the trailing ones close in. to_left: move to +X."""
        d = 1.0 if to_left else -1.0
        lead, trail = ("l", "r") if to_left else ("r", "l")
        # Planted holds drift opposite to travel (-d), SIDE_STRIDE per half cycle.
        lh = self._cycle_limb(ph % 1.0, 8.0, 8.0 + SIDE_STRIDE, 9.0)              # lead hand: out
        th = self._cycle_limb((ph + 0.5) % 1.0, -32.0, -32.0 + SIDE_STRIDE, 9.0)  # trail hand: in to the body
        lf = self._cycle_limb((ph + 0.25) % 1.0, 4.0, 4.0 + SIDE_STRIDE, 10.0)
        tf = self._cycle_limb((ph + 0.75) % 1.0, -28.0, -28.0 + SIDE_STRIDE, 10.0)
        w = 2 * math.pi * ph
        hands = {lead: (d * float(lh[0]), 186.0 + 5.0 * math.sin(math.pi * lh[1] / 9.0), lh[1], lh[2]),
                 trail: (d * float(th[0]), 178.0, th[1], th[2])}
        feet = {lead: (d * float(lf[0]), 34.0 + 6.0 * math.sin(math.pi * lf[1] / 10.0), lf[1], 1.0),
                trail: (d * float(tf[0]), 26.0, tf[1], 1.0)}
        return self.on_wall(hands=hands, feet=feet, pelvis=(d * 3.0 * math.sin(w), 0.0, 1.5 * math.cos(2 * w)),
                            lean=(0.0, d * 4.0, 0.0), look=(2.0, d * 18.0))

    def climb_leap(self, t):
        """0.55 s: gather, spring up with both arms reaching, catch."""
        idle = dict(hands={"l": (21.0, 192.0, 0.0, 1.0), "r": (-23.0, 168.0, 0.0, 1.0)},
                    feet={"l": (15.0, 44.0, 0.0, 1.0), "r": (-16.0, 22.0, 0.0, 1.0)}, pelvis=(0.0, 0.0, 0.0))
        gather = dict(hands={"l": (20.0, 176.0, 0.0, 1.0), "r": (-20.0, 166.0, 0.0, 1.0)},
                      feet={"l": (15.0, 56.0, 0.0, 1.0), "r": (-15.0, 52.0, 0.0, 1.0)}, pelvis=(0.0, 4.0, -8.0))
        spring = dict(hands={"l": (24.0, 214.0, 14.0, 0.0), "r": (-24.0, 214.0, 14.0, 0.0)},
                      feet={"l": (12.0, 8.0, 6.0, 1.0), "r": (-12.0, 2.0, 10.0, 1.0)}, pelvis=(0.0, -4.0, 6.0))
        keys = [(0.0, idle), (0.1, gather), (0.28, spring), (0.55, idle)]
        for (t0, a), (t1, b) in zip(keys, keys[1:]):
            if t <= t1:
                u = smooth((t - t0) / (t1 - t0))
                break
        def mix(A, B):
            return {s: tuple(float(v) for v in lerp(A[s], B[s], u)) for s in A}
        look = 22.0 * math.sin(math.pi * min(1.0, t / 0.4))
        return self.on_wall(hands=mix(a["hands"], b["hands"]), feet=mix(a["feet"], b["feet"]),
                            pelvis=tuple(lerp(a["pelvis"], b["pelvis"], u)), look=(look, 0.0))

    # ------------------------------------------------------------------ ledge
    def hang_idle(self, ph):
        w = 2 * math.pi * ph
        return self.hanging(hands={"l": (21.0, 0.0, 1.0), "r": (-21.0, 0.0, 1.0)},
                            feet={"l": (13.0, 30.0 + 4.0 * math.sin(w), 0.0), "r": (-13.0, 22.0, 3.0)},
                            pelvis=(2.0 * math.sin(w), 0.0, 1.0 * math.sin(2 * w)), lean=(0.0, -1.5 * math.sin(w), 0.0),
                            look=(3.0 * math.sin(w), 0.0))

    def hang_side(self, ph, to_left):
        d = 1.0 if to_left else -1.0
        lead, trail = ("l", "r") if to_left else ("r", "l")
        lh = self._cycle_limb(ph % 1.0, 10.0, 10.0 + HANG_STRIDE, 6.0)
        th = self._cycle_limb((ph + 0.5) % 1.0, -30.0, -30.0 + HANG_STRIDE, 6.0)
        w = 2 * math.pi * ph
        hands = {lead: (d * float(lh[0]), lh[1], lh[2]), trail: (d * float(th[0]), th[1], th[2])}
        feet = {lead: (d * (14.0 + 4.0 * math.sin(w)), 28.0, 0.0), trail: (d * (-12.0 + 4.0 * math.sin(w)), 24.0, 2.0)}
        return self.hanging(hands=hands, feet=feet, pelvis=(d * 3.0 * math.sin(w), 0.0, 1.0 * math.cos(2 * w)),
                            lean=(0.0, d * 3.0 * math.sin(w), 0.0), look=(0.0, d * 15.0))

    # ------------------------------------------------------------------ mantle
    def mantle_lip(self, t, forward=60.0, ease=0.65):
        """Where the lip is, in component space, while UClimbingComponent eases the capsule from the hang
        onto the ledge (alpha^ease)."""
        s = t ** ease
        return np.array([0.0, self.LY - (self.LY + forward) * s, self.LZ - self.LZ * s])

    def mantle(self, t):
        """0.5 s, synced to the capsule's eased rise: pull, press out, knee on, stand (blends into idle)."""
        m = self.m
        lip = self.mantle_lip(t)
        p = Pose(m)
        # Pelvis relative to the lip: hanging below -> chest at the lip -> above it on a knee -> standing.
        keys = [(0.0, (0.0, -27.0, -98.0), 0.0), (0.3, (0.0, -24.0, -55.0), 18.0),
                (0.55, (0.0, -5.0, -5.0), 30.0), (0.8, (0.0, 30.0, 70.0), 10.0), (1.0, (0.0, 60.0, 96.0), 0.0)]
        for (t0, a, ba), (t1, b, bb) in zip(keys, keys[1:]):
            if t <= t1:
                u = smooth((t - t0) / (t1 - t0))
                rel, bend = lerp(a, b, u), ba + (bb - ba) * u
                break
        p.pelvis_pos = lip + rel
        p.spine(pitch=8.0 + bend)
        p.head(pitch=-15.0 + bend * 0.6)
        press = smooth((t - 0.2) / 0.35)          # hands go from hanging to pressing down on top
        release = smooth((t - 0.6) / 0.25)        # then let go
        for s, o in SIDES.items():
            p.shrug(s, up_deg=14.0 * (1 - press), fwd_deg=6.0)
        G, P = p.fk()
        for s, o in SIDES.items():
            on_lip = lip + np.array([o * 22.0, -6.0 + 10.0 * press, 3.0])
            free = P[f"upperarm_{s}"] + np.array([o * 14.0, 6.0, -48.0])
            wrist = lerp(on_lip, free, release)
            fingers = unit(lerp((0.1 * o, 1.0, -0.15), (0.0, 0.2, -1.0), release))
            palm = unit(lerp((0.0, 0.0, -1.0), (-o, 0.0, 0.0), release))
            p.arm(s, wrist, pole=(o * 0.8, -0.8, 0.2 - 1.2 * press), fingers=fingers, palm=palm)
            p.grip(s, 70.0 * (1 - release) + 15.0, thumb=20.0)
        # Legs: dangle, then the left knee comes up onto the lip, then both feet under the body.
        knee_up = smooth((t - 0.35) / 0.3)
        stand = smooth((t - 0.75) / 0.25)
        G, P = p.fk()
        for s, o in SIDES.items():
            hang_foot = lip + np.array([o * 13.0, -17.0, -185.0])
            up_foot = lip + np.array([o * 12.0, 8.0 if s == "l" else -20.0, 8.0 if s == "l" else -80.0])
            stand_foot = np.array([o * 14.0, P["pelvis"][1] - 2.0, max(8.0, lip[2] + 8.0)])
            ankle = lerp(lerp(hang_foot, up_foot, knee_up), stand_foot, stand)
            p.leg(s, ankle, pole=(o * 0.2, 1.0, 0.2), toe=unit((0.1 * o, 1.0, -0.4 * (1 - stand))), sole=UP)
        frame = p.frame_dict()
        if self.idle is not None and t > 0.75:
            frame = mp.blend_frames(frame, self.idle, smooth((t - 0.75) / 0.25), m.parent)
        return frame

    # ------------------------------------------------------------------ glide
    def glide(self, ph):
        """Arms-out soar (no glider prop yet): body pitched forward, arms spread, legs trailing; gentle bank."""
        m = self.m
        w = 2 * math.pi * ph
        bank = 6.0 * math.sin(w)
        p = Pose(m)
        body = euler(pitch=62.0, roll=bank)
        p.rel["pelvis"] = body
        p.pelvis_pos = np.array([0.0, -18.0, 118.0 + 2.0 * math.sin(2 * w)])
        p.spine(pitch=-12.0, roll=-bank * 0.3)
        p.head(pitch=-58.0, roll=-bank * 0.4)
        for s in SIDES:
            p.shrug(s, up_deg=4.0, fwd_deg=-6.0)
        G, P = p.fk()
        for s, o in SIDES.items():
            sh = P[f"upperarm_{s}"]
            flutter = 2.5 * math.sin(2 * w + (0.0 if s == "l" else 1.3))
            wrist = sh + body @ np.array([o * 50.0, -14.0, -2.0 + flutter])
            p.arm(s, wrist, pole=body @ np.array([0.0, -1.0, -0.3]), fingers=unit((o, -0.1, -0.1)),
                  palm=(0.0, 0.0, -1.0))   # palms to the ground
            p.grip(s, 12.0, thumb=5.0)
        G, P = p.fk()
        for s, o in SIDES.items():
            hip = P[f"thigh_{s}"]
            drift = 3.0 * math.sin(w + (0.0 if s == "l" else 2.0))
            ankle = hip + body @ np.array([o * (9.0 + drift * 0.3), -8.0, -80.0 + drift])
            p.leg(s, ankle, pole=body @ np.array([0.0, 1.0, -0.1]), toe=body @ unit((0.0, 0.25, -1.0)),
                  sole=body @ unit((0.0, 1.0, 0.25)))
        return p


CLIPS = {
    # name: (seconds, loop, builder(clips, phase_or_time))
    "AW_Climb_Idle": (2.0, True, lambda c, x: c.climb_idle(x)),
    "AW_Climb_Up": (1.0, True, lambda c, x: c.climb_up(x)),
    "AW_Climb_Down": (1.0, True, lambda c, x: c.climb_up((1.0 - x) % 1.0)),
    "AW_Climb_Left": (1.0, True, lambda c, x: c.climb_side(x, True)),
    "AW_Climb_Right": (1.0, True, lambda c, x: c.climb_side(x, False)),
    "AW_Climb_Leap": (0.55, False, lambda c, x: c.climb_leap(x)),
    "AW_Hang_Idle": (2.4, True, lambda c, x: c.hang_idle(x)),
    "AW_Hang_Left": (1.0, True, lambda c, x: c.hang_side(x, True)),
    "AW_Hang_Right": (1.0, True, lambda c, x: c.hang_side(x, False)),
    "AW_Mantle": (0.5, False, lambda c, x: c.mantle(x)),
    "AW_Glide": (2.4, True, lambda c, x: c.glide(x)),
}


def build(c: Clips, names=None):
    out = {}
    for name, (secs, loop, fn) in CLIPS.items():
        if names and name not in names:
            continue
        n = int(round(secs * FPS))
        frames = []
        for f in range(n + 1):
            x = (f / n) if loop else (f / n) * (secs if name != "AW_Mantle" else 1.0)
            if loop:
                x = x % 1.0 if f < n else 0.0     # the last key repeats the first: a seamless loop
            r = fn(c, x)
            frames.append(r if isinstance(r, dict) else r.frame_dict())
        out[name] = {"fps": FPS, "loop": loop, "seconds": secs, "frames": frames}
    return out


def idle_frame(manny, poses_path):
    if not poses_path:
        return None
    poses = json.loads(Path(poses_path).read_text())["poses"]
    idle = next((p for p in poses if p["anim"] == "MM_Idle"), None)
    if idle is None:
        return None
    frame = {n: {"pos": idle["bones"][n]["pos"], "quat": idle["bones"][n]["quat"]} for n in manny.order}
    return mp.with_locals(frame, manny.parent)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("refpose")
    ap.add_argument("out")
    ap.add_argument("--idle-pose")
    ap.add_argument("--wall", type=float, default=62.0)
    ap.add_argument("--lip-y", type=float, default=82.0)
    ap.add_argument("--lip-z", type=float, default=207.0)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    manny = mp.Manny(a.refpose)
    clips = Clips(manny, a.wall, a.lip_y, a.lip_z, idle_frame(manny, a.idle_pose))
    names = [n for n in a.only.split(",") if n]
    data = build(clips, names)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "traversal_clips.json").write_text(json.dumps({"schema": "rac.manny-clips.v1", "space": "UE component space, cm",
                                                           "clips": data}))
    preview = []
    for name, clip in data.items():
        n = len(clip["frames"]) - 1
        for k in sorted({0, n // 4, n // 2, (3 * n) // 4}):
            preview.append({"anim": name, "time": k / clip["fps"], "bones": clip["frames"][k]})
    (out / "preview_poses.json").write_text(json.dumps({"poses": preview}))
    print(json.dumps({name: len(c["frames"]) for name, c in data.items()}))


if __name__ == "__main__":
    main()
