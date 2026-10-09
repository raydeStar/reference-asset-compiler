"""Cut a scan's hair out as its own textured mesh, in template metres.

Mesh hair, step two (docs/CHARACTER_MESH_HAIR.md). Keeps the triangles
classify_scan_hair.py marked as hair, minus any that the scan's own texture
paints as skin within --skin-near of the skin (an ear or a patch of scalp the
geometry let through; lit hair tips are far out and keep their caramel), welds
the seams the GLB split, and writes the result in the template's metres (the
conform receipt's similarity) with the scan's base-colour texture.

Usage:
  blender -b --factory-startup --python scripts/blender/cut_scan_hair.py -- \
      <scan.glb> <conform.json> <conform.npz> <classified.npz> <out_dir> [--yaw-deg 180] [--skin-near 0.04]

--yaw-deg turns the scan as it was turned before export_mesh_arrays.py (Pixal3D
delivers figures facing +y). Writes <out_dir>/hair-full.npz (verts, tris,
loop_uv), hair-full-basecolor.png and hair-full.json.
"""

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix


def base_colour_image(ob):
    for slot in ob.material_slots:
        if slot.material is None or not slot.material.use_nodes:
            continue
        for node in slot.material.node_tree.nodes:
            if node.type == "BSDF_PRINCIPLED" and node.inputs["Base Color"].is_linked:
                src = node.inputs["Base Color"].links[0].from_node
                while src.type != "TEX_IMAGE" and any(i.is_linked for i in src.inputs):
                    src = next(i for i in src.inputs if i.is_linked).links[0].from_node
                if src.type == "TEX_IMAGE" and src.image:
                    return src.image
    raise SystemExit("the scan has no base-colour texture")


def face_colours(me, img):
    """The texture under each face's corners, averaged, then lifted (see below)."""
    w, h = img.size
    pix = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(pix)
    pix = pix.reshape(h, w, 4)[..., :3]
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    starts = np.empty(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_start", starts)
    totals = np.empty(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_total", totals)
    rgb = pix[np.clip((uv[:, 1] % 1) * (h - 1), 0, h - 1).astype(int), np.clip((uv[:, 0] % 1) * (w - 1), 0, w - 1).astype(int)]
    mean = np.clip(np.add.reduceat(rgb, starts) / totals[:, None], 0, 1)
    # One more sRGB transfer on the stored values: it lifts the dark end apart, and skin_like's
    # thresholds were set on values read this way (character-02's Pixal3D head).
    return np.where(mean <= 0.0031308, mean * 12.92, 1.055 * np.power(mean, 1 / 2.4) - 0.055)


def skin_like(srgb):
    mx, mn = srgb.max(1), srgb.min(1)
    light = (mx + mn) / 2
    sat = (mx - mn) / np.maximum(1e-6, 1 - np.abs(2 * light - 1))
    hue = np.degrees(np.arctan2(np.sqrt(3) * (srgb[:, 1] - srgb[:, 2]), 2 * srgb[:, 0] - srgb[:, 1] - srgb[:, 2])) % 360
    return (light > 0.33) & (sat > 0.25) & (hue > 10) & (hue < 50)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    p = argparse.ArgumentParser()
    for name in ("scan", "receipt", "conform", "classified", "out"):
        p.add_argument(name)
    p.add_argument("--yaw-deg", type=float, default=0.0)
    p.add_argument("--skin-near", type=float, default=0.04)
    a = p.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(Path(a.scan).resolve()))
    obs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if len(obs) != 1:
        raise SystemExit(f"expected one mesh in the scan, found {len(obs)}: classify against a joined export")
    ob = obs[0]
    me = ob.data
    me.transform(Matrix.Rotation(math.radians(a.yaw_deg), 4, "Z") @ ob.matrix_world)
    ob.matrix_world = Matrix.Identity(4)
    al = json.loads(Path(a.receipt).read_text(encoding="utf-8"))["alignment"]
    s, r, t = al["scale_template_to_acquisition"], np.array(al["rotation"]), np.array(al["translation"])
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    me.vertices.foreach_set("co", (((co.reshape(-1, 3) - t) @ r) / s).ravel())
    me.update()

    n_scan = int(np.load(a.conform)["acq_tris"].shape[0])
    if len(me.polygons) != n_scan:
        raise SystemExit(f"the scan has {len(me.polygons)} faces, the conform {n_scan}: not the same export")
    cls = np.load(a.classified)
    keep = np.zeros(n_scan, bool)
    keep[cls["face_index"]] = True
    signed = np.zeros(n_scan)
    signed[cls["face_index"]] = cls["signed"]
    img = base_colour_image(ob)
    skin = skin_like(face_colours(me, img)) & (signed < a.skin_near)
    dropped = int((keep & skin).sum())
    keep &= ~skin

    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[f for f, k in zip(bm.faces, keep) if not k], context="FACES")
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)       # the GLB splits vertices at UV seams
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.update()

    verts = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", verts)
    tris = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", tris)
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    np.savez(out / "hair-full.npz", verts=verts.reshape(-1, 3), tris=tris.reshape(-1, 3), loop_uv=uv.reshape(-1, 2))
    img.filepath_raw = str(out / "hair-full-basecolor.png")
    img.file_format = "PNG"
    img.save()
    receipt = {"stage": "cut_scan_hair", "scan": str(a.scan),
               "scan_sha256": hashlib.sha256(Path(a.scan).read_bytes()).hexdigest(),
               "yaw_deg": a.yaw_deg, "classified_triangles": int(len(cls["face_index"])),
               "dropped_as_skin": dropped, "triangles": int(len(tris) // 3), "vertices": int(len(verts) // 3)}
    (out / "hair-full.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print("CUT_SCAN_HAIR " + json.dumps(receipt))


if __name__ == "__main__":
    main()
