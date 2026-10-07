"""Re-rig an assembled character onto the UE5 Manny skeleton contract.

Inputs (all on the command line after ``--``):
  --plan      joint plan JSON from scripts/plan_ue5_joints.py (Blender metres,
              character facing -Y, left = +X), including an optional arm
              proportion remap
  --manny     Manny reference pose dumped from the local UE project
              (scripts/ue5/dump_refpose.py; Epic content, never committed)
  --template  MakeHuman hm08 template NPZ (CC0) with per-vertex skin weights
  --head-npz  the conformed head NPZ (same topology as the template)
  --out       new output directory (refused if it exists)

What it does, in order:
  1. Optionally shortens the arms along |x| with a smooth 1-D remap (T-pose
     arms lie along X), carrying custom normals with the remap's Jacobian.
  2. Builds a *skinning* armature with every deform bone pointing at its
     child joint, so Blender's bone-heat solver sees proper segments.
  3. Weights the body by inverse distance to the bone segments each vertex can
     see through a filled voxel solid of body + head. Blender's bone heat and
     its voxel remesh both fail on open, layered clothing scans (the earlier
     rig silently fell back to envelopes); the slice-filled solid does not.
  4. Re-weights hands by distance to finger segments (voxel proxies fuse
     fingers), takes the face and neck from the template's authored weights,
     and blends the body collar onto the head mesh's weights so the seam
     cannot open. Influences are capped and normalised.
  5. Builds the *export* armature: Manny's 89 bones and hierarchy with each
     bone's frame = Manny's frame rotated onto this character's joints
     (two-vector frames for the spine, legs and hands, minimum rotation for
     arms and fingers, Manny's own frame for the head and toes). Bone axes then
     match Manny, so retargeting is a pure copy of rotations.

Outputs: <out>/Ennix_UE5_Skin.blend (skinning armature, for deformation tests),
<out>/Ennix_UE5.blend (export armature named ``root``), fit-report.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector
from mathutils.kdtree import KDTree

M_UE = np.diag([1.0, -1.0, 1.0])  # Blender (x, y, z) m  <->  UE (x, -y, z) cm
P_AX = np.diag([1.0, -1.0, 1.0])  # Blender bone axes -> UE bone axes (FBX, primary Y / secondary X)

# Manny deform hierarchy children used to aim each bone.
AIM = {
    "pelvis": "spine_01", "spine_01": "spine_02", "spine_02": "spine_03", "spine_03": "spine_04",
    "spine_04": "spine_05", "spine_05": "neck_01", "neck_01": "neck_02", "neck_02": "head",
}
for s in "lr":
    AIM.update({
        f"clavicle_{s}": f"upperarm_{s}", f"upperarm_{s}": f"lowerarm_{s}", f"lowerarm_{s}": f"hand_{s}",
        f"hand_{s}": f"middle_01_{s}", f"thumb_01_{s}": f"thumb_02_{s}", f"thumb_02_{s}": f"thumb_03_{s}",
        f"thigh_{s}": f"calf_{s}", f"calf_{s}": f"foot_{s}", f"foot_{s}": f"ball_{s}",
    })
    for f in ("index", "middle", "ring", "pinky"):
        AIM.update({f"{f}_metacarpal_{s}": f"{f}_01_{s}", f"{f}_01_{s}": f"{f}_02_{s}", f"{f}_02_{s}": f"{f}_03_{s}"})
TWO_VECTOR = {"pelvis", "spine_01", "spine_02", "spine_03", "spine_04", "spine_05", "neck_01", "neck_02",
              "thigh_l", "calf_l", "foot_l", "thigh_r", "calf_r", "foot_r", "hand_l", "hand_r"}
COPY_MANNY = {"head", "ball_l", "ball_r", "root", "ik_foot_root", "ik_hand_root", "interaction", "center_of_mass"}
NON_DEFORM = {"root", "ik_foot_root", "ik_foot_l", "ik_foot_r", "ik_hand_root", "ik_hand_gun", "ik_hand_l",
              "ik_hand_r", "interaction", "center_of_mass"}
IK_COPIES = {"ik_foot_l": "foot_l", "ik_foot_r": "foot_r", "ik_hand_gun": "hand_r",
             "ik_hand_l": "hand_l", "ik_hand_r": "hand_r"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def quat_matrix(q):
    x, y, z, w = q
    return np.array(Quaternion((w, x, y, z)).to_matrix())


def frame(d, s):
    e1 = unit(d)
    e2 = unit(np.asarray(s, float) - np.dot(s, e1) * e1)
    return np.column_stack([e1, e2, np.cross(e1, e2)])


def min_rot(a, b):
    a, b = unit(a), unit(b)
    v = np.cross(a, b)
    c = float(np.dot(a, b))
    if np.linalg.norm(v) < 1e-9:
        return np.eye(3)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * (1.0 / (1.0 + c))


class ArmRemap:
    """Smooth monotone map of |x| that shortens T-pose arms segment by segment."""

    def __init__(self, spec):
        self.on = bool(spec)
        if not self.on:
            return
        src = np.array(spec["source"], float)   # e.g. [start, elbow, wrist, tip]
        dst = np.array(spec["target"], float)
        sigma = float(spec.get("blend", 0.015))
        self.grid = np.linspace(0.0, 1.4, 14001)
        rate = np.ones_like(self.grid)
        for i in range(len(src) - 1):
            seg = (self.grid >= src[i]) & (self.grid < src[i + 1])
            rate[seg] = (dst[i + 1] - dst[i]) / (src[i + 1] - src[i])
        tail = self.grid >= src[-1]
        rate[tail] = rate[np.nonzero(self.grid < src[-1])[0][-1]]
        step = self.grid[1] - self.grid[0]
        k = np.arange(-int(4 * sigma / step), int(4 * sigma / step) + 1) * step
        kern = np.exp(-0.5 * (k / sigma) ** 2)
        kern /= kern.sum()
        # Smooth only beyond the untouched shoulder so the torso never moves.
        padded = np.pad(rate, len(k) // 2, mode="edge")
        smooth = np.convolve(padded, kern, mode="valid")
        smooth[self.grid < src[0]] = 1.0
        self.rate = smooth
        self.value = np.concatenate([[0.0], np.cumsum((smooth[1:] + smooth[:-1]) * 0.5 * step)])
        self.src, self.dst = src, dst

    def u(self, a):
        return np.interp(a, self.grid, self.value) if self.on else a

    def du(self, a):
        return np.interp(a, self.grid, self.rate) if self.on else np.ones_like(a)

    def point(self, p):
        p = np.array(p, float)
        if self.on and abs(p[0]) > self.src[0]:
            p[0] = np.sign(p[0]) * self.u(abs(p[0]))
        return p


def mesh_world(ob):
    mw = np.array(ob.matrix_world)
    co = np.empty(len(ob.data.vertices) * 3)
    ob.data.vertices.foreach_get("co", co)
    return co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]


def set_mesh_world(ob, world):
    inv = np.linalg.inv(np.array(ob.matrix_world))
    local = world @ inv[:3, :3].T + inv[:3, 3]
    ob.data.vertices.foreach_set("co", local.ravel())
    ob.data.update()


def remap_arms(ob, remap, zmin):
    """Shorten arm geometry in place; returns the number of moved vertices."""
    if not remap.on:
        return 0
    me = ob.data
    loop_normals = None
    if me.has_custom_normals:
        loop_normals = np.empty(len(me.loops) * 3)
        me.corner_normals.foreach_get("vector", loop_normals)
        loop_normals = loop_normals.reshape(-1, 3)
    world = mesh_world(ob)
    ax = np.abs(world[:, 0])
    moving = (ax > remap.src[0]) & (world[:, 2] > zmin)
    new = world.copy()
    new[moving, 0] = np.sign(world[moving, 0]) * remap.u(ax[moving])
    set_mesh_world(ob, new)
    if loop_normals is not None:
        vidx = np.empty(len(me.loops), int)
        me.loops.foreach_get("vertex_index", vidx)
        g = np.where(moving[vidx], remap.du(ax[vidx]), 1.0)
        n = loop_normals.copy()
        n[:, 0] /= g  # inverse-transpose of diag(g, 1, 1)
        n /= np.linalg.norm(n, axis=1, keepdims=True)
        me.normals_split_custom_set([tuple(v) for v in n])
    return int(moving.sum())


def build_joints(plan, remap, old_rig):
    """Every Manny joint position, Blender metres, after the arm remap."""
    J = {k: np.array(v, float) for k, v in plan["joints"].items()}
    for name in list(J):
        if name.endswith("_l") and name[:-2] + "_r" not in J:
            J[name[:-2] + "_r"] = J[name] * np.array([-1.0, 1.0, 1.0])
    # Finger joints the plan lacks come from a measured hand rig, mirrored.
    if old_rig is not None:
        heads = {b.name: np.array(old_rig.matrix_world @ b.head_local) for b in old_rig.data.bones}
        for name in list(heads):
            if not name.endswith("_l") or not any(t in name for t in ("thumb", "index", "middle", "ring", "pinky")):
                continue
            r = name[:-2] + "_r"
            if r not in heads:
                continue
            left, right = heads[name], heads[r]
            avg = np.array([(left[0] - right[0]) / 2, (left[1] + right[1]) / 2, (left[2] + right[2]) / 2])
            J.setdefault(name, avg)
            J.setdefault(r, avg * np.array([-1, 1, 1]))
    for s, sign in (("l", 1.0), ("r", -1.0)):
        for base in ("clavicle", "upperarm", "lowerarm", "hand", "thigh", "calf", "foot", "ball"):
            key = f"{base}_{s}"
            if key not in J and f"{base}_l" in J:
                J[key] = J[f"{base}_l"] * np.array([sign, 1, 1])
    J = {k: remap.point(v) for k, v in J.items()}
    # Twist joints at Manny's thirds (01 nearest the shoulder/hip, the forearm and
    # calf count from the far end, exactly as Manny does).
    for s in "lr":
        a, b = J[f"upperarm_{s}"], J[f"lowerarm_{s}"]
        J[f"upperarm_twist_01_{s}"], J[f"upperarm_twist_02_{s}"] = a + (b - a) / 3, a + 2 * (b - a) / 3
        a, b = J[f"lowerarm_{s}"], J[f"hand_{s}"]
        J[f"lowerarm_twist_02_{s}"], J[f"lowerarm_twist_01_{s}"] = a + (b - a) / 3, a + 2 * (b - a) / 3
        a, b = J[f"thigh_{s}"], J[f"calf_{s}"]
        J[f"thigh_twist_01_{s}"], J[f"thigh_twist_02_{s}"] = a + (b - a) / 3, a + 2 * (b - a) / 3
        a, b = J[f"calf_{s}"], J[f"foot_{s}"]
        J[f"calf_twist_02_{s}"], J[f"calf_twist_01_{s}"] = a + (b - a) / 3, a + 2 * (b - a) / 3
    for name, src in IK_COPIES.items():
        J[name] = J[src].copy()
    for name in ("root", "ik_foot_root", "ik_hand_root", "interaction", "center_of_mass"):
        J[name] = np.zeros(3)
    return J


def solve_frames(manny, J):
    """Each bone's UE component-space rotation for this character."""
    mb = {b["name"]: b for b in manny["bones"]}
    Pm = {n: np.array(b["pos"], float) for n, b in mb.items()}
    Rm = {n: quat_matrix(b["quat"]) for n, b in mb.items()}
    Pe = {n: M_UE @ J[n] * 100.0 for n in mb}
    Re = {}
    lateral = np.array([1.0, 0.0, 0.0])
    order = []

    def visit(n):
        if n in order:
            return
        p = mb[n]["parent"]
        if p:
            visit(p)
        order.append(n)

    for n in mb:
        visit(n)
    for n in order:
        p = mb[n]["parent"]
        delta = Re[p] @ Rm[p].T if p else np.eye(3)
        if n in IK_COPIES:
            Re[n] = Re[IK_COPIES[n]]  # Manny's IK bones carry their limb's rotation
            continue
        if n in COPY_MANNY:
            Re[n] = Rm[n]
        elif n in TWO_VECTOR:
            c = AIM[n]
            if n.startswith("hand_"):
                s = n[-1]
                sm = Pm[f"pinky_01_{s}"] - Pm[f"index_01_{s}"]
                se = Pe[f"pinky_01_{s}"] - Pe[f"index_01_{s}"]
            else:
                sm = se = lateral
            Fm = frame(Pm[c] - Pm[n], sm)
            Fe = frame(Pe[c] - Pe[n], se)
            Re[n] = Fe @ Fm.T @ Rm[n]
        elif n in AIM:
            c = AIM[n]
            transported = delta @ Rm[n]
            dm = delta @ (Pm[c] - Pm[n])
            Re[n] = min_rot(dm, Pe[c] - Pe[n]) @ transported
        else:
            Re[n] = delta @ Rm[n]  # twist bones and finger tips ride their parent
    return order, Pe, Re, Rm


