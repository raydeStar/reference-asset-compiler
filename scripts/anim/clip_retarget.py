# SPDX-License-Identifier: MIT
"""Retarget clips from an open animation library onto a character's game rig (runs inside Blender).

The transfer is by world rotation relative to a matched reference pose (both rigs in a T-pose):

    R_tgt(t) = A . R_src(t) . R_src_ref^-1 . A^-1 . R_tgt_rest

A is the yaw that takes the source's right-to-left shoulder line onto the target's, so the two rigs'
bone-axis conventions never matter. The pelvis displacement is scaled by hip height. Target bones the map
leaves out keep their rest offset from their parent; the UE IK bones (ik_foot_*, ik_hand_*) are pinned to
the bones they shadow, because the UE template's foot IK plants the feet on them.

Library adapters: `ual` (Quaternius Universal Animation Library 1 and 2, CC0; its A_TPose action is the
reference). A bone map is a JSON {source bone: target bone}; profiles/animation/ holds the shipped ones.
Used by scripts/anim/bake_library_clips.py (UE tracks) and scripts/anim/preview_library_clip.py (renders).
"""
from __future__ import annotations

import math
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector

UE_AXES = Matrix.Diagonal((1., -1., 1., 1.))
IK_PINS = [('foot_l', 'ik_foot_l'), ('foot_r', 'ik_foot_r'), ('hand_r', 'ik_hand_gun'),
           ('hand_l', 'ik_hand_l'), ('hand_r', 'ik_hand_r')]


def ue_from_matrix(matrix):
    """A Blender bone-local matrix (metres) as a UE local transform [x, y, z cm, qx, qy, qz, qw]."""
    m = UE_AXES @ Matrix(np.asarray(matrix).tolist()) @ UE_AXES
    q = m.to_quaternion()
    return [*(m.translation * 100), q.x, q.y, q.z, q.w]


class TargetRig:
    """The character's game armature: rest data in world space and parent-first ordering."""

    def __init__(self, armature):
        self.obj = armature
        self.bones = list(armature.data.bones)
        self.names = [b.name for b in self.bones]
        self.index = {n: i for i, n in enumerate(self.names)}
        self.parents = [self.index[b.parent.name] if b.parent else -1 for b in self.bones]
        assert all(p < i for i, p in enumerate(self.parents)), 'Parent-first bone ordering required.'
        self.mw = np.array(armature.matrix_world)
        self.rest = np.array([self.mw @ np.array(b.matrix_local) for b in self.bones])
        self.local_rest = np.array([np.linalg.inv(np.array(b.parent.matrix_local)) @ np.array(b.matrix_local)
                                    if b.parent else np.array(b.matrix_local) for b in self.bones])

    def world_to_local(self, world):
        local = np.empty_like(world)
        inv_mw = np.linalg.inv(self.mw)
        for i, p in enumerate(self.parents):
            local[i] = np.linalg.inv(world[p]) @ world[i] if p >= 0 else inv_mw @ world[i]
        return local

    def apply(self, local):
        for i, n in enumerate(self.names):
            self.obj.pose.bones[n].matrix_basis = Matrix((np.linalg.inv(self.local_rest[i]) @ local[i]).tolist())


class UalLibrary:
    """A Quaternius UAL file (FBX or glTF) imported beside the character, hidden from renders."""

    def __init__(self, path):
        before = set(bpy.data.objects)
        before_actions = set(bpy.data.actions)
        if str(path).lower().endswith('.fbx'):
            bpy.ops.import_scene.fbx(filepath=str(path))     # sets the scene to the file's own frame rate
        else:
            bpy.ops.import_scene.gltf(filepath=str(path))    # converts seconds at the scene's frame rate
        scene = bpy.context.scene
        self.fps = scene.render.fps / scene.render.fps_base
        new = set(bpy.data.objects) - before
        self.rig = next(o for o in new if o.type == 'ARMATURE')
        for o in new:
            o.hide_render = True    # hide_viewport would stop the depsgraph evaluating its pose
        # This file's actions only: a second library must not shadow the first's clips.
        self.actions = {a.name.split('|')[-1]: a for a in set(bpy.data.actions) - before_actions
                        if any(fc for fc in _fcurves(a))}
        self.rig.animation_data_create()

    def length(self, action):
        start, end = self.actions[action].frame_range
        return (end - start) / self.fps

    def world(self, action, t, loop=True):
        """{bone: 4x4 world matrix} at time t seconds."""
        act = self.actions[action]
        start, end = act.frame_range
        frame = start + ((t % self.length(action)) if loop else min(t, self.length(action))) * self.fps
        ad = self.rig.animation_data
        if ad.action is not act:
            ad.action = act
            if hasattr(ad, 'action_slot') and act.slots:
                ad.action_slot = act.slots[0]
        bpy.context.scene.frame_set(int(frame), subframe=frame - int(frame))
        mw = np.array(self.rig.matrix_world)
        return {pb.name: mw @ np.array(pb.matrix) for pb in self.rig.pose.bones}

    def reference(self):
        return self.world('A_TPose', 0.0, loop=False)


