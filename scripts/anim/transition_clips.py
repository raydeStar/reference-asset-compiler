# SPDX-License-Identifier: MIT
"""Starts and stops built from a character's own locomotion clips (runs inside Blender, after the retarget).

A game's starts and stops must agree with its movement physics, or the feet slide: the capsule decelerates on its
own curve, and an animation that stops in a different distance glides. The open libraries this pipeline may use
have no jog starts or stops (100STYLE's mocap tops out at walking pace), so these clips are composed from two
clips the user already accepted, the in-place jog cycle and the idle, on the game's exact speed curve:

* the jog is played on a time warp, phase advance = distance travelled / the jog's planted speed, so a planted
  foot stays planted while the body decelerates (or accelerates);
* the pose cross-fades jog <-> idle (local rotations slerped, pelvis lerped) on a smoothstep;
* both feet then go to explicit targets by two-bone leg IK: the planted foot holds its ground spot, the other
  foot travels on an arc to its idle spot (stop) or out of it into the jog's swing (start);
* a stop dips the pelvis as the weight is caught and settles into the idle's first frame, so the Idle state
  continues it without a pop; a start ends on the jog's frame 0, where the Walk/Run blend space begins.

Speed curves (UE CharacterMovementComponent, flat ground):
  braking   dv/dt = -(B + F v)      B = BrakingDecelerationWalking, F = BrakingFriction x BrakingFrictionFactor
  starting  dv/dt = A                A = MaxAcceleration (straight-line start from rest)
The game plays a stop at the clip time whose speed equals the capsule's (velocity matching, which for these
curves is the same as distance matching), so every release speed lands on the matching moment of the clip.

All poses are in place (the rig's root is the armature object; the engine locks it); the clip's travel goes into
its metadata (`profile`: time, speed, distance) instead of a root track.
"""
from __future__ import annotations

import math

import numpy as np
from mathutils import Matrix, Quaternion, Vector

from clip_retarget import IK_PINS, _aim


def braking_curve(v0, decel, friction):
    """(T, v(t), s(t)) for dv/dt = -(decel + friction v) from v0 to rest (m, s)."""
    if friction <= 1e-9:
        T = v0 / decel
        return T, (lambda t: max(0.0, v0 - decel * t)), (lambda t: v0 * min(t, T) - 0.5 * decel * min(t, T) ** 2)
    k = decel / friction
    T = math.log(1 + v0 / k) / friction

    def v(t):
        t = min(t, T)
        return max(0.0, (v0 + k) * math.exp(-friction * t) - k)

    def s(t):
        t = min(t, T)
        return (v0 + k) * (1 - math.exp(-friction * t)) / friction - k * t
    return T, v, s


def accel_curve(v0, accel):
    """(T, v(t), s(t)) for a constant-acceleration start from rest to v0, then constant v0 (m, s)."""
    T = v0 / accel

    def v(t):
        return min(v0, accel * t)

    def s(t):
        return 0.5 * accel * t * t if t <= T else 0.5 * accel * T * T + v0 * (t - T)
    return T, v, s


