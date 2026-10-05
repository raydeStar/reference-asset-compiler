"""Write a mesh's world-space triangles to an NPZ, for numeric stages.

The conform and fitting stages run in plain Python with NumPy/SciPy, which
Blender's interpreter lacks. This is their reader: every mesh object in the
file, joined in world space and triangulated, with nothing else changed.
Read-only on the source.

Usage:
  blender -b --factory-startup --python scripts/blender/export_mesh_arrays.py \
      -- <mesh.glb|blend|fbx|obj> <out.npz>
"""

from __future__ import annotations

import sys
from pathlib import Path

import bpy
import numpy as np


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    src, out = Path(argv[0]), Path(argv[1])
    suffix = src.suffix.lower()
    if suffix == ".blend":
        bpy.ops.wm.open_mainfile(filepath=str(src))
    else:
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        if suffix in (".glb", ".gltf"):
            bpy.ops.import_scene.gltf(filepath=str(src))
        elif suffix == ".fbx":
            bpy.ops.import_scene.fbx(filepath=str(src))
        elif suffix == ".obj":
            bpy.ops.wm.obj_import(filepath=str(src))
        else:
            raise SystemExit("unsupported mesh format: " + suffix)

    verts, tris, offset = [], [], 0
    deps = bpy.context.evaluated_depsgraph_get()
    for ob in bpy.context.scene.objects:
        if ob.type != "MESH":
            continue
        ev = ob.evaluated_get(deps)
        me = ev.to_mesh()
        me.calc_loop_triangles()
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        m = np.array(ob.matrix_world)
        verts.append(co @ m[:3, :3].T + m[:3, 3])
        t = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
        me.loop_triangles.foreach_get("vertices", t)
        tris.append(t.reshape(-1, 3) + offset)
        offset += len(co)
        ev.to_mesh_clear()
    v = np.concatenate(verts)
    f = np.concatenate(tris)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, verts=v, tris=f)
    print("mesh", len(v), "verts", len(f), "tris", "bounds", v.min(0), v.max(0), "->", out)


main()