def build_export_armature(manny, order, J, Re):
    data = bpy.data.armatures.new("ue5_manny")
    rig = bpy.data.objects.new("root", data)  # FBX turns the object into the root bone
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    parents = {b["name"]: b["parent"] for b in manny["bones"]}
    ebs = {}
    for n in order:
        if n == "root":
            continue
        eb = data.edit_bones.new(n)
        Bm = M_UE @ Re[n] @ P_AX
        mat = Matrix(Bm.tolist()).to_4x4()
        mat.translation = Vector(J[n])
        eb.head = Vector(J[n])
        eb.tail = Vector(J[n]) + Vector((0, 0, 0.05))
        eb.matrix = mat
        eb.length = 0.04 if n.startswith(("index", "middle", "ring", "pinky", "thumb")) else 0.08
        ebs[n] = eb
    for n, eb in ebs.items():
        p = parents[n]
        if p and p != "root":
            eb.parent = ebs[p]
        eb.use_deform = n not in NON_DEFORM
    bpy.ops.object.mode_set(mode="OBJECT")
    return rig


def build_skin_armature(manny, J):
    data = bpy.data.armatures.new("ue5_skin")
    rig = bpy.data.objects.new("SkinRig", data)
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    parents = {b["name"]: b["parent"] for b in manny["bones"]}
    ebs = {}
    for b in manny["bones"]:
        n = b["name"]
        if n in NON_DEFORM:
            continue
        head = Vector(J[n])
        child = AIM.get(n)
        if n.startswith(("upperarm_", "thigh_")) and "twist" not in n:
            child = n.replace("upperarm", "upperarm_twist_01").replace("thigh", "thigh_twist_01")
        tail = None
        if child:
            tail = Vector(J[child])
        if n == "pelvis":
            # Heat flows from the segment: aim the pelvis down through the hips
            # so the seat and groin follow it rather than the thighs.
            tail = head + Vector((0, 0, -0.11))
        twist_next = {"upperarm_twist_01": "upperarm_twist_02", "upperarm_twist_02": "lowerarm",
                      "thigh_twist_01": "thigh_twist_02", "thigh_twist_02": "calf",
                      "lowerarm_twist_02": "lowerarm_twist_01", "lowerarm_twist_01": "hand",
                      "calf_twist_02": "calf_twist_01", "calf_twist_01": "foot"}
        for key, nxt in twist_next.items():
            if n.startswith(key + "_"):
                tail = Vector(J[nxt + n[-2:]])
        if n.startswith(("lowerarm_", "calf_")) and "twist" not in n:
            tail = Vector(J[n.replace("lowerarm", "lowerarm_twist_02").replace("calf", "calf_twist_02")])
        if tail is None:
            p = parents[n]
            direction = (head - Vector(J[p])).normalized() if p and p in J else Vector((0, 0, 1))
            if n == "head":
                tail = head + Vector((0, 0, 0.17))
            elif n.startswith("ball_"):
                tail = head + Vector((0, -0.07, 0))
            else:
                tail = head + direction * 0.022
        eb = data.edit_bones.new(n)
        eb.head, eb.tail = head, tail
        ebs[n] = eb
    for n, eb in ebs.items():
        p = parents[n]
        if p in ebs:
            eb.parent = ebs[p]
    bpy.ops.object.mode_set(mode="OBJECT")
    return rig


