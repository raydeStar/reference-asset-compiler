"""Prepare the preserved garment/wrist acquisition for source-view UV baking."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy
import numpy as np


def main():
    p = argparse.ArgumentParser()
    p.add_argument("source")
    p.add_argument("out")
    p.add_argument("--triangles", type=int, default=120000)
    a = p.parse_args(sys.argv[sys.argv.index("--") + 1:])
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(Path(a.source).resolve()))
    body = bpy.data.objects["Ennix_Garment_And_Wrists_Preserved"]
    for ob in list(bpy.data.objects):
        if ob != body:
            bpy.data.objects.remove(ob, do_unlink=True)
    body.hide_render = False
    body.hide_set(False)
    bpy.context.view_layer.objects.active = body
    body.select_set(True)
    before = len(body.data.polygons)
    mod = body.modifiers.new("review-reduction", "DECIMATE")
    mod.ratio = min(1.0, a.triangles / before)
    bpy.ops.object.modifier_apply(modifier=mod.name)
    body.data.materials.clear()
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.151917, island_margin=0.005, area_weight=0.5)
    bpy.ops.object.mode_set(mode="OBJECT")
    mesh = body.data
    mesh.calc_loop_triangles()
    verts = np.array([body.matrix_world @ v.co for v in mesh.vertices])
    tris = np.array([list(t.vertices) for t in mesh.loop_triangles])
    loops = np.array([list(t.loops) for t in mesh.loop_triangles])
    uv = np.array([list(u.uv) for u in mesh.uv_layers.active.data])
    np.savez_compressed(out / "body.npz", verts=verts, tris=tris, tris_uv=loops, uv=uv)
    bpy.ops.wm.save_as_mainfile(filepath=str(out / "body-uv.blend"))
    receipt = {"source": str(Path(a.source).resolve()),
               "source_sha256": hashlib.sha256(Path(a.source).read_bytes()).hexdigest(),
               "source_polygons": before, "triangles": len(tris), "vertices": len(verts),
               "uv_method": "Blender Smart Project", "topology_review_pending": True}
    (out / "body-preparation.json").write_text(json.dumps(receipt, indent=2))
    print("The tailor has retained the coat and repaired cuffs, sir.", json.dumps(receipt))


if __name__ == "__main__":
    main()