def _bvh_frame_time(path):
    with open(path, encoding='latin-1') as f:
        for line in f:
            if line.strip().startswith('Frame Time:'):
                return float(line.split(':')[1])
    raise ValueError(f'{path}: no Frame Time')


class BvhLibrary:
    """A folder of BVH takes sharing one skeleton (e.g. 100STYLE, CC BY 4.0). Each take imports once into its own
    armature; the reference is the BVH rest pose (a T-pose for 100STYLE) with the hips at a standing height
    measured from the data (BVH rests the hips at the origin)."""

    def __init__(self, folder, takes, hips='Hips', fps=None):
        self.folder, self.hips = Path(folder), hips
        self.rigs, self.actions, self.fps_of = {}, {}, {}
        for take in takes:
            before = set(bpy.data.objects)
            bpy.ops.import_anim.bvh(filepath=str(self.folder / f'{take}.bvh'), global_scale=0.01, rotate_mode='NATIVE',
                                    axis_forward='-Z', axis_up='Y', update_scene_fps=False, update_scene_duration=False)
            rig = next(o for o in set(bpy.data.objects) - before if o.type == 'ARMATURE')
            rig.hide_render = True
            self.rigs[take] = rig
            self.actions[take] = rig.animation_data.action
            # The importer keys one BVH frame per scene frame: time comes from the take's own Frame Time.
            self.fps_of[take] = fps or 1.0 / _bvh_frame_time(self.folder / f'{take}.bvh')
        self.rig = next(iter(self.rigs.values()))

    def length(self, take):
        start, end = self.actions[take].frame_range
        return (end - start) / self.fps_of[take]

    def world(self, take, t, loop=True):
        rig, act = self.rigs[take], self.actions[take]
        start, _ = act.frame_range
        L = self.length(take)
        frame = start + ((t % L) if loop else min(t, L)) * self.fps_of[take]
        bpy.context.scene.frame_set(int(frame), subframe=frame - int(frame))
        mw = np.array(rig.matrix_world)
        return {pb.name: mw @ np.array(pb.matrix) for pb in rig.pose.bones}

    def reference(self, take=None):
        take = take or next(iter(self.rigs))
        rig = self.rigs[take]
        mw = np.array(rig.matrix_world)
        ref = {b.name: mw @ np.array(b.matrix_local) for b in rig.data.bones}
        # standing hip height: median over the take
        L = self.length(take)
        heights = [self.world(take, L * i / 40, loop=False)[self.hips][2, 3] for i in range(41)]
        ref[self.hips] = ref[self.hips].copy()
        ref[self.hips][2, 3] = float(np.median(heights))
        return ref


def _fcurves(action):
    """Every F-curve of an action (Blender 5 layered actions and the legacy list)."""
    if getattr(action, 'layers', None):
        for layer in action.layers:
            for strip in layer.strips:
                for bag in getattr(strip, 'channelbags', []):
                    yield from bag.fcurves
    else:
        yield from getattr(action, 'fcurves', [])