FINGERS = ("thumb", "index", "middle", "ring", "pinky")


def _shift_or(a, axis, step):
    out = a.copy()
    sl_dst = [slice(None)] * 3
    sl_src = [slice(None)] * 3
    if step > 0:
        sl_dst[axis], sl_src[axis] = slice(step, None), slice(None, -step)
    else:
        sl_dst[axis], sl_src[axis] = slice(None, step), slice(-step, None)
    out[tuple(sl_dst)] |= a[tuple(sl_src)]
    return out


def _flood(free, axes):
    """Voxels of ``free`` reachable from the grid border, moving only along ``axes``."""
    seed = np.zeros_like(free)
    for ax in axes:
        lo = [slice(None)] * 3
        hi = [slice(None)] * 3
        lo[ax], hi[ax] = 0, -1
        seed[tuple(lo)] = True
        seed[tuple(hi)] = True
    reach = seed & free
    while True:
        grow = reach
        for ax in axes:
            grow = _shift_or(_shift_or(grow, ax, 1), ax, -1)
        grow &= free
        if np.array_equal(grow, reach):
            return reach
        reach = grow


class VoxelSolid:
    """A filled occupancy grid of scanned clothing that is not watertight.

    Surfaces are sampled into a shell (dilated one voxel to seal small gaps),
    then the inside is everything the outside cannot reach: in 3-D, and in
    every horizontal and every sagittal slice, so open jacket hems, cuffs and
    collars still enclose the body they wrap.
    """

    def __init__(self, objs, h):
        pts = np.concatenate([surface_samples(o, 0.45 * h) for o in objs])
        self.h = h
        self.lo = pts.min(0) - 3 * h
        dims = np.ceil((pts.max(0) + 3 * h - self.lo) / h).astype(int) + 1
        shell = np.zeros(dims, bool)
        idx = np.floor((pts - self.lo) / h).astype(int)
        shell[idx[:, 0], idx[:, 1], idx[:, 2]] = True
        for ax in range(3):
            shell = _shift_or(_shift_or(shell, ax, 1), ax, -1)
        free = ~shell
        inside = free & ~_flood(free, (0, 1, 2))
        for axes in ((0, 1), (1, 2)):
            inside |= free & ~_flood(free, axes)
        self.occ = shell | inside
        self.stats = {"voxel_m": h, "dims": dims.tolist(), "shell": int(shell.sum()),
                      "inside": int(inside.sum()), "surface_samples": int(len(pts))}

    def lookup(self, pts):
        idx = np.floor((pts - self.lo) / self.h).astype(int)
        for ax in range(3):
            np.clip(idx[..., ax], 0, self.occ.shape[ax] - 1, out=idx[..., ax])
        return self.occ[idx[..., 0], idx[..., 1], idx[..., 2]]