def smoothstep(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def fk(rig, local):
    world = np.empty_like(local)
    for i, p in enumerate(rig.parents):
        world[i] = (world[p] if p >= 0 else rig.mw) @ local[i]
    return world


def blend_local(a, b, w):
    """Per-bone local blend: rotations slerped, translations lerped."""
    if w <= 0:
        return a.copy()
    if w >= 1:
        return b.copy()
    out = a.copy()
    for i in range(len(a)):
        qa = Matrix(a[i][:3, :3].tolist()).to_quaternion()
        qb = Matrix(b[i][:3, :3].tolist()).to_quaternion()
        if qa.dot(qb) < 0:
            qb = Quaternion((-qb.w, -qb.x, -qb.y, -qb.z))
        out[i][:3, :3] = np.array(qa.slerp(qb, w).to_matrix())
        out[i][:3, 3] = a[i][:3, 3] * (1 - w) + b[i][:3, 3] * w
    return out


def slerp_rot(ra, rb, w):
    qa = Matrix(ra.tolist()).to_quaternion()
    qb = Matrix(rb.tolist()).to_quaternion()
    if qa.dot(qb) < 0:
        qb = Quaternion((-qb.w, -qb.x, -qb.y, -qb.z))
    return np.array(qa.slerp(qb, min(1.0, max(0.0, w))).to_matrix())


class Legs:
    """Two-bone leg IK on thigh/calf with a forward knee pole; the foot (and everything under it) gets an
    explicit world rotation. Same construction as clip_retarget.Stance, but to arbitrary ankle targets."""

    def __init__(self, rig, forward=(0.0, -1.0, 0.0)):
        self.rig, self.fwd = rig, np.array(forward, float)
        ix = rig.index
        self.legs = {}
        for s in 'lr':
            thigh, calf, foot = ix[f'thigh_{s}'], ix[f'calf_{s}'], ix[f'foot_{s}']
            l1 = np.linalg.norm(rig.rest[calf][:3, 3] - rig.rest[thigh][:3, 3])
            l2 = np.linalg.norm(rig.rest[foot][:3, 3] - rig.rest[calf][:3, 3])
            self.legs[s] = (thigh, calf, foot, l1, l2)
        self.below = {}
        for name in ('thigh', 'calf', 'foot'):
            for s in 'lr':
                root = ix[f'{name}_{s}']
                self.below[root] = [i for i in range(len(rig.parents)) if i != root and self._under(i, root)]

    def _under(self, i, root):
        p = self.rig.parents[i]
        while p != -1:
            if p == root:
                return True
            p = self.rig.parents[p]
        return False

    def _move(self, world, root, new):
        delta = new @ np.linalg.inv(world[root])
        world[root] = new
        for i in self.below[root]:
            world[i] = delta @ world[i]

    def place(self, world, side, ankle, foot_rot, knee_keep=0.3):
        thigh, calf, foot, l1, l2 = self.legs[side]
        hip = world[thigh][:3, 3]
        to = ankle - hip
        dist = min(np.linalg.norm(to), (l1 + l2) * 0.999)
        u = to / max(np.linalg.norm(to), 1e-9)
        knee_now = world[calf][:3, 3] - hip
        pole = self.fwd * (1 - knee_keep) + (knee_now - np.dot(knee_now, u) * u) * knee_keep
        pole -= np.dot(pole, u) * u
        pole /= max(np.linalg.norm(pole), 1e-9)
        a = (l1 * l1 - l2 * l2 + dist * dist) / (2 * dist)
        h = math.sqrt(max(l1 * l1 - a * a, 0.0))
        knee = hip + u * a + pole * h
        self._move(world, thigh, _aim(world[thigh], world[calf][:3, 3] - hip, knee - hip))
        new_calf = _aim(world[calf], world[foot][:3, 3] - world[calf][:3, 3], hip + u * dist - knee)
        self._move(world, calf, new_calf)
        f = world[foot].copy()
        f[:3, :3] = foot_rot
        self._move(world, foot, f)
        return world


def _pin_ik(rig, world):
    for bone, ik in IK_PINS:
        if bone in rig.index and ik in rig.index:
            world[rig.index[ik]] = world[rig.index[bone]]
    return world


def contact_phase(rig, jog, length, side, fps=120, contact_m=0.02):
    """Source time in the jog loop where `side`'s ball of foot touches down (lands after its swing)."""
    b = rig.index.get(f'ball_{side}', rig.index[f'foot_{side}'])
    n = max(16, round(length * fps))
    z = np.array([jog(length * i / n)[b][2, 3] for i in range(n)])
    low = z.min()
    down = z - low < contact_m
    for i in range(n):
        if down[i] and not down[i - 1]:
            return length * i / n
    return 0.0


def stance_window(rig, jog, length, side, fps=120, contact_m=0.02):
    """Fraction of the loop `side`'s ball of foot stays planted after touchdown (seconds)."""
    b = rig.index.get(f'ball_{side}', rig.index[f'foot_{side}'])
    t0 = contact_phase(rig, jog, length, side, fps, contact_m)
    n = max(16, round(length * fps))
    z = np.array([jog((t0 + length * i / n) % length)[b][2, 3] for i in range(n)])
    low = z.min()
    i = 0
    while i < n and z[i] - low < contact_m:
        i += 1
    return length * i / n


def foot_track(rig, worlds, travel, forward=(0.0, -1.0, 0.0)):
    """Per frame: ball-of-foot world positions (cm) with the clip's travel added back, for slip checks."""
    fwd = np.array(forward, float)
    out = []
    for w, d in zip(worlds, travel):
        row = []
        for side in 'lr':
            b = rig.index.get(f'ball_{side}', rig.index[f'foot_{side}'])
            row.append([round(float(c) * 100, 2) for c in w[b][:3, 3] + fwd * d])
        out.append(row)
    return out


def slip_report(feet, times, contact_cm=2.0):
    """Median and max horizontal speed (cm/s) of each ball of foot while it is within contact_cm of its lowest."""
    rep = {}
    for k, side in enumerate('lr'):
        z = [f[k][2] for f in feet]
        low = min(z)
        sp = []
        for i in range(1, len(feet)):
            if z[i] - low < contact_cm and z[i - 1] - low < contact_cm:
                d = math.hypot(feet[i][k][0] - feet[i - 1][k][0], feet[i][k][1] - feet[i - 1][k][1])
                sp.append(d / (times[i] - times[i - 1]))
        sp.sort()
        rep[side] = {'planted_frames': len(sp), 'slip_median_cm_s': round(sp[len(sp) // 2], 1) if sp else None,
                     'slip_max_cm_s': round(sp[-1], 1) if sp else None}
    return rep


def arc(p0, p1, u, lift):
    """A foot's swing from p0 to p1 (u in [0, 1]): eased along the ground, lifted by `lift` at mid-swing."""
    e = smoothstep(u)
    p = (p0 * (1 - e) + p1 * e).copy()
    p[2] += lift * math.sin(math.pi * min(1.0, max(0.0, u)))
    return p


def _keep_ball_above(rig, legs, world, side, target, rot, floor_z):
    """Re-place the leg so its ball of foot is not below the floor (a toe-down foot rotation under an ankle at
    standing height would push it through)."""
    b = rig.index.get(f'ball_{side}')
    if b is None:
        return world
    deficit = floor_z - world[b][2, 3]
    if deficit > 0.002:
        t = target.copy()
        t[2] += deficit
        legs.place(world, side, t, rot)
    return world


def build_stop(rig, jog, jog_length, jog_speed, idle, idle_length, side, v0, decel, friction,
               settle_s=0.4, blend=(0.0, 0.45), dip_m=0.03, fps=30, forward=(0.0, -1.0, 0.0),
               through_land_s=0.22, close_s=0.28, through_lift_m=0.10, close_lift_m=0.07):
    """World poses for a jog-to-idle stop in two steps. `side` is the foot planted at the start; the other foot
    steps through to its idle spot (landing at through_land_s), then the planted foot closes up to its idle spot
    (over close_s). The body follows the time-warped jog cross-fading into the idle; the feet go where the steps
    say by leg IK. jog(t)/idle(t): in-place world poses (layers already applied); jog_speed: the jog's planted
    ground speed (m/s). Returns (worlds, meta)."""
    fwd = np.array(forward, float)
    T_brake, v, s = braking_curve(v0, decel, friction)
    D = s(T_brake)
    length = T_brake + settle_s
    n = max(2, round(length * fps) + 1)
    other = 'r' if side == 'l' else 'l'
    phi0 = contact_phase(rig, jog, jog_length, side)
    legs = Legs(rig, forward)
    pelvis = rig.index['pelvis']
    body = [pelvis] + [k for k in range(len(rig.parents)) if legs._under(k, pelvis)]
    fp, fo = rig.index[f'foot_{side}'], rig.index[f'foot_{other}']
    idle_end = idle(0.0)              # the Idle state begins on the idle's frame 0
    J0 = jog(phi0)
    ball = {sd: rig.index.get(f'ball_{sd}') for sd in 'lr'}
    floor_ball = {sd: idle_end[ball[sd]][2, 3] if ball[sd] is not None else 0.0 for sd in 'lr'}
    # step plan in world space (the root frame at t = 0); the travel D carries the body forward
    plant0 = J0[fp][:3, 3].copy()
    plant0[2] = idle_end[fp][2, 3]
    plant_end = idle_end[fp][:3, 3] + fwd * D
    other0 = J0[fo][:3, 3].copy()
    other_end = idle_end[fo][:3, 3] + fwd * D
    close_lift = through_land_s - 0.03
    close_land = close_lift + close_s
    worlds, prof = [], []
    for i in range(n):
        t = length * i / (n - 1)
        here = fwd * s(t)                                  # world -> root frame: subtract the travel
        J = jog((phi0 + s(t) / jog_speed) % jog_length)
        idle_pose = idle((t - length) % idle_length)
        w = smoothstep((t - blend[0]) / (blend[1] - blend[0]))
        world = fk(rig, blend_local(rig.world_to_local(J), rig.world_to_local(idle_pose), w))
        dip = dip_m * math.sin(math.pi * min(1.0, max(0.0, t / (close_land + 0.1))))
        drop = np.eye(4)
        drop[2, 3] = -dip
        for j in body:
            world[j] = drop @ world[j]
        u_o = t / through_land_s
        target_o = (arc(other0, other_end, u_o, through_lift_m) if u_o < 1 else other_end) - here
        rot_o = slerp_rot(J0[fo][:3, :3], idle_end[fo][:3, :3], u_o)
        u_p = (t - close_lift) / close_s
        if u_p <= 0:
            target_p = plant0 - here
        elif u_p < 1:
            target_p = arc(plant0, plant_end, u_p, close_lift_m) - here
        else:
            target_p = plant_end - here
        # a planted foot keeps its rotation (turning it about the ankle would swing the ball sideways)
        rot_p = slerp_rot(J0[fp][:3, :3], idle_end[fp][:3, :3], u_p)
        legs.place(world, other, target_o, rot_o)
        legs.place(world, side, target_p, rot_p)
        if u_o >= 1:
            _keep_ball_above(rig, legs, world, other, target_o, rot_o, floor_ball[other])
        if u_p <= 0 or u_p >= 1:
            _keep_ball_above(rig, legs, world, side, target_p, rot_p, floor_ball[side])
        worlds.append(_pin_ik(rig, world))
        prof.append([round(t, 4), round(v(t) * 100, 2), round(s(t) * 100, 2)])
    meta = {'kind': 'stop', 'plant': side, 'v0_cm_s': v0 * 100, 'braking_decel_cm_s2': decel * 100,
            'braking_friction': friction, 'brake_s': round(T_brake, 4), 'settle_s': settle_s,
            'distance_cm': round(D * 100, 2), 'jog_phase0_s': round(phi0, 4),
            'steps': {'through_land_s': through_land_s, 'close_lift_s': round(close_lift, 3),
                      'close_land_s': round(close_land, 3)}, 'profile': prof}
    meta['feet'] = foot_track(rig, worlds, [r[2] / 100 for r in prof], forward)
    meta['slip'] = slip_report(meta['feet'], [r[0] for r in prof])
    return worlds, meta


def _ball_down(rig, J, side, floor_z, contact_m=0.02):
    b = rig.index.get(f'ball_{side}', rig.index[f'foot_{side}'])
    return J[b][2, 3] - floor_z < contact_m


def build_start(rig, jog, jog_length, jog_speed, idle, idle_length, v0, accel, run_s=0.2, blend=(0.0, 0.32),
                fps=30, forward=(0.0, -1.0, 0.0), first='l', first_lift_s=0.03, first_land_s=0.28, lift_m=0.09,
                push_s=0.12):
    """World poses for an idle-to-jog start that steps off with `first`. The jog's time warp is phased so its
    `first` foot touches down at first_land_s; that foot steps from its idle spot onto the touchdown, the other
    holds its idle spot until the jog lifts it (push-off) and joins the jog's swing push_s later; from then on
    both feet follow the jog. Begins on the idle's frame 0; ends on jog phase `jog_phase_end_s` (meta), which
    the game's Walk/Run state starts its blend space at. Returns (worlds, meta)."""
    fwd = np.array(forward, float)
    T_acc, v, s = accel_curve(v0, accel)
    length = T_acc + run_s
    n = max(2, round(length * fps) + 1)
    total = s(length)
    legs = Legs(rig, forward)
    second = 'r' if first == 'l' else 'l'
    phi_end = (contact_phase(rig, jog, jog_length, first) + (total - s(first_land_s)) / jog_speed) % jog_length

    def phi_of(t):
        return (phi_end - (total - s(t)) / jog_speed) % jog_length

    idle0 = idle(0.0)
    feet = {sd: rig.index[f'foot_{sd}'] for sd in 'lr'}
    ball = {sd: rig.index.get(f'ball_{sd}', feet[sd]) for sd in 'lr'}
    floor_ball = {sd: idle0[ball[sd]][2, 3] for sd in 'lr'}
    # when the jog lifts the second foot (its push-off) after the first has landed
    lift_second = None
    t = first_land_s - 0.05
    while t < length:
        if not _ball_down(rig, jog(phi_of(t)), second, floor_ball[second] - 0.01, 0.03):
            lift_second = t
            break
        t += 1 / 120
    lift_second = lift_second if lift_second is not None else first_land_s
    plan = {first: (first_lift_s, first_land_s), second: (lift_second, min(length, lift_second + push_s))}
    worlds, prof = [], []
    for i in range(n):
        t = length * i / (n - 1)
        here = fwd * s(t)
        J = jog(phi_of(t))
        idle_pose = idle(t % idle_length)
        w = smoothstep((t - blend[0]) / (blend[1] - blend[0]))
        world = fk(rig, blend_local(rig.world_to_local(idle_pose), rig.world_to_local(J), w))
        for sd in 'lr':
            f = feet[sd]
            lift, join = plan[sd]
            start_p = idle0[f][:3, 3]
            if t <= lift:
                target = start_p - here
            elif t < join:
                end_p = jog(phi_of(join))[f][:3, 3] + fwd * s(join)
                target = arc(start_p, end_p, (t - lift) / (join - lift), lift_m if sd == first else 0.0) - here
            else:
                target = J[f][:3, 3]
            k = min(1.0, max(0.0, (t - lift) / max(join - lift, 1e-3)))
            rot = slerp_rot(idle0[f][:3, :3], J[f][:3, :3], k)
            legs.place(world, sd, target, rot)
            if t <= lift:
                _keep_ball_above(rig, legs, world, sd, target, rot, floor_ball[sd])
        worlds.append(_pin_ik(rig, world))
        prof.append([round(t, 4), round(v(t) * 100, 2), round(s(t) * 100, 2)])
    meta = {'kind': 'start', 'v0_cm_s': v0 * 100, 'accel_cm_s2': accel * 100, 'accel_s': round(T_acc, 4),
            'run_s': run_s, 'distance_cm': round(total * 100, 2), 'first_foot': first,
            'jog_phase_end_s': round(phi_end, 4), 'jog_length_s': round(jog_length, 4),
            'steps': {sd: [round(x, 3) for x in plan[sd]] for sd in 'lr'}, 'profile': prof}
    meta['feet'] = foot_track(rig, worlds, [r[2] / 100 for r in prof], forward)
    meta['slip'] = slip_report(meta['feet'], [r[0] for r in prof])
    return worlds, meta


def _rot_z(angle):
    c, s_ = math.cos(angle), math.sin(angle)
    return np.array([[c, -s_, 0.0], [s_, c, 0.0], [0.0, 0.0, 1.0]])


def build_pivot(rig, jog, jog_length, jog_speed, turn, v0, accel, friction, yaw_rate_deg=720.0, end_phase=None,
                fps=30, forward=(0.0, -1.0, 0.0), lift_m=0.10, min_run_s=0.1):
    """World poses for a 180-degree running pivot (the stick reversed at the jog), in the actor's frame while the actor
    itself turns at yaw_rate_deg (CharacterMovement bOrientRotationToMovement) and its velocity reverses on the
    movement component's curve: dv/dt = -(friction v + accel) down to rest (friction = 2 x GroundFriction, the
    reversed input pulling against the velocity), then accel back up to v0 the other way.

    turn: 'l' or 'r', the side the body turns to (Blender: 'l' is counter-clockwise from above). The inside foot plants
    at the reversal and pivots on its ball; the outside foot swings round and lands on the jog's touchdown in the new
    direction; the planted foot pushes off just after and joins the jog's swing. The clip runs on at the jog until its
    phase reaches end_phase (seconds into the jog loop; the start's end phase, where the Walk/Run blend space resumes).
    Returns (worlds, meta)."""
    fwd = np.array(forward, float)
    T1, v_dec, s_dec = braking_curve(v0, accel, friction)
    T_acc, v_acc, s_acc = accel_curve(v0, accel)
    run_s = min_run_s
    if end_phase is not None:
        swing_ = 'r' if turn == 'l' else 'l'
        t_land_ = T1 + 0.10
        at_min = (contact_phase(rig, jog, jog_length, swing_)
                  + (s_acc(T_acc + min_run_s) - s_acc(t_land_ - T1)) / jog_speed) % jog_length
        run_s = min_run_s + ((end_phase - at_min) % jog_length) * jog_speed / v0
    length = T1 + T_acc + run_s
    n = max(2, round(length * fps) + 1)
    sign = 1.0 if turn == 'l' else -1.0
    yaw_rate = math.radians(yaw_rate_deg)

    def psi(t):
        return sign * min(math.pi, yaw_rate * t)

    def travel(t):                     # along the original forward: out, then back
        return s_dec(t) - (s_acc(t - T1) if t > T1 else 0.0)

    def speed(t):
        return v_dec(t) if t <= T1 else -v_acc(t - T1)

    origin = rig.mw[:3, 3]

    def to_actor(p, t):               # world point -> the actor's frame at time t
        return _rot_z(-psi(t)) @ (p - origin - fwd * travel(t)) + origin

    def to_world(p, t):
        return _rot_z(psi(t)) @ (p - origin) + origin + fwd * travel(t)

    plant = turn
    swing = 'r' if turn == 'l' else 'l'
    legs = Legs(rig, forward)
    fp, fs = rig.index[f'foot_{plant}'], rig.index[f'foot_{swing}']
    bp = rig.index.get(f'ball_{plant}', fp)
    phi0 = contact_phase(rig, jog, jog_length, plant)
    J0 = jog(phi0)
    floor_ball = J0[bp][2, 3]
    # the planted foot pivots on its ball: ball fixed in the world, foot yaw following the body
    ball_w = J0[bp][:3, 3].copy()
    foot0_rot = J0[fp][:3, :3]
    ankle_from_ball = J0[fp][:3, 3] - J0[bp][:3, 3]
    # the new direction's jog: phased so the swing foot touches down at t_land
    t_land = T1 + 0.10
    phi_new_land = contact_phase(rig, jog, jog_length, swing)

    def s_new(t):
        return s_acc(t - T1) if t > T1 else 0.0

    def phi_new(t):
        return (phi_new_land + (s_new(t) - s_new(t_land)) / jog_speed) % jog_length

    def phi_old(t):
        return (phi0 + s_dec(min(t, T1)) / jog_speed) % jog_length

    swing0_w = to_world(J0[fs][:3, 3], 0.0)
    land_w = to_world(jog(phi_new(t_land))[fs][:3, 3], t_land)
    land_w[2] = J0[fs][2, 3] if J0[fs][2, 3] < land_w[2] else land_w[2]
    push = t_land + 0.04
    join_p = push + 0.12
    worlds, prof = [], []
    for i in range(n):
        t = length * i / (n - 1)
        Jo, Jn = jog(phi_old(t)), jog(phi_new(t))
        w = smoothstep((t - 0.03) / (t_land + 0.02))
        world = fk(rig, blend_local(rig.world_to_local(Jo), rig.world_to_local(Jn), w))
        # swing foot: round from behind onto the new touchdown, then the new jog
        if t < t_land:
            u = t / t_land
            target_s = to_actor(arc(swing0_w, land_w, u, lift_m), t)
            rot_s = slerp_rot(J0[fs][:3, :3], Jn[fs][:3, :3], u)
        else:
            target_s, rot_s = Jn[fs][:3, 3], Jn[fs][:3, :3]
        # planted foot: pivot on the ball until it pushes off, then swing into the new jog
        yaw_w = _rot_z(psi(min(t, push)))
        rot_p_w = yaw_w @ foot0_rot
        ankle_w = ball_w + yaw_w @ ankle_from_ball
        if t <= push:
            target_p = to_actor(ankle_w, t)
            rot_p = _rot_z(-psi(t)) @ rot_p_w
        elif t < join_p:
            u = (t - push) / (join_p - push)
            end_w = to_world(jog(phi_new(join_p))[fp][:3, 3], join_p)
            target_p = to_actor(arc(ankle_w, end_w, u, lift_m * 0.6), t)
            rot_p = slerp_rot(_rot_z(-psi(t)) @ rot_p_w, Jn[fp][:3, :3], u)
        else:
            target_p, rot_p = Jn[fp][:3, 3], Jn[fp][:3, :3]
        legs.place(world, swing, target_s, rot_s)
        legs.place(world, plant, target_p, rot_p)
        if t <= push:
            _keep_ball_above(rig, legs, world, plant, target_p, rot_p, floor_ball)
        worlds.append(_pin_ik(rig, world))
        prof.append([round(t, 4), round(speed(t) * 100, 2), round(travel(t) * 100, 2), round(math.degrees(psi(t)), 1)])
    # slip check in the world: put each frame back where the actor stood and faced
    feet = []
    for w_, (t, _, _, _) in zip(worlds, prof):
        row = []
        for side in 'lr':
            b = rig.index.get(f'ball_{side}', rig.index[f'foot_{side}'])
            row.append([round(float(c) * 100, 2) for c in to_world(w_[b][:3, 3], t)])
        feet.append(row)
    meta = {'kind': 'pivot', 'turn': turn, 'plant': plant, 'v0_cm_s': v0 * 100, 'accel_cm_s2': accel * 100,
            'reverse_friction': friction, 'yaw_rate_deg_s': yaw_rate_deg, 'reverse_s': round(T1, 4),
            'jog_phase0_s': round(phi0, 6),
            'touchdown_s': round(t_land, 3), 'push_off_s': round(push, 3), 'run_s': round(run_s, 4),
            'jog_phase_end_s': round(phi_new(length), 4), 'length_s': round(length, 4),
            'profile': prof, 'feet': feet, 'slip': slip_report(feet, [r[0] for r in prof])}
    return worlds, meta


def _keyed(keys, t):
    """Smooth interpolation through (time, value) keys: smoothstep between neighbours, flat outside."""
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            return v0 + (v1 - v0) * smoothstep((t - t0) / max(t1 - t0, 1e-6))
    return keys[-1][1]


def _turn_subtree(rig, world, bone, axis, degrees, below):
    """Rotate a bone and everything under it about its own head, around a world axis."""
    i = rig.index[bone]
    p = world[i][:3, 3].copy()
    M = np.eye(4)
    M[:3, :3] = np.array(Matrix.Rotation(math.radians(degrees), 3, Vector(axis.tolist())))
    M[:3, 3] = p - M[:3, :3] @ p
    for j in [i] + below:
        world[j] = M @ world[j]


def build_backhop(rig, idle, idle_length, fps=30, forward=(0.0, -1.0, 0.0), lateral=(1.0, 0.0, 0.0),
                  pelvis_keys=((0.0, 0.0), (0.06, -0.14), (0.19, 0.08), (0.32, -0.17), (0.46, -0.06), (0.62, 0.0)),
                  foot_lift_keys=((0.0, 0.0), (0.07, 0.0), (0.14, 0.18), (0.22, 0.24), (0.30, 0.04), (0.32, 0.0)),
                  foot_fwd_keys=((0.0, 0.0), (0.07, 0.04), (0.2, 0.16), (0.32, 0.05), (0.62, 0.0)),
                  lean_keys=((0.0, 0.0), (0.06, 12.0), (0.19, 24.0), (0.32, 16.0), (0.62, 0.0)),
                  arm_keys=((0.0, 0.0), (0.1, 45.0), (0.3, 25.0), (0.62, 0.0))):
    """World poses for an in-place evasive hop backwards (the game moves the capsule ~3.6 m in 0.34 s, faster than any
    step): crouch, both feet leave the ground with the body pitched forward and the arms thrown forward for balance,
    land low behind, and rise back into the idle (on its frame 0). Built on the idle by keyed offsets: pelvis height,
    foot lift and reach, spine pitch, upper-arm swing; feet by leg IK. Returns (worlds, meta)."""
    fwd, lat = np.array(forward, float), np.array(lateral, float)
    length = pelvis_keys[-1][0]
    n = max(2, round(length * fps) + 1)
    legs = Legs(rig, forward)
    pelvis = rig.index['pelvis']
    under = {b: [k for k in range(len(rig.parents)) if legs._under(k, rig.index[b])]
             for b in ('pelvis', 'spine_01', 'upperarm_l', 'upperarm_r') if b in rig.index}
    I0 = idle(0.0)
    worlds = []
    for i in range(n):
        t = length * i / (n - 1)
        world = idle(t % idle_length)
        dz = _keyed(pelvis_keys, t)
        drop = np.eye(4)
        drop[2, 3] = dz
        for j in [pelvis] + under['pelvis']:
            world[j] = drop @ world[j]
        # positive about the lateral (+X, the character's left) axis pitches the chest forward
        _turn_subtree(rig, world, 'spine_01', lat, _keyed(lean_keys, t), under['spine_01'])
        for side in 'lr':
            arm = f'upperarm_{side}'
            if arm in rig.index:
                _turn_subtree(rig, world, arm, lat, -_keyed(arm_keys, t), under[arm])
        for side in 'lr':
            f = rig.index[f'foot_{side}']
            target = I0[f][:3, 3] + fwd * _keyed(foot_fwd_keys, t)
            target[2] += _keyed(foot_lift_keys, t)
            legs.place(world, side, target, I0[f][:3, :3])
        worlds.append(_pin_ik(rig, world))
    chest = rig.index.get('spine_05', rig.index.get('spine_03'))
    lean_check = [round(float(np.dot(w[chest][:3, 3] - w[pelvis][:3, 3], fwd)) * 100, 1) for w in worlds[::3]]
    meta = {'kind': 'backhop', 'length_s': round(length, 4), 'chest_ahead_of_pelvis_cm': lean_check,
            'keys': {'pelvis_m': pelvis_keys, 'foot_lift_m': foot_lift_keys, 'foot_forward_m': foot_fwd_keys,
                     'spine_pitch_deg': lean_keys, 'arm_swing_deg': arm_keys}}
    return worlds, meta


def with_runin(rig, jog, jog_length, jog_speed, worlds, meta, runin_s, forward=(0.0, -1.0, 0.0)):
    """Prepend runin_s of the plain jog (at the transition's starting speed) leading into the clip's first frame, the
    plant foot's touchdown. The stick is released or reversed anywhere in the stride, often with both feet in the air:
    the game enters the clip runin_s minus the plant foot's time to touchdown, so the jog carries on in the air and the
    foot lands where the clip plants it (instead of a crossfade dragging it there). Frame spacing matches the clip's."""
    fwd = np.array(forward, float)
    prof = meta['profile']
    dt = prof[1][0] - prof[0][0]
    m = max(1, round(runin_s / dt))
    runin = m * dt
    v0 = prof[0][1] / 100.0
    phi0 = meta['jog_phase0_s']
    pre, pre_prof, pre_feet = [], [], []
    for k in range(m):
        t = -runin + k * dt                       # before touchdown
        w = jog((phi0 + v0 * t / jog_speed) % jog_length)
        pre.append(_pin_ik(rig, w))
        row = list(prof[0])
        row[0], row[1], row[2] = round(t, 4), round(v0 * 100, 2), round(v0 * t * 100, 2)
        pre_prof.append(row)
        feet = []
        for side in 'lr':
            b = rig.index.get(f'ball_{side}', rig.index[f'foot_{side}'])
            feet.append([round(float(c) * 100, 2) for c in w[b][:3, 3] + fwd * (v0 * t)])
        pre_feet.append(feet)
    worlds = pre + worlds
    meta['profile'] = [[round(r[0] + runin, 4), *r[1:]] for r in pre_prof + prof]
    meta['feet'] = pre_feet + meta['feet']
    meta['slip'] = slip_report(meta['feet'][m:], [r[0] for r in meta['profile']][m:])
    meta['runin_s'] = round(runin, 4)
    return worlds, meta