class Retarget:
    @staticmethod
    def _leg(world, names):
        p = [world[n][:3, 3] for n in names]
        return float(np.linalg.norm(p[1] - p[0]) + np.linalg.norm(p[2] - p[1]))

    def __init__(self, target: TargetRig, library, bone_map, reference=None):
        self.t, self.lib = target, library
        self.ref = reference or library.reference()
        self.pairs = {target.index[tn]: sn for sn, tn in bone_map.items() if sn in self.ref and tn in target.index}
        inv = {tn: sn for sn, tn in bone_map.items()}
        self.leg_names = tuple(inv[n] for n in ('thigh_l', 'calf_l', 'foot_l'))
        self.src_pelvis = inv['pelvis']
        missing = sorted(set(bone_map.values()) - set(target.names))
        assert not [m for m in missing if not m.startswith(('ball', 'spine_0'))], f'target lacks {missing}'

        def heading(world, left, right):
            v = world[left][:3, 3] - world[right][:3, 3]
            return math.atan2(v[1], v[0])
        tw = {n: target.rest[i] for i, n in enumerate(target.names)}
        self.src_arms = (inv['upperarm_l'], inv['upperarm_r'])
        yaw = heading(tw, 'upperarm_l', 'upperarm_r') - heading(self.ref, *self.src_arms)
        self.A = np.array(Matrix.Rotation(yaw, 3, 'Z'))
        self.scale = self._leg(tw, ('thigh_l', 'calf_l', 'foot_l')) / self._leg(self.ref, self.leg_names)

    def _mirror(self, pose):
        """The pose reflected through the source's sagittal plane (left and right swapped)."""
        u = self.ref[self.src_arms[0]][:3, 3] - self.ref[self.src_arms[1]][:3, 3]
        u /= np.linalg.norm(u)
        S = np.eye(4)
        S[:3, :3] -= 2 * np.outer(u, u)
        p0 = np.eye(4)
        p0[:3, 3] = self.ref[self.src_pelvis][:3, 3]
        R = p0 @ S @ np.linalg.inv(p0)
        def swap(n):
            return n[:-2] + {'_l': '_r', '_r': '_l'}[n[-2:]] if n[-2:] in ('_l', '_r') else n
        return {n: R @ pose[swap(n)] @ S for n in pose if swap(n) in pose}

    def world(self, action, t, loop=True, mirror=False):
        """Target world matrices at time t. mirror plays the source's mirror image (a left-hand swing from a
        right-hand one); the T-pose reference is mirrored with it, so the rest stays symmetric."""
        src = self.lib.world(action, t, loop)
        ref = self.ref
        if mirror:
            src, ref = self._mirror(src), self._mirror(self.ref)
        tg, A = self.t, self.A
        world = np.empty_like(tg.rest)
        for i, p in enumerate(tg.parents):
            world[i] = (world[p] if p >= 0 else tg.mw) @ tg.local_rest[i]
            sn = self.pairs.get(i)
            if sn is None:
                continue
            delta = src[sn][:3, :3] @ np.linalg.inv(ref[sn][:3, :3])
            world[i][:3, :3] = A @ delta @ A.T @ tg.rest[i][:3, :3]
            if tg.names[i] == 'pelvis':
                world[i][:3, 3] = tg.rest[i][:3, 3] + A @ (src[sn][:3, 3] - ref[sn][:3, 3]) * self.scale
        for bone, ik in IK_PINS:
            if bone in tg.index and ik in tg.index:
                world[tg.index[ik]] = world[tg.index[bone]]
        return world

    def local(self, action, t, loop=True):
        return self.t.world_to_local(self.world(action, t, loop))


def planted_speed(retarget, action, forward, fps=120, contact_m=0.02):
    """Ground speed (m/s) an in-place loop implies: the backward distance a planted foot travels divided by
    the time it is planted. The ball of the foot (the heel lifts at push-off) counts as planted within
    contact_m of its lowest point; sampled at a high rate so a sprint's short contacts are seen."""
    rig = retarget.t
    names = [b for b in ('ball_l', 'ball_r') if b in rig.index] or ['foot_l', 'foot_r']
    length = retarget.lib.length(action)
    n = max(8, round(length * fps))
    pts = np.array([[w[rig.index[b]][:3, 3] for b in names]
                    for w in (retarget.world(action, length * i / n) for i in range(n + 1))])
    distance = time = 0.0
    for s in range(len(names)):
        low = pts[:, s, 2].min()
        for f in range(1, len(pts)):
            if pts[f, s, 2] - low < contact_m and pts[f - 1, s, 2] - low < contact_m:
                distance += -float(np.dot(pts[f, s] - pts[f - 1, s], forward))
                time += length / n
    return distance / time if time else 0.0


# Leg capsules the coat must clear: bone, child that ends it, radius (m). Matches TheAetherWars CoatPhysics.
LEG_CAPSULES = (('thigh_l', 'calf_l', 0.10), ('thigh_r', 'calf_r', 0.10),
                ('calf_l', 'foot_l', 0.075), ('calf_r', 'foot_r', 0.075))


def _segment_distance(p, a, b):
    ab = b - a
    t = np.clip(np.dot(p - a, ab) / max(np.dot(ab, ab), 1e-9), 0.0, 1.0)
    return float(np.linalg.norm(p - (a + t * ab)))


