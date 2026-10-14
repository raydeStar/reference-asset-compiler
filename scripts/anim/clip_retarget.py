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
    def __init__(self, target: TargetRig, library, bone_map, reference=None):
        self.t, self.lib = target, library
        self.ref = reference or library.reference()
        self.pairs = {target.index[tn]: sn for sn, tn in bone_map.items() if sn in self.ref and tn in target.index}
        missing = sorted(set(bone_map.values()) - set(target.names))
        assert not [m for m in missing if not m.startswith(('ball', 'spine_0'))], f'target lacks {missing}'

        def heading(world, left, right):
            v = world[left][:3, 3] - world[right][:3, 3]
            return math.atan2(v[1], v[0])
        tw = {n: target.rest[i] for i, n in enumerate(target.names)}
        yaw = heading(tw, 'upperarm_l', 'upperarm_r') - heading(self.ref, 'upperarm_l', 'upperarm_r')
        self.A = np.array(Matrix.Rotation(yaw, 3, 'Z'))
        self.scale = target.rest[target.index['pelvis'], 2, 3] / self.ref['pelvis'][2, 3]

    def _mirror(self, pose):
        """The pose reflected through the source's sagittal plane (left and right swapped)."""
        u = self.ref['upperarm_l'][:3, 3] - self.ref['upperarm_r'][:3, 3]
        u /= np.linalg.norm(u)
        S = np.eye(4)
        S[:3, :3] -= 2 * np.outer(u, u)
        p0 = np.eye(4)
        p0[:3, 3] = self.ref['pelvis'][:3, 3]
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
        self.rig, self.pelvis, self.root = rig, rig.index['pelvis'], rig.index.get('root', 0)
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
                    keep = w[self.root].copy()
                    w[:, :3, 3] += off
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


def extract_root_motion(world, rig, start_pelvis):
    """Move the pelvis's horizontal travel since frame 0 onto the root bone (and its IK children)."""
    root, pelvis = rig.index.get('root', 0), rig.index['pelvis']
    d = world[pelvis][:3, 3] - start_pelvis
    shift = np.array([d[0], d[1], 0.0])
    world[root][:3, 3] += shift
    for i, p in enumerate(rig.parents):      # ik_foot_root / ik_hand_root ride with the root
        if p == root and i != pelvis:
            world[i][:3, 3] += shift
    return world
