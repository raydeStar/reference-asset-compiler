"""Give a long coat its own bones: add coat-tail chains to a UE5 blend, skin the coat, export the FBX.

  blender -b <Name>_UE5.blend --factory-startup --python add_coat_chains.py -- \
      <out.fbx> --profile <character.json> [--receipt <out.coat.json>] [--outfit OBJECT] \
      [--save-blend <coated.blend>]

The input is the UE5 rig stage's Manny-conformant blend (rig_ue5_character.py's
fit/<Name>_UE5.blend); it is never saved over. The profile's `coat` block
(scripts/coat_profile.py, which documents every key and default) says where
the chains hang:

- Placement. Each chain sits at its angle around the body (0 = straight ahead,
  -Y; positive toward the character's left, +X). A ray cast outward from the
  body's vertical axis (through the pelvis joint) at the root height (just
  under the belt) finds the outfit's outermost surface; another at the hem
  height finds the hem. Only lower-body faces count (weighted mostly to
  pelvis, spine_01, thigh, calf, foot or ball), so hanging arms are never hit.
  A hem ray that misses, or only finds a trouser leg (a hit within
  leg_clearance_m of a leg axis), is retried 2.5 and 5 cm higher; then the
  chain hangs straight down from its root. The receipt says which.
- Bones. coat_<group>_01_<side> .. _<NN>_<side> parented pelvis -> 01 -> 02 ...,
  plus a non-deforming coat_<group>_end_<side> leaf at the hem. Blender bone X
  runs along the chain toward the child (UE maps Blender bone axes as
  diag(1, -1, 1), so in UE every coat bone's child sits on +X, both sides, no
  mirroring); Z is the outward normal of the coat (the horizontal radial
  direction, made square to X); tails are the same 8 cm +Y stubs as the fitted
  Manny bones.
- Skin. Coat vertices are outfit vertices that are lower-body (as above), no
  lower than one segment below the hem, and stand off the legs: further than
  leg_clearance_m from the nearest thigh/calf/foot axis, fully coat 3 cm
  beyond. Down the coat a vertex hands over from its own (pelvis/thigh)
  weights to the chains over top_blend_m below the roots; along a chain it
  blends between neighbouring bones at the joints; around the body between
  the two chains either side of it by angle (smoothstep), never across the
  front centre line when open_front. Results keep the strongest four
  influences (the skeleton gate's and UE's limit) and are normalized. Every
  other vertex, and every other mesh, keeps its weights exactly.
- Export. export_ue5_character.py itself runs on the coated scene, so the FBX
  has the pipeline's settings (centimetres, add_leaf_bones=False, ...) and its
  provenance JSON (<out>.json). The receipt (<out stem>.coat.json by default)
  records the chains, bone positions, coat vertex count and weights.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import re
import runpy
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

HERE = Path(__file__).resolve().parent
LOWER_BODY = re.compile(r"^(pelvis|spine_01|thigh_.*|calf_.*|foot_.*|ball_.*)$")
CLEARANCE_RAMP_M = 0.03
HEM_RETRIES_M = (0.0, 0.025, 0.05)
MAX_INFLUENCES = 4
STUB_M = 0.08


def load_coat_profile():
    spec = importlib.util.spec_from_file_location("rac_coat_profile", HERE.parent / "coat_profile.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:]
    p = argparse.ArgumentParser(prog="add_coat_chains.py")
    p.add_argument("out", help="coated FBX (first after --: export_ue5_character.py reads it there)")
    p.add_argument("--profile", required=True, help="character profile with a coat block")
    p.add_argument("--receipt", help="default: <out stem>.coat.json")
    p.add_argument("--outfit", help="the outfit mesh object (default: the skinned mesh with most lower-body vertices)")
    p.add_argument("--save-blend", help="also save the coated scene (metres, before export) as this blend")
    return p.parse_args(argv)


def world_head(arm, name):
    bone = arm.data.bones.get(name)
    return None if bone is None else arm.matrix_world @ bone.head_local


def segment_distance(points, a, b):
    ab = b - a
    t = np.clip(((points - a) @ ab) / max(float(ab @ ab), 1e-12), 0.0, 1.0)
    return np.linalg.norm(points - (a + t[:, None] * ab), axis=1)


def leg_segments(arm):
    segments = []
    for side in ("l", "r"):
        joints = [world_head(arm, n + "_" + side) for n in ("thigh", "calf", "foot", "ball")]
        joints = [np.array(j) for j in joints if j is not None]
        if len(joints) >= 2 and "ball_" + side in arm.data.bones and "foot_" + side in arm.data.bones:
            joints.append(joints[-1] + (joints[-1] - joints[-2]) * 0.6)   # toward the toe tip
        segments += list(zip(joints[:-1], joints[1:]))
    return segments


def farthest_hit(tree, origin, direction, reach=1.5):
    last, start = None, Vector(origin)
    for _ in range(256):
        hit = tree.ray_cast(start, direction, reach)
        if hit[0] is None:
            break
        last = hit[0]
        start = hit[0] + direction * 1e-4
    return last


def angular_weights(az, angles, open_front):
    """(vertices, chains) weights around the body: the two chains either side, smoothstep between."""
    order = np.argsort(np.mod(angles, 360.0))
    weights = np.zeros((len(az), len(angles)))
    if len(angles) == 1:
        weights[:, 0] = 1.0
        return weights
    for k, i in enumerate(order):
        j = order[(k + 1) % len(order)]
        arc = np.mod(angles[j] - angles[i], 360.0) or 360.0
        offset = np.mod(az - angles[i], 360.0)
        inside = offset < arc
        to_front = np.mod(0.0 - angles[i], 360.0)
        if open_front and 0.0 < to_front < arc:
            # The opening lies between these chains: each side follows its own chain.
            weights[inside & (offset <= to_front), i] = 1.0
            weights[inside & (offset > to_front), j] = 1.0
        else:
            u = smoothstep(offset[inside] / arc)
            weights[inside, i] += 1.0 - u
            weights[inside, j] += u
    return weights


def along_weights(s, n):
    """(vertices, n) weights along a chain at s bones below the root: each bone owns its middle."""
    weights = np.zeros((len(s), n))
    x = np.clip(s, 0.0, float(n)) - 0.5
    lower = np.floor(x).astype(int)
    u = smoothstep(x - lower)
    rows = np.arange(len(s))
    a, b = np.clip(lower, 0, n - 1), np.clip(lower + 1, 0, n - 1)
    np.add.at(weights, (rows, a), 1.0 - u)
    np.add.at(weights, (rows, b), u)
    return weights


def main():
    args = parse_args()
    out = Path(args.out).resolve()
    receipt_path = Path(args.receipt).resolve() if args.receipt else out.with_suffix(".coat.json")
    profile_path = Path(args.profile).resolve()
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    coat_profile = load_coat_profile()
    coat = coat_profile.resolve_coat(profile.get("coat"))
    if coat is None:
        raise SystemExit("{0} has no coat block; nothing to add.".format(profile_path))

    armatures = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
    arm = next((o for o in armatures if o.name == "root"), armatures[0] if armatures else None)
    if arm is None:
        raise SystemExit("No armature in the blend.")
    for name in ("pelvis", "thigh_l", "thigh_r", "calf_l", "calf_r"):
        if name not in arm.data.bones:
            raise SystemExit("The armature has no {0}; is this a Manny-conformant UE5 blend?".format(name))
    if any(b.name.startswith("coat_") for b in arm.data.bones):
        raise SystemExit("The armature already has coat bones; start from the uncoated blend.")
    pelvis = world_head(arm, "pelvis")
    knee_z = (world_head(arm, "calf_l").z + world_head(arm, "calf_r").z) / 2.0
    nb = coat["bones_per_chain"]
    top_z = pelvis.z - coat["top_below_pelvis_m"]
    hem_z = coat["hem_z_m"] if coat["hem_z_m"] is not None else knee_z + coat["hem_above_knee_m"]
    if hem_z > top_z - 0.05:
        raise SystemExit("The hem ({0:.3f} m) must be well below the chain roots ({1:.3f} m).".format(hem_z, top_z))
    seg = (top_z - hem_z) / nb
    floor_z = hem_z - seg
    blend_len = coat["top_blend_m"] or seg
    axis = np.array([pelvis.x, pelvis.y])

    # Every skinned mesh: world positions and weights on bone-named groups.
    bone_set = {b.name for b in arm.data.bones}
    skinned = [o for o in bpy.context.scene.objects if o.type == "MESH" and any(
        m.type == "ARMATURE" and m.object == arm for m in o.modifiers)]

    def lower_body_share(obj):
        names = [g.name for g in obj.vertex_groups]
        share = np.zeros(len(obj.data.vertices))
        for v in obj.data.vertices:
            for g in v.groups:
                if LOWER_BODY.match(names[g.group]):
                    share[v.index] += g.weight
        return share

    def world_positions(obj):
        co = np.empty(len(obj.data.vertices) * 3)
        obj.data.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        mw = np.array(obj.matrix_world)
        return co @ mw[:3, :3].T + mw[:3, 3]

    if args.outfit:
        outfit = bpy.data.objects.get(args.outfit)
        if outfit is None or outfit.type != "MESH":
            raise SystemExit("No mesh object named {0!r}.".format(args.outfit))
    else:
        def band_count(obj):
            z = world_positions(obj)[:, 2]
            return int(((z >= floor_z) & (z <= top_z) & (lower_body_share(obj) >= 0.5)).sum())
        outfit = max(skinned, key=band_count, default=None)
        if outfit is None:
            raise SystemExit("No mesh is skinned to the armature.")
    me = outfit.data
    pos = world_positions(outfit)
    nv = len(pos)
    group_names = [g.name for g in outfit.vertex_groups]
    bone_groups = [i for i, n in enumerate(group_names) if n in bone_set]
    column = {gi: c for c, gi in enumerate(bone_groups)}
    original = np.zeros((nv, len(bone_groups)))
    for v in me.vertices:
        for g in v.groups:
            if g.group in column:
                original[v.index, column[g.group]] = g.weight
    lower = np.zeros(nv)
    for c, gi in enumerate(bone_groups):
        if LOWER_BODY.match(group_names[gi]):
            lower += original[:, c]
    lower_body = lower >= 0.5

    # Place the chains on the garment.
    polys = [tuple(p.vertices) for p in me.polygons if all(lower_body[i] for i in p.vertices)]
    if not polys:
        raise SystemExit("{0} has no lower-body faces to hang a coat on.".format(outfit.name))
    tree = BVHTree.FromPolygons([Vector(p) for p in pos], polys)

    legs = leg_segments(arm)

    def leg_distance(points):
        d = np.full(len(points), np.inf)
        for a, b in legs:
            d = np.minimum(d, segment_distance(points, a, b))
        return d

    def radius_at(direction, z, off_the_legs=False):
        hit = farthest_hit(tree, Vector((axis[0], axis[1], z)), direction)
        if hit is None or (off_the_legs and leg_distance(np.array([hit]))[0] < coat["leg_clearance_m"]):
            return None
        return float(np.hypot(hit.x - axis[0], hit.y - axis[1]))

    chains = []
    for chain, degrees in coat["chains"].items():
        a = math.radians(degrees)
        radial = Vector((math.sin(a), -math.cos(a), 0.0))
        r_top = radius_at(radial, top_z)
        if r_top is None:
            raise SystemExit("Chain {0}: no garment {1:.0f} degrees round the body at the roots' height "
                             "({2:.3f} m).".format(chain, degrees, top_z))
        r_hem, hem_ray_z = None, None
        for lift in HEM_RETRIES_M:
            r_hem = radius_at(radial, hem_z + lift, off_the_legs=True)   # a trouser leg is not the hem
            if r_hem is not None:
                hem_ray_z = hem_z + lift
                break
        if r_hem is None:
            r_hem = r_top
        joints = []
        for k in range(nb + 1):
            t = k / nb
            r = r_top + (r_hem - r_top) * t
            joints.append(Vector((axis[0] + radial.x * r, axis[1] + radial.y * r, top_z + (hem_z - top_z) * t)))
        chains.append({"chain": chain, "degrees": degrees, "radial": radial, "joints": joints,
                       "names": coat_profile.bone_names(chain, nb), "radius_top_m": r_top, "radius_hem_m": r_hem,
                       "hem_ray_z_m": hem_ray_z})

    bpy.context.view_layer.objects.active = arm
    arm.hide_set(False)
    arm.hide_viewport = False
    bpy.ops.object.mode_set(mode="EDIT")
    edit = arm.data.edit_bones
    inv = arm.matrix_world.inverted()
    for c in chains:
        parent, joints = edit["pelvis"], c["joints"]
        for i, name in enumerate(c["names"]):
            head = joints[i]
            down = (joints[i + 1] - head) if i < nb else (joints[nb] - joints[nb - 1])
            down.normalize()
            z_axis = (c["radial"] - c["radial"].project(down)).normalized()
            y_axis = z_axis.cross(down).normalized()
            m = Matrix((down, y_axis, z_axis)).transposed().to_4x4()
            m.translation = head
            bone = edit.new(name)
            bone.head = inv @ head
            bone.tail = inv @ (head + y_axis * STUB_M)
            bone.matrix = inv @ m
            bone.length = STUB_M
            bone.parent = parent
            bone.use_connect = False
            bone.use_deform = i < nb
            parent = bone
    bpy.ops.object.mode_set(mode="OBJECT")

    # Skin the coat.
    d_leg = leg_distance(pos)
    coat_factor = smoothstep((d_leg - coat["leg_clearance_m"]) / CLEARANCE_RAMP_M)
    coat_factor[~lower_body | (pos[:, 2] < floor_z)] = 0.0
    depth = top_z - pos[:, 2]
    handover = smoothstep(depth / blend_len)
    k = coat_factor * handover
    changed = np.nonzero(k > 0.0)[0]
    az = np.degrees(np.arctan2(pos[changed, 0] - axis[0], -(pos[changed, 1] - axis[1])))
    around = angular_weights(az, np.array([c["degrees"] for c in chains]), coat["open_front"])
    along = along_weights(depth[changed] / seg, nb)
    chain_bones = [name for c in chains for name in c["names"][:nb]]
    chain_part = np.concatenate([around[:, [ci]] * along for ci in range(len(chains))], axis=1)
    kc = k[changed, None]
    blended = np.concatenate([(1.0 - kc) * original[changed], kc * chain_part], axis=1)
    if blended.shape[1] > MAX_INFLUENCES:
        cut = np.argsort(-blended, axis=1)[:, MAX_INFLUENCES:]
        np.put_along_axis(blended, cut, 0.0, axis=1)
    totals = blended.sum(axis=1)
    if (totals <= 0).any():
        raise SystemExit("A coat vertex ended with no weight; this is a bug.")
    blended /= totals[:, None]

    new_groups = [outfit.vertex_groups.new(name=name) for name in chain_bones]
    targets = [outfit.vertex_groups[gi] for gi in bone_groups] + new_groups
    had = np.concatenate([original[changed] > 0.0, np.zeros((len(changed), len(new_groups)), bool)], axis=1)
    for row, vi in enumerate(changed.tolist()):
        for col in np.nonzero((blended[row] > 0.0) | had[row])[0].tolist():
            w = float(blended[row, col])
            if w > 0.0:
                targets[col].add([vi], w, "REPLACE")
            else:
                targets[col].remove([vi])

    nbg = len(bone_groups)
    per_chain = {}
    for ci, c in enumerate(chains):
        cols = blended[:, nbg + ci * nb: nbg + (ci + 1) * nb]
        share = cols.sum(axis=1)
        per_chain[c["chain"]] = {"max_weight": round(float(share.max(initial=0.0)), 4),
                                 "vertices": int((share > 0).sum()),
                                 "max_weight_per_bone": {n: round(float(cols[:, b].max(initial=0.0)), 4)
                                                         for b, n in enumerate(c["names"][:nb])}}
    influences = (blended > 0).sum(axis=1)
    on_chains = blended[:, nbg:].sum(axis=1)

    if args.save_blend:
        Path(args.save_blend).parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(args.save_blend).resolve()), copy=True)

    # The pipeline's own UE5 export, on this scene: it reads <out> as the first argument after --.
    runpy.run_path(str(HERE / "export_ue5_character.py"), run_name="__main__")

    bones = []
    for c in chains:
        for i, name in enumerate(c["names"]):
            child = c["joints"][min(i + 1, nb)] if i < nb else None
            bones.append({"name": name, "parent": "pelvis" if i == 0 else c["names"][i - 1],
                          "deform": i < nb, "head_m": [round(x, 4) for x in c["joints"][i]],
                          "child_m": None if child is None else [round(x, 4) for x in child]})
    receipt = {
        "stage": "add_coat_chains.py",
        "input_blend": bpy.data.filepath,
        "input_sha256": hashlib.sha256(Path(bpy.data.filepath).read_bytes()).hexdigest(),
        "profile": str(profile_path),
        "coat": coat,
        "fbx": str(out),
        "fbx_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "outfit_object": outfit.name,
        "armature": arm.name,
        "pelvis_m": [round(x, 4) for x in pelvis],
        "knee_z_m": round(knee_z, 4),
        "top_z_m": round(top_z, 4),
        "hem_z_m": round(hem_z, 4),
        "segment_m": round(seg, 4),
        "chains": {c["chain"]: {"degrees": c["degrees"], "bones": c["names"],
                                "radius_top_m": round(c["radius_top_m"], 4),
                                "radius_hem_m": round(c["radius_hem_m"], 4),
                                "hem_found": c["hem_ray_z_m"] is not None,
                                "hem_ray_z_m": None if c["hem_ray_z_m"] is None else round(c["hem_ray_z_m"], 4),
                                **per_chain[c["chain"]]} for c in chains},
        "bones": bones,
        "outfit_vertices": nv,
        "coat_vertices": int((on_chains > 0).sum()),
        "coat_vertices_fully_on_chains": int((on_chains >= 0.999).sum()),
        "reweighted_vertices": int(len(changed)),
        "coat_max_influences": int(influences.max(initial=0)),
        "coat_zero_weight_vertices": int((blended.sum(axis=1) <= 0).sum()),
        "untouched_vertices": int(nv - len(changed)),
        "note": ("coat_vertices carry chain weight; reweighted_vertices also counts the edge of the coat, "
                 "where the four-influence cap kept only the vertex's own weights (renormalized)."),
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print("COAT {0} chains, {1} coat vertices of {2} on {3}; receipt {4}".format(
        len(chains), receipt["coat_vertices"], nv, outfit.name, receipt_path))
    for c in chains:
        print("COAT", c["chain"], json.dumps(receipt["chains"][c["chain"]]))


main()
