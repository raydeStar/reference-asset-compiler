# SPDX-License-Identifier: MIT
"""Render Manny-space clip frames on a Manny-conformant character, with the wall / ledge they assume.

blender -b <Character>_UE5.blend --python render_traversal_preview.py -- \
    <manny_refpose.json> <preview_poses.json> <out_dir> --only AW_Climb_Up,... [--wall-y 62] [--lip-z 207] [--res 480]

A wireframe wall (UE +Y = wall-y cm in front of the feet) and, with --lip-z, a ledge on top of it, so hand
and foot contact can be judged; then pose_ue5_anim_test.py does the posing and rendering (--views back,side: the game camera's
view and the profile that shows wall contact).
"""
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pose_ue5_anim_test as pose_test  # noqa: E402


def arg(name, default=None):
    argv = sys.argv[sys.argv.index("--") + 1:]
    return argv[argv.index(name) + 1] if name in argv else default


def wire_box(name, loc, size):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    mod = ob.modifiers.new("wire", "WIREFRAME")
    mod.thickness = 0.012
    mat = bpy.data.materials.new(name + "_M")
    mat.diffuse_color = (0.15, 0.55, 0.9, 1)
    ob.data.materials.append(mat)
    return ob


def main():
    wall = arg("--wall-y")
    lip = arg("--lip-z")
    if wall is not None:
        y = -float(wall) / 100.0                      # UE +Y forward is Blender -Y
        top = float(lip) / 100.0 if lip else 2.6
        bpy.ops.mesh.primitive_plane_add(size=1)
        wall_ob = bpy.context.active_object
        wall_ob.name = "PreviewWall"
        wall_ob.rotation_euler = (1.5708, 0, 0)
        wall_ob.scale = (2.4, top, 1)
        wall_ob.location = (0, y - 0.002, top / 2)
        bpy.ops.object.modifier_add(type="SUBSURF")
        wall_ob.modifiers[-1].subdivision_type = "SIMPLE"
        wall_ob.modifiers[-1].levels = 4
        wire = wall_ob.modifiers.new("wire", "WIREFRAME")
        wire.thickness = 0.006
        if lip:
            wire_box("PreviewLedge", (0, y - 0.6, top - 0.15), (2.4, 1.2, 0.3))
    pose_test.main()


if __name__ == "__main__":
    main()