def surface_samples(ob, step):
    me = ob.data
    me.calc_loop_triangles()
    tri = np.empty(len(me.loop_triangles) * 3, int)
    me.loop_triangles.foreach_get("vertices", tri)
    tri = tri.reshape(-1, 3)
    P = mesh_world(ob)
    A, B, C = P[tri[:, 0]], P[tri[:, 1]], P[tri[:, 2]]
    longest = np.max([np.linalg.norm(B - A, axis=1), np.linalg.norm(C - B, axis=1),
                      np.linalg.norm(A - C, axis=1)], axis=0)
    n = np.clip(np.ceil(longest / step), 1, 40).astype(int)
    out = [P]
    for k in np.unique(n):
        sel = n == k
        ij = np.array([(i, j) for i in range(k + 1) for j in range(k + 1 - i)], float) / k
        u, v = ij[:, 0], ij[:, 1]
        out.append((A[sel, None] * (1 - u - v)[None, :, None] + B[sel, None] * u[None, :, None]
                    + C[sel, None] * v[None, :, None]).reshape(-1, 3))
    return np.concatenate(out)


def visible_idw(P, segs, solid, col, nbones, power=4.0, k=10, samples=16):
    """Inverse-distance weights to bone segments the vertex can see through the solid."""
    H = np.array([s[1] for s in segs])
    T = np.array([s[2] for s in segs])
    cols = np.array([col[s[0]] for s in segs])
    AB = T - H
    L2 = np.maximum((AB * AB).sum(1), 1e-12)
    ts = np.linspace(0.0, 1.0, samples)
    W = np.zeros((len(P), nbones), np.float32)
    blind = 0
    for c0 in range(0, len(P), 3000):
        Q = P[c0:c0 + 3000]
        t = np.clip(((Q[:, None, :] - H[None]) * AB[None]).sum(-1) / L2[None], 0, 1)
        Cp = H[None] + t[..., None] * AB[None]
        D = np.linalg.norm(Q[:, None, :] - Cp, axis=-1)
        nn = np.argsort(D, axis=1)[:, :k]
        Cn = np.take_along_axis(Cp, nn[..., None], 1)
        Dn = np.take_along_axis(D, nn, 1)
        pts = Q[:, None, None, :] + ts[None, None, :, None] * (Cn[:, :, None, :] - Q[:, None, None, :])
        inside = solid.lookup(pts)
        near_vertex = (ts[None, None, :] * Dn[..., None]) < 1.5 * solid.h
        vis = (inside | near_vertex).mean(-1) >= 0.9
        w = 1.0 / np.maximum(Dn, 0.01) ** power
        none = ~vis.any(1)
        blind += int(none.sum())
        w = np.where(vis | none[:, None], w, 0.0)
        rows = np.arange(len(Q))[:, None].repeat(k, 1)
        np.add.at(W, (c0 + rows, cols[nn]), w)
    W /= W.sum(1, keepdims=True)
    return W, blind


