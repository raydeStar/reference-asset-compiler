"""Report world-space bounds of every object in a scene. Read-only.

Usage:
  blender -b --factory-startup --python scripts/blender/measure.py -- <asset>
"""

from __future__ import annotations

import sys
from pathlib import Path

import bpy
from mathutils import Vector


def main() -> int:
    path = Path(sys.argv[sys.argv.index("--") + 1])
    if path.suffix.lower() == ".fbx":
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.fbx(filepath=str(path))
    else:
        bpy.ops.wm.open_mainfile(filepath=str(path))

    scene = bpy.context.scene
    print("SCENE unit_system={0} scale_length={1}".format(
        scene.unit_settings.system, scene.unit_settings.scale_length))

    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            world = obj.matrix_world @ Vector(corner)
            for i in range(3):
                lo[i] = min(lo[i], world[i])
                hi[i] = max(hi[i], world[i])

    size = hi - lo
    print("MESH world bounds min=({0:.4f}, {1:.4f}, {2:.4f})".format(*lo))
    print("MESH world bounds max=({0:.4f}, {1:.4f}, {2:.4f})".format(*hi))
    print("MESH world size  X={0:.4f} Y={1:.4f} Z={2:.4f}".format(*size))

    for obj in bpy.data.objects:
        if obj.type != "ARMATURE":
            continue
        print("ARMATURE '{0}' scale={1} loc={2}".format(
            obj.name,
            tuple(round(v, 5) for v in obj.scale),
            tuple(round(v, 5) for v in obj.location),
        ))
        heads = [obj.matrix_world @ b.head_local for b in obj.data.bones]
        if heads:
            zs = [h.z for h in heads]
            print("  bone head Z range {0:.4f} .. {1:.4f}".format(min(zs), max(zs)))
        for name in ("root", "pelvis", "head", "foot_l"):
            bone = obj.data.bones.get(name)
            if bone:
                world = obj.matrix_world @ bone.head_local
                print("  {0:<8} head world=({1:.4f}, {2:.4f}, {3:.4f})".format(
                    name, world.x, world.y, world.z))
    return 0


if __name__ == "__main__":
    sys.exit(main())