class CoatFollow:
    """Swing coat chains (coat_<group>_01_<side> .. _end_<side>, rac-character add_coat_chains.py) out of the
    legs' way: per frame, the smallest outward hinge angle at each chain's root that keeps every joint below
    the hinge at least min(keep x its rest clearance, floor_m) from the leg capsules; then a temporal envelope so a panel
    eases out before the knee arrives and settles after. Children keep their rest bend (physics in the game
    can add sway on top). A rig without coat bones is returned unchanged."""

    DRAPE = (0.35, 0.3)   # fraction of the hinge angle each lower joint (02, 03) bends back toward hanging

    def __init__(self, rig: TargetRig, keep=0.85, floor_m=0.04, max_deg=55, lead_frames=4, settle_frames=8):
        self.rig, self.keep, self.floor, self.max_deg = rig, keep, floor_m, max_deg
        self.lead, self.settle = lead_frames, settle_frames
        roots = [n for n in rig.names if n.startswith('coat_') and n.split('_')[2] == '01']
        self.chains = {}
        for root in roots:
            group, side = root.split('_')[1], root.split('_')[3]
            bones = [n for n in rig.names if n.startswith(f'coat_{group}_') and n.endswith(f'_{side}')]
            self.chains[root] = [rig.index[b] for b in bones]   # parent-first
        rest = {n: rig.rest[i] for i, n in enumerate(rig.names)}
        self.rest_clear = {root: [self._clearance(rest, rig.rest[i][:3, 3]) for i in idx]
                           for root, idx in self.chains.items()}

    def _clearance(self, world_by_name, p):
        return min(_segment_distance(p, world_by_name[a][:3, 3], world_by_name[b][:3, 3]) - r
                   for a, b, r in LEG_CAPSULES)

    def _swing(self, world, root, degrees):
        """World matrices of the chain with its root hinged outward by `degrees` and each lower joint bent
        back by DRAPE of it, so the panel folds over the knee like cloth instead of levering out as a board."""
        rig, idx = self.rig, self.chains[root]
        top = world[idx[0]][:3, 3]
        pelvis = world[rig.index['pelvis']][:3, 3]
        out = top - pelvis
        out[2] = 0
        out /= max(np.linalg.norm(out), 1e-9)
        axis = Vector(np.cross(np.array([0.0, 0.0, -1.0]), out).tolist()).normalized()
        moved = {i: world[i].copy() for i in idx}
        for j, i in enumerate(idx):
            angle = degrees if j == 0 else -degrees * (self.DRAPE[j - 1] if j - 1 < len(self.DRAPE) else 0.0)
            if not angle:
                continue
            pivot = moved[i][:3, 3].copy()
            m = np.eye(4)
            m[:3, :3] = np.array(Matrix.Rotation(math.radians(angle), 3, axis))
            m[:3, 3] = pivot - m[:3, :3] @ pivot
            for k in idx[j:]:
                moved[k] = m @ moved[k]
        return moved

    def required(self, world):
        """{chain root: degrees} for one frame (world: target bones x 4x4)."""
        names = {n: world[i] for i, n in enumerate(self.rig.names)}
        need = {}
        for root, idx in self.chains.items():
            # The hinge joint cannot move; judge the joints below it. A joint must stay clear of the leg
            # by min(keep x its rest clearance, floor_m): enough that cloth never enters the leg, without
            # forcing a loose back panel to keep its whole rest gap.
            target = [min(c * self.keep, self.floor) for c in self.rest_clear[root]][1:]
            for deg in range(0, self.max_deg + 1, 2):
                moved = self._swing(world, root, deg)
                if all(self._clearance(names, moved[i][:3, 3]) >= t for i, t in zip(idx[1:], target)):
                    need[root] = float(deg)
                    break
            else:
                need[root] = float(self.max_deg)
        return need

    def apply(self, worlds, loop):
        """Mutates and returns the list of per-frame world arrays."""
        if not self.chains:
            return worlds
        n = len(worlds)
        per_frame = [self.required(w) for w in worlds]
        raw = {root: np.array([pf[root] for pf in per_frame]) for root in self.chains}
        self.last = {root: {'peak_deg': float(v.max()), 'frames_needing': int((v > 0).sum())} for root, v in raw.items()}
        period = max(n - 1, 1)     # a loop's last key repeats its first
        for root, need in raw.items():
            amount = np.zeros(n)
            for f in np.nonzero(need)[0]:
                d = np.arange(n) - f
                if loop:
                    d = (d + period // 2) % period - period // 2
                # ease in over `lead` frames before the contact, out over `settle` after it
                span = np.where(d < 0, self.lead, self.settle).astype(float)
                x = np.clip(1 - np.abs(d) / span, 0, 1)
                amount = np.maximum(amount, need[f] * x * x * (3 - 2 * x))
            for f, w in enumerate(worlds):
                if amount[f] > 0:
                    for i, m in self._swing(w, root, amount[f]).items():
                        w[i] = m
        return worlds


class Sequence:
    """A clip built from one or more library actions played back to back (a swing and its recovery), with
    the pelvis carried across each join so nothing pops, optionally mirrored, retimed, and with its
    horizontal travel moved onto the root bone (root motion).

    segments: [{'library': name, 'action': name}, ...]; retargets: {library name: Retarget}."""

    def __init__(self, retargets, segments, mirror=False):
        self.rts, self.mirror = retargets, mirror
        self.segs = [(retargets[s['library']], s['action'], retargets[s['library']].lib.length(s['action']))
                     for s in segments]
        self.length = sum(L for _, _, L in self.segs)
        rig = self.segs[0][0].t
        # A rig exported with the armature object as UE's root bone has no 'root' bone in Blender.
        self.rig, self.pelvis, self.root = rig, rig.index['pelvis'], rig.index.get('root')
        self.offsets, carry = [], np.zeros(3)
        for k, (rt, action, L) in enumerate(self.segs):
            if k:
                prev_rt, prev_action, prev_L = self.segs[k - 1]
                end = prev_rt.world(prev_action, prev_L, loop=False, mirror=mirror)[self.pelvis][:3, 3] + carry
                start = rt.world(action, 0.0, loop=False, mirror=mirror)[self.pelvis][:3, 3]
                carry = carry + np.array([end[0] - start[0], end[1] - start[1], 0.0])
            self.offsets.append(carry.copy())

    def world(self, s):
        """World matrices at source time s (seconds along the joined segments)."""
        for (rt, action, L), off in zip(self.segs, self.offsets):
            if s <= L or (rt, action, L) == self.segs[-1]:
                w = rt.world(action, min(s, L), loop=False, mirror=self.mirror)
                if off.any():
                    keep = w[self.root].copy() if self.root is not None else None
                    w[:, :3, 3] += off
                    if keep is not None:
                        w[self.root] = keep
                return w
            s -= L

    def peak_speed_time(self, bone, fps=120):
        """Source time of the bone's fastest movement (the impact of a swing)."""
        i = self.rig.index[bone]
        ts = np.linspace(0, self.length, max(4, int(self.length * fps)) + 1)
        p = np.array([self.world(t)[i][:3, 3] for t in ts])
        v = np.linalg.norm(np.diff(p, axis=0), axis=1)
        return float(ts[1:][v.argmax()])


def retime(length, n, source_length, keys=()):
    """n target times over `length` and the source time each samples: piecewise linear through
    (0, 0), each (target_t, source_t) in keys, and (length, source_length)."""
    pts = sorted([(0.0, 0.0), *keys, (length, source_length)])
    tt = np.linspace(0, length, n)
    return tt, np.interp(tt, [p[0] for p in pts], [p[1] for p in pts])


def _rest_side_roots(world, rig):
    """UE parents ik_foot_root / ik_hand_root (and other side roots) to the root bone. Once a pose is expressed
    relative to the root, they belong at rest there; carried along with the pose they sit metres off whenever the
    engine locks or extracts the root, and foot IK drags the feet after them. The IK targets under them keep their
    world positions (on the hands and feet)."""
    pelvis = rig.index['pelvis']
    for i, p in enumerate(rig.parents):
        if p < 0 and i != pelvis:
            world[i] = rig.rest[i].copy()
    return world


def extract_root_motion(world, rig, start_pelvis):
    """Move the pelvis's horizontal offset from start_pelvis onto the root. Returns (world, shift): with a
    'root' bone the root (and its IK children) carry the shift; without one (the armature object is UE's root
    bone) the whole pose moves back by it, and the caller keys `shift` as UE's root track."""
    pelvis = rig.index['pelvis']
    d = world[pelvis][:3, 3] - start_pelvis
    shift = np.array([d[0], d[1], 0.0])
    root = rig.index.get('root')
    if root is not None:
        world[root][:3, 3] += shift
        for i, p in enumerate(rig.parents):      # ik_foot_root / ik_hand_root ride with the root
            if p == root and i != pelvis:
                world[i][:3, 3] += shift
    else:
        world[:, :3, 3] -= shift       # the whole pose, rigidly: these are world matrices
        _rest_side_roots(world, rig)
    return world, shift


def facing_root_motion(worlds, rig, smooth_s=0.2, fps=30, forward=(0.0, -1.0, 0.0)):
    """Root motion with facing for travelling takes (mocap): the root carries the pelvis's ground position and the
    body's heading (the pelvis's rest-forward axis on the ground), both Gaussian-smoothed so stride sway neither
    steers nor shoves it (the sway stays on the pelvis). The whole pose is re-expressed relative to that root (this rig's root is the armature
    object, so the caller keys the returned root matrices as UE's root track). Returns (worlds, roots)."""
    pelvis = rig.index['pelvis']
    rest_rot = rig.rest[pelvis][:3, :3]
    fwd = np.array(forward, float)
    heads = []
    for w in worlds:
        f = w[pelvis][:3, :3] @ np.linalg.inv(rest_rot) @ fwd
        heads.append(math.atan2(f[1], f[0]))
    rest_head = math.atan2(fwd[1], fwd[0])
    yaw = np.unwrap(np.array(heads)) - rest_head
    sigma = max(smooth_s * fps, 1e-6)
    k = np.arange(-int(2 * sigma) - 1, int(2 * sigma) + 2)
    kern = np.exp(-0.5 * (k / sigma) ** 2)
    kern /= kern.sum()
    padded = np.concatenate([np.full(len(k) // 2, yaw[0]), yaw, np.full(len(k) // 2, yaw[-1])])
    yaw = np.convolve(padded, kern, mode='valid')[:len(worlds)]
    rest_xy = rig.rest[pelvis][:3, 3].copy()
    rest_xy[2] = 0
    ground = np.array([[w[pelvis][0, 3], w[pelvis][1, 3]] for w in worlds])
    pad = len(k) // 2
    ground = np.stack([np.convolve(np.concatenate([np.full(pad, g[0]), g, np.full(pad, g[-1])]), kern, mode='valid')[:len(worlds)]
                       for g in ground.T], -1)          # the root's path is smooth; stride sway stays on the pelvis
    out, roots = [], []
    for w, a, g in zip(worlds, yaw, ground):
        R = np.eye(4)
        R[:3, :3] = np.array(Matrix.Rotation(float(a), 3, 'Z'))
        R[:3, 3] = np.array([g[0], g[1], 0.0]) - R[:3, :3] @ rest_xy
        out.append(_rest_side_roots(np.linalg.inv(R) @ w, rig))
        roots.append(R)
    return out, roots


def ue_root_matrix(rig, root):
    """UE local transform of the root bone from a world-space root matrix (rotation + translation)."""
    inv_mw = np.linalg.inv(rig.mw)
    return ue_from_matrix(inv_mw @ root)


def ue_root_track(rig, shift):
    """UE local transform of the root bone carrying a world-space horizontal shift (metres)."""
    m = np.eye(4)
    m[:3, 3] = np.linalg.inv(rig.mw[:3, :3]) @ shift
    return ue_from_matrix(m)


# Relaxed hand: curl per joint (01, 02, 03) in degrees, toward the palm. Index to pinky curl a little more
# each, as a hand at rest does; the thumb barely flexes.
RELAXED_CURL = {'index': (18, 30, 18), 'middle': (22, 34, 20), 'ring': (26, 38, 22), 'pinky': (30, 42, 24),
                'thumb': (12, 16, 12)}


class RelaxedHands:
    """Replace the fingers with a relaxed rest curl, carried by the animated hand. The curl is built on the
    rig's own rest geometry: each joint bends about the axis across its finger and the palm normal, so it
    does not depend on bone-axis conventions. The palm faces down in the T-pose (palm = -Z)."""

    def __init__(self, rig: TargetRig, curl=None, palm=(0.0, 0.0, -1.0), spread_keep=0.3, thumb_tuck_deg=18):
        self.rig, curl = rig, curl or RELAXED_CURL
        palm = np.array(palm, float)
        self.local = {}            # finger bone index -> world matrix relative to its hand, relaxed
        ix = rig.index

        def joint(name):
            return rig.rest[ix[name]][:3, 3]

        def rotate_chain(world, chain, start, axis, deg, pivot):
            r = np.eye(4)
            r[:3, :3] = np.array(Matrix.Rotation(math.radians(deg), 3, Vector((axis / np.linalg.norm(axis)).tolist())))
            r[:3, 3] = pivot - r[:3, :3] @ pivot
            for k in chain[start:]:
                world[k] = r @ world[k]
        for side in 'lr':
            hand = ix.get(f'hand_{side}')
            if hand is None or f'middle_01_{side}' not in ix:
                continue
            inv_hand = np.linalg.inv(rig.rest[hand])
            mid_dir = joint(f'middle_02_{side}') - joint(f'middle_01_{side}')
            for finger, angles in curl.items():
                names = [f'{finger}_{k:02d}_{side}' for k in (1, 2, 3)]
                if any(n not in ix for n in names):
                    continue
                chain = [ix[n] for n in names]
                world = {i: rig.rest[i].copy() for i in chain}
                # Close the spread: turn the finger about the palm normal toward the middle finger.
                base = world[chain[0]][:3, 3].copy()
                d0 = joint(names[1]) - joint(names[0])
                if finger == 'thumb':
                    rotate_chain(world, chain, 0, np.cross(d0, palm), thumb_tuck_deg, base)
                elif finger != 'middle':
                    flat = lambda v: v - np.dot(v, palm) * palm  # noqa: E731
                    a, b = flat(d0), flat(mid_dir)
                    ang = math.degrees(math.atan2(np.dot(np.cross(a, b), palm), np.dot(a, b)))
                    rotate_chain(world, chain, 0, palm, ang * (1 - spread_keep), base)
                for j, (i, deg) in enumerate(zip(chain, angles)):
                    child = world[chain[j + 1]][:3, 3] if j + 1 < len(chain) else None
                    d = (child - world[i][:3, 3]) if child is not None else world[i][:3, 3] - world[chain[j - 1]][:3, 3]
                    d = d / np.linalg.norm(d)
                    axis = np.cross(d, palm)
                    if np.linalg.norm(axis) < 1e-6:
                        continue
                    axis /= np.linalg.norm(axis)
                    r = np.eye(4)
                    r[:3, :3] = np.array(Matrix.Rotation(math.radians(deg), 3, Vector(axis.tolist())))
                    pivot = world[i][:3, 3].copy()
                    r[:3, 3] = pivot - r[:3, :3] @ pivot
                    for k in chain[j:]:
                        world[k] = r @ world[k]
                for i in chain:
                    self.local[i] = (hand, inv_hand @ world[i])

    def apply(self, world, weight=1.0):
        for i, (hand, rel) in self.local.items():
            relaxed = world[hand] @ rel
            if weight >= 1:
                world[i] = relaxed
            else:
                q0 = Matrix(world[i].tolist()).to_quaternion()
                q1 = Matrix(relaxed.tolist()).to_quaternion()
                m = np.array(q0.slerp(q1, weight).to_matrix().to_4x4())
                m[:3, 3] = world[i][:3, 3] * (1 - weight) + relaxed[:3, 3] * weight
                world[i] = m
        return world


def _aim(m, current, wanted):
    """m turned about its own head by the smallest rotation taking the vector `current` onto `wanted`.
    Aim by the real vector to the child joint: a rig's bone axes need not point at their children."""
    q = Vector((current / np.linalg.norm(current)).tolist()).rotation_difference(
        Vector((wanted / np.linalg.norm(wanted)).tolist()))
    out = m.copy()
    out[:3, :3] = np.array(q.to_matrix()) @ m[:3, :3]
    return out


class Stance:
    """Bring the feet toward a target ankle spacing across the body (and, with max_stagger_m, closer fore and
    aft) and point the knees forward, by two-bone IK on thigh/calf; each foot keeps its animated world rotation and height. Feet already closer than
    the target are left alone. lateral is the rig's left-right axis (+X: the character's left, facing -Y)."""

    def __init__(self, rig: TargetRig, feet_apart_m=0.26, knee_forward=1.0, max_stagger_m=None,
                 pelvis_lift_m=0.0, lateral=(1.0, 0.0, 0.0), forward=(0.0, -1.0, 0.0)):
        self.rig, self.width, self.knee_forward, self.stagger = rig, feet_apart_m, knee_forward, max_stagger_m
        self.pelvis_lift = float(pelvis_lift_m)
        self.lat, self.fwd = np.array(lateral, float), np.array(forward, float)
        ix = rig.index
        self.pelvis = ix.get('pelvis')
        self.legs = []
        for s in 'lr':
            thigh, calf, foot = ix[f'thigh_{s}'], ix[f'calf_{s}'], ix[f'foot_{s}']
            l1 = np.linalg.norm(rig.rest[calf][:3, 3] - rig.rest[thigh][:3, 3])
            l2 = np.linalg.norm(rig.rest[foot][:3, 3] - rig.rest[calf][:3, 3])
            self.legs.append((s, thigh, calf, foot, l1, l2))

    def apply(self, world):
        rig = self.rig
        feet = {s: world[foot][:3, 3].copy() for s, _, _, foot, _, _ in self.legs}
        centre = (feet['l'] + feet['r']) / 2
        spread = float(np.dot(feet['l'] - feet['r'], self.lat))
        stagger = float(np.dot(feet['l'] - feet['r'], self.fwd))
        narrow = spread > self.width
        unstagger = self.stagger is not None and abs(stagger) > self.stagger
        lift = abs(self.pelvis_lift) > 1e-6
        if not (narrow or unstagger or lift):
            return world
        if lift and self.pelvis is not None:
            for i in range(len(rig.parents)):
                anc = i
                while anc not in (-1, self.pelvis):
                    anc = rig.parents[anc]
                if anc == self.pelvis:
                    world[i][2, 3] += self.pelvis_lift
        for s, thigh, calf, foot, l1, l2 in self.legs:
            sign = 1.0 if s == 'l' else -1.0
            ankle = feet[s].copy()
            if narrow:
                ankle -= self.lat * (np.dot(feet[s] - centre, self.lat) - sign * self.width / 2)
            if unstagger:
                # both feet move toward their fore-aft midpoint until they are max_stagger_m apart
                excess = (abs(stagger) - self.stagger) / 2
                ankle -= self.fwd * sign * np.sign(stagger) * excess
            hip = world[thigh][:3, 3]
            to = ankle - hip
            dist = min(np.linalg.norm(to), (l1 + l2) * 0.999)
            u = to / np.linalg.norm(to)
            # knee in the plane of the leg and the pole (forward, keeping some of the animated knee bend)
            knee_now = world[calf][:3, 3] - hip
            pole = self.fwd * self.knee_forward + (knee_now - np.dot(knee_now, u) * u) * (1 - self.knee_forward)
            pole -= np.dot(pole, u) * u
            pole /= max(np.linalg.norm(pole), 1e-9)
            a = (l1 * l1 - l2 * l2 + dist * dist) / (2 * dist)
            h = math.sqrt(max(l1 * l1 - a * a, 0.0))
            knee = hip + u * a + pole * h
            foot_rot = world[foot][:3, :3].copy()
            old_knee, old_ankle = world[calf][:3, 3].copy(), world[foot][:3, 3].copy()
            new_thigh = _aim(world[thigh], old_knee - hip, knee - hip)
            new_calf = _aim(world[calf], old_ankle - old_knee, hip + u * dist - knee)
            new_calf[:3, 3] = knee
            delta_t = new_thigh @ np.linalg.inv(world[thigh])
            delta_c = new_calf @ np.linalg.inv(world[calf])
            world[thigh] = new_thigh
            world[calf] = new_calf
            # every descendant of the calf follows it; the foot then gets its animated rotation back
            for i, p in enumerate(rig.parents):
                anc = p
                while anc not in (-1, calf, thigh):
                    anc = rig.parents[anc]
                if anc == calf and i != calf:
                    world[i] = delta_c @ world[i]
                elif anc == thigh and i != calf and i != thigh:
                    world[i] = delta_t @ world[i]
            fix = np.eye(4)
            fix[:3, :3] = foot_rot @ np.linalg.inv(world[foot][:3, :3])
            fix[:3, 3] = world[foot][:3, 3] - fix[:3, :3] @ world[foot][:3, 3]
            for i, p in enumerate(rig.parents):
                anc = i
                while anc not in (-1, foot):
                    anc = rig.parents[anc]
                if anc == foot:
                    world[i] = fix @ world[i]
        for bone, ik in IK_PINS:
            if bone in rig.index and ik in rig.index:
                world[rig.index[ik]] = world[rig.index[bone]]
        return world


class TwistBones:
    """Distribute distal joint axial X-twist (hand relative to lowerarm, foot relative to calf) across
    Manny's sibling twist bones (_twist_02 at 1/3, _twist_01 at 2/3), preventing wrist/cuff candy-wrapping
    when retargeting from open libraries (UAL) that lack twist bones."""

    def __init__(self, rig: TargetRig, frac_01=0.35, frac_02=0.18):
        self.rig = rig
        self.frac_01 = float(frac_01)
        self.frac_02 = float(frac_02)
        ix = rig.index
        self.chains = []
        for parent_prefix, child_prefix in (('lowerarm', 'hand'), ('calf', 'foot')):
            for s in 'lr':
                parent = ix.get(f'{parent_prefix}_{s}')
                child = ix.get(f'{child_prefix}_{s}')
                t1 = ix.get(f'{parent_prefix}_twist_01_{s}')
                t2 = ix.get(f'{parent_prefix}_twist_02_{s}')
                if None not in (parent, child, t1, t2):
                    self.chains.append((parent, child, t1, t2))

    def apply(self, world):
        rig = self.rig
        for parent, child, t1, t2 in self.chains:
            anim_rel = np.linalg.inv(world[parent]) @ world[child]
            basis = np.linalg.inv(rig.local_rest[child]) @ anim_rel
            _, twist = Matrix(basis[:3, :3].tolist()).to_quaternion().to_swing_twist('X')
            for ti, frac in ((t1, self.frac_01), (t2, self.frac_02)):
                rx = np.eye(4)
                rx[:3, :3] = np.array(Matrix.Rotation(twist * frac, 3, 'X'))
                world[ti] = world[parent] @ rig.local_rest[ti] @ rx
        return world