def read_weights(ob, names):
    col = {n: i for i, n in enumerate(names)}
    W = np.zeros((len(ob.data.vertices), len(names)), np.float32)
    gi = {g.index: col.get(g.name) for g in ob.vertex_groups}
    for v in ob.data.vertices:
        for g in v.groups:
            j = gi.get(g.group)
            if j is not None:
                W[v.index, j] = g.weight
    return W


def write_weights(ob, W, names, cap):
    ob.vertex_groups.clear()
    groups = [ob.vertex_groups.new(name=n) for n in names]
    top = np.argsort(-W, axis=1)[:, :cap]
    for vi in range(W.shape[0]):
        idx = top[vi]
        w = W[vi, idx]
        keep = w > 1e-4
        if not keep.any():
            raise RuntimeError(f"Unweighted vertex {ob.name}:{vi}")
        w = w[keep] / w[keep].sum()
        for j, wt in zip(idx[keep], w):
            groups[j].add([vi], float(wt), "REPLACE")


def segment_distance(P, a, b):
    ab = b - a
    t = np.clip(((P - a) @ ab) / max(float(ab @ ab), 1e-12), 0, 1)
    return np.linalg.norm(P - (a + t[:, None] * ab), axis=1)


def smooth_weights(ob, W, iterations, mask=None):
    me = ob.data
    e = np.empty(len(me.edges) * 2, int)
    me.edges.foreach_get("vertices", e)
    e = e.reshape(-1, 2)
    n = len(me.vertices)
    for _ in range(iterations):
        acc = np.zeros_like(W)
        cnt = np.zeros(n)
        np.add.at(acc, e[:, 0], W[e[:, 1]])
        np.add.at(acc, e[:, 1], W[e[:, 0]])
        np.add.at(cnt, e[:, 0], 1)
        np.add.at(cnt, e[:, 1], 1)
        avg = np.where(cnt[:, None] > 0, acc / np.maximum(cnt, 1)[:, None], W)
        new = 0.5 * W + 0.5 * avg
        W = np.where(mask[:, None], new, W) if mask is not None else new
    return W


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    p = argparse.ArgumentParser()
    p.add_argument("--plan", required=True)
    p.add_argument("--manny", required=True)
    p.add_argument("--template")
    p.add_argument("--head-npz")
    p.add_argument("--name", default="Ennix")
    p.add_argument("--out", required=True)
    p.add_argument("--voxel", type=float, default=0.01)
    p.add_argument("--cap", type=int, default=4)
    a = p.parse_args(argv)
    out = Path(a.out).resolve()
    if out.exists():
        raise RuntimeError("Choose a new output directory; earlier fits are evidence.")
    out.mkdir(parents=True)
    plan = json.loads(Path(a.plan).read_text())
    manny = json.loads(Path(a.manny).read_text())
    remap = ArmRemap(plan.get("arm_remap"))
    report = {"inputs": {k: {"path": str(Path(v).resolve()), "sha256": sha(v)} for k, v in
                         (("blend", bpy.data.filepath), ("plan", a.plan), ("manny", a.manny),
                          ("template", a.template), ("head_npz", a.head_npz)) if v},
              "blender": bpy.app.version_string}

    old_rig = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    body = bpy.data.objects[plan.get("body_object") or max(meshes, key=lambda o: len(o.data.vertices)).name]
    head = bpy.data.objects.get(plan.get("head_object") or "")
    groom = next((o for o in bpy.data.objects if o.type == "CURVES"), None)
    for ob in meshes + ([groom] if groom else []):
        world = ob.matrix_world.copy()
        ob.parent = None
        ob.matrix_world = world
        for m in [m for m in ob.modifiers if m.type == "ARMATURE"]:
            ob.modifiers.remove(m)
        if ob.type == "MESH":
            ob.vertex_groups.clear()
    J = build_joints(plan, remap, old_rig)
    if old_rig:
        bpy.data.objects.remove(old_rig, do_unlink=True)
    report["arm_vertices_moved"] = remap_arms(body, remap, plan.get("arm_zmin", 1.1))
    report["arm_remap"] = plan.get("arm_remap")

    order, Pe, Re, Rm = solve_frames(manny, J)
    deform = [b["name"] for b in manny["bones"] if b["name"] not in NON_DEFORM]

    # --- weights -----------------------------------------------------------
    skin = build_skin_armature(manny, J)
    solid = VoxelSolid([body, head], a.voxel)
    report["solid"] = solid.stats
    col = {n: i for i, n in enumerate(deform)}
    skin_segs = [(b.name, np.array(skin.matrix_world @ b.head_local), np.array(skin.matrix_world @ b.tail_local))
                 for b in skin.data.bones]

    # Body: visible inverse-distance weights, hands by finger segments, smoothing.
    Pb = mesh_world(body)
    Wb, blind = visible_idw(Pb, [s for s in skin_segs if not s[0].startswith(FINGERS) and
                                  "metacarpal" not in s[0]], solid, col, len(deform))
    report["body_vertices_without_visible_bone"] = blind
    hand_bones = {}
    for s in "lr":
        names = [f"hand_{s}"] + [n for n in deform if n.endswith(f"_{s}") and
                                  n.split("_")[0] in ("thumb", "index", "middle", "ring", "pinky")]
        segs = []
        for n in names:
            child = AIM.get(n)
            tip = J[child] if child else J[n] + (J[n] - J[manny_parent(manny, n)]) * 0.9
            segs.append((n, J[n], tip))
        segs.append((f"lowerarm_twist_01_{s}", J[f"lowerarm_twist_01_{s}"], J[f"hand_{s}"]))
        hand_bones[s] = segs
        sign = 1 if s == "l" else -1
        wrist = abs(J[f"hand_{s}"][0])
        sel = (sign * Pb[:, 0] > wrist - 0.03) & (Pb[:, 2] > J["hand_l"][2] - 0.15)
        if not sel.any():
            continue
        D = np.column_stack([segment_distance(Pb[sel], h, t) for _, h, t in segs])
        Wfing = 1.0 / np.maximum(D, 0.003) ** 6
        Wfing /= Wfing.sum(1, keepdims=True)
        Wn = np.zeros((sel.sum(), len(deform)), np.float32)
        for j, (n, _, _) in enumerate(segs):
            Wn[:, col[n]] += Wfing[:, j]
        blend = np.clip((sign * Pb[sel, 0] - (wrist - 0.03)) / 0.03, 0, 1)[:, None]
        Wb[sel] = (1 - blend) * Wb[sel] + blend * Wn
    hand_mask = (np.abs(Pb[:, 0]) > abs(J["hand_l"][0]) - 0.03) & (Pb[:, 2] > J["hand_l"][2] - 0.15)
    Wb = smooth_weights(body, Wb, 4, mask=~hand_mask)

    if head is None:
        Wh = None
    elif a.template and a.head_npz:
        Wh = template_head_weights(a.template, a.head_npz, head, J, col, len(deform), report)
    else:
        # No template: the head is weighted like the body, then smoothed.
        Wh, _ = visible_idw(mesh_world(head), [s for s in skin_segs if not s[0].startswith(FINGERS)],
                            solid, col, len(deform))
        Wh = smooth_weights(head, Wh, 4)
    if Wh is not None:
        # Body collar: match the head mesh exactly at the seam, fade over 4 cm.
        Ph = mesh_world(head)
        htree = KDTree(len(Ph))
        for i, co in enumerate(Ph):
            htree.insert(co, i)
        htree.balance()
        near = [htree.find(co) for co in Pb]
        dist = np.array([n[2] for n in near])
        nidx = np.array([n[1] for n in near])
        t = np.clip(dist / 0.04, 0, 1)
        t = t * t * (3 - 2 * t)
        seam = dist < 0.04
        Wb[seam] = (1 - t[seam, None]) * Wh[nidx[seam]] + t[seam, None] * Wb[seam]

    write_weights(body, Wb, deform, a.cap)
    if Wh is not None:
        write_weights(head, Wh, deform, a.cap)
    rigid = np.zeros(len(deform), np.float32)
    rigid[col["head"]] = 1.0
    for ob in meshes:
        if ob is not body and ob is not head:
            write_weights(ob, np.tile(rigid, (len(ob.data.vertices), 1)), deform, 1)

    def bind(ob, rig):
        for m in [m for m in ob.modifiers if m.type == "ARMATURE"]:
            ob.modifiers.remove(m)
        mod = ob.modifiers.new("Armature", "ARMATURE")
        mod.object = rig
        while ob.modifiers[0] != mod:
            bpy.context.view_layer.objects.active = ob
            bpy.ops.object.modifier_move_up(modifier=mod.name)
        world = ob.matrix_world.copy()
        ob.parent = rig
        ob.matrix_world = world

    def attach_groom(rig):
        if groom:
            world = groom.matrix_world.copy()
            groom.parent = rig
            groom.parent_type = "BONE"
            groom.parent_bone = "head"
            bpy.context.view_layer.update()
            groom.matrix_world = world

    for ob in meshes:
        bind(ob, skin)
    attach_groom(skin)
    bpy.ops.wm.save_as_mainfile(filepath=str(out / f"{a.name}_UE5_Skin.blend"))

    # --- export armature with Manny's bone axes ---------------------------
    export = build_export_armature(manny, order, J, Re)
    for ob in meshes:
        bind(ob, export)
    attach_groom(export)
    bpy.data.objects.remove(skin, do_unlink=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out / f"{a.name}_UE5.blend"))

    # --- report ------------------------------------------------------------
    angles = {}
    for n in order:
        if n in Rm and n in Re:
            d = Re[n] @ Rm[n].T
            angles[n] = round(float(np.degrees(np.arccos(np.clip((np.trace(d) - 1) / 2, -1, 1)))), 2)
    report.update({
        "joints_m": {k: [round(float(x), 5) for x in v] for k, v in J.items()},
        "ue_component": {n: {"pos_cm": [round(float(x), 4) for x in Pe[n]],
                             "quat_xyzw": quat_xyzw(Re[n])} for n in order},
        "delta_from_manny_deg": angles,
        "deform_bones": len(deform), "bone_count": len(order),
        "influence_cap": a.cap,
        "outputs": {"skin_blend": str(out / f"{a.name}_UE5_Skin.blend"), "export_blend": str(out / f"{a.name}_UE5.blend")},
    })
    (out / "fit-report.json").write_text(json.dumps(report, indent=1))
    print("UE5 FIT DONE", out)


