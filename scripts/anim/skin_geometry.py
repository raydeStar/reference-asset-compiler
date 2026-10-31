# SPDX-License-Identifier: MIT
"""Complete native skin weights for measured contact; Blender CPU only."""

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector


def matrix(values):
    x, y, z, qx, qy, qz, qw = values
    value = Quaternion((qw, qx, qy, qz)).to_matrix().to_4x4()
    value.translation = Vector((x / 100, y / 100, z / 100))
    axes = Matrix.Diagonal((1.0, -1.0, 1.0, 1.0))
    return np.array(axes @ value @ axes)


def skin_data(obj, indices):
    vertices = np.array([obj.matrix_world @ v.co for v in obj.data.vertices])
    # Retain all source influences; silently truncating weights would invalidate a clearance claim.
    width = max(len(v.groups) for v in obj.data.vertices)
    weights = np.zeros((len(vertices), width))
    groups = np.zeros((len(vertices), width), dtype=int)
    for v in obj.data.vertices:
        for j, g in enumerate(v.groups):
            groups[v.index, j] = indices[obj.vertex_groups[g.group].name]
            weights[v.index, j] = g.weight
    assert np.max(abs(weights.sum(1) - 1)) < 0.001, "Unnormalised skin weights"
    return vertices, groups, weights


def deform(data, transforms):
    vertices, groups, weights = data
    t = transforms[groups]
    points = np.einsum("nvij,nj->nvi", t[:, :, :3, :3], vertices) + t[:, :, :3, 3]
    return np.einsum("nv,nvi->ni", weights, points)


def boot_data(rig):
    indices = {b.name: i for i, b in enumerate(rig.data.bones)}
    result = []
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH" or not any(
            m.type == "ARMATURE" and m.object == rig for m in obj.modifiers
        ):
            continue
        if not any(g.name.startswith(("foot_", "ball_")) for g in obj.vertex_groups):
            continue
        data = skin_data(obj, indices)
        # Select the actual boot mesh below its ankle/cuff, with the native rig's foot/ball weights.
        sides = {}
        for side in "lr":
            groups = {
                g.index for g in obj.vertex_groups if g.name in ("foot_" + side, "ball_" + side)
            }
            sides[side] = [
                v.index
                for v in obj.data.vertices
                if sum(g.weight for g in v.groups if g.group in groups) > 0.5
            ]
        if any(sides.values()):
            used = sorted(set().union(*map(set, sides.values())))
            remap = {old: new for new, old in enumerate(used)}
            result.append(
                (
                    obj.name,
                    tuple(values[used] for values in data),
                    {side: [remap[i] for i in ids] for side, ids in sides.items()},
                )
            )
    assert result
    return result
