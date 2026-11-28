"""Tone the Raider's iron plates to the reference's worn iron.

Hunyuan3D-Paint painted the shoulder, chest and back plates and the knee pads near-white silver; the reference
shows dark, warm, worn iron. The plate and knee-pad faces of the paint mesh (their part labels from
part_uv_mask.py), and the light grey texels of jacket faces (the back plate was labelled jacket), are rasterized in
UV space into a mask; inside it each texel takes the part's reference colour
(measured on the reference: plates (0.37, 0.32, 0.28), knee pads (0.31, 0.25, 0.21), sRGB, darkened 20%) scaled by its own
brightness relative to the part's mean, so scratches, rivets and edges keep their contrast. The plates get a
worn-iron finish in the packed metallic-roughness map (roughness 0.55, metallic 0.55).

  $B -b --factory-startup --python tone_metal.py -- <in.glb> <out.glb> <paint.obj> <face-parts.npy> <face-parts.json>
"""
import bpy
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from uv_raster import fill_polygon  # noqa: E402


a = sys.argv[sys.argv.index("--") + 1:]
src, out, obj_p, parts_p, names_p = a[:5]
# part: (reference colour, saturation below which a texel is fully iron, and the lightness a texel needs).
# The back plate was labelled jacket: there only light, grey texels count (the jacket's own paint is dark teal,
# saturation 0.5 and up).
TARGET = {"plate": ((0.37, 0.32, 0.28), 0.45, 0.0), "kneepad": ((0.31, 0.25, 0.21), 0.4, 0.0),
          "jacket": ((0.37, 0.32, 0.28), 0.22, 0.3)}
# the reference colours carry the painting's own light; lit again in a render they read pale, so they are darkened
DARKEN, CONTRAST, ROUGH, METAL = 0.8, 1.0, 0.55, 0.55
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
names = json.load(open(names_p))["parts"]
labels = np.load(parts_p)
vt, faces = [], []
for line in open(obj_p, encoding="utf-8", errors="ignore"):
    if line.startswith("vt "):
        vt.append([float(x) for x in line.split()[1:3]])
    elif line.startswith("f "):
        faces.append([int(c.split("/")[1]) - 1 for c in line.split()[1:]])
vt = np.array(vt)
if len(faces) != len(labels):
    raise SystemExit(f"paint mesh has {len(faces)} faces but {len(labels)} part labels")
mat = bpy.data.materials["painted"]
texs = [n for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image]
base_node = next(n for n in texs if any(lk.to_socket.name == "Base Color" for lk in n.outputs[0].links))
mr_node = next(n for n in texs if n is not base_node)
W, H = base_node.image.size


def pixels(img):
    px = np.empty(img.size[0] * img.size[1] * 4, np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(img.size[1], img.size[0], 4)


base, mr = pixels(base_node.image), pixels(mr_node.image)
report = {}
for part, (target, sat_iron, light_min) in TARGET.items():
    pid = names.index(part)
    mask = np.zeros((H, W), bool)
    for fi in np.nonzero(labels == pid)[0]:
        fill_polygon(mask, [(vt[i, 0] * W, vt[i, 1] * H) for i in faces[fi]])
    # one texel of padding so seams do not keep a silver rim
    mask[1:, :] |= mask[:-1, :].copy()
    mask[:-1, :] |= mask[1:, :].copy()
    mask[:, 1:] |= mask[:, :-1].copy()
    mask[:, :-1] |= mask[:, 1:].copy()
    rgb = base[mask][:, :3]
    lum = rgb.mean(1)
    # silvery texels (low saturation) take the iron fully; the brown leather rims and straps inside the part keep
    # their colour
    sat = (rgb.max(1) - rgb.min(1)) / np.maximum(rgb.max(1), 1e-4)
    w = np.clip((sat_iron - sat) / 0.15, 0, 1)
    if light_min > 0:
        w = w * np.clip((lum - light_min) / 0.08, 0, 1)
    w = w[:, None]
    rel = np.clip(lum / max(1e-4, float(np.average(lum, weights=w[:, 0] + 1e-6))), 0, 3) ** CONTRAST
    iron = np.clip(np.outer(rel, np.array(target) * DARKEN), 0, 1)
    base[mask, :3] = rgb * (1 - w) + iron * w
    mr[mask, 1] = mr[mask, 1] * (1 - w[:, 0]) + ROUGH * w[:, 0]
    mr[mask, 2] = mr[mask, 2] * (1 - w[:, 0]) + METAL * w[:, 0]
    report[part] = {"texels": int(mask.sum()), "iron_weight_mean": round(float(w.mean()), 3), "mean_before": round(float(lum.mean()), 3),
                    "mean_after": round(float(base[mask][:, :3].mean()), 3)}
    print("TONE", part, report[part])
stem = os.path.splitext(out)[0]
for node, px, cs in ((base_node, base, 'sRGB'), (mr_node, mr, 'Non-Color')):
    img = bpy.data.images.new(node.image.name + "-toned", W, H, alpha=False)
    img.colorspace_settings.name = cs
    img.pixels.foreach_set(px.ravel())
    path = f"{stem}-{node.image.name}-toned.png"
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    fresh = bpy.data.images.load(path)      # a loaded file is what the exporter embeds
    fresh.colorspace_settings.name = cs
    node.image = fresh
bpy.ops.export_scene.gltf(filepath=out, export_format='GLB')
side = json.load(open(src + ".json")) if os.path.exists(src + ".json") else {}
side.update({"metal_tone": report})
json.dump(side, open(out + ".json", "w"), indent=2)
print("TONE_METAL_OK")