def template_head_weights(template, head_npz, head, J, col, nbones, report):
    """The MakeHuman template's authored weights, mapped onto Manny's two neck bones."""
    tmpl = np.load(template)
    hnpz = np.load(head_npz)
    hw = head.matrix_world
    tworld = hnpz["verts"] * np.array(hw.to_scale()) + np.array(hw.translation)
    Ph = mesh_world(head)
    ttree = KDTree(len(tworld))
    for i, co in enumerate(tworld):
        ttree.insert(co, i)
    ttree.balance()
    match = [ttree.find(co) for co in Ph]
    report["head_template_match_max_m"] = float(max(m[2] for m in match))
    TW = tmpl["weights"][np.array([m[1] for m in match])]
    tnames = [str(n) for n in tmpl["bone_names"]]
    Wh = np.zeros((len(Ph), nbones), np.float32)
    n1, hd = J["neck_01"][2], J["head"][2]
    for j, tn in enumerate(tnames):
        w = TW[:, j]
        if not w.any():
            continue
        if tn == "neck_01":
            t = np.clip((Ph[:, 2] - n1) / (hd - n1), 0, 1)
            Wh[:, col["neck_01"]] += w * (1 - t)
            Wh[:, col["neck_02"]] += w * t
        elif tn in col:
            Wh[:, col[tn]] += w
        elif tn.startswith("spine_"):
            Wh[:, col["spine_05"]] += w
        else:
            Wh[:, col["head"]] += w
    return Wh / np.maximum(Wh.sum(1, keepdims=True), 1e-8)


def quat_xyzw(R):
    q = Matrix(R.tolist()).to_quaternion().normalized()
    return [round(q.x, 6), round(q.y, 6), round(q.z, 6), round(q.w, 6)]


def manny_parent(manny, n):
    return next(b["parent"] for b in manny["bones"] if b["name"] == n)


if __name__ == "__main__":
    main()
