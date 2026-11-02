"""Bring the Raider's painted arm and chest skin to the reference's tone (as look_face.py does for the face).

The bare forearms (painted on the hand acquisition) and the body's skin (the open collar) read orange: as bright as
the reference's skin but redder (forearm mean (0.68, 0.43, 0.30) against the reference forearm's (0.68, 0.47,
0.34)). Each is matched by a per-channel gain that brings its skin's mean to a target (forearms to the colour that renders as
the reference forearm, collar skin to the reference face), keeping each texel's variation. The
face's desaturate-and-lift (skin_tone.tone) left these brighter paints pale and pink. In the hand texture, skin is
told from the glove's leather by brightness (leather below 0.4, skin above 0.55, same hue); in the body texture
only texels of faces labelled skin are touched (tan pouches and leather share skin's hue).

  $B -b --factory-startup --python tone_skin.py -- <in.glb> <out.glb> <paint.obj> <face-parts.npy> <face-parts.json>
"""
import bpy
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from skin_tone import skin_weight  # noqa: E402
from uv_raster import fill_polygon  # noqa: E402

a = sys.argv[sys.argv.index("--") + 1:]
src, out, obj_p, parts_p, names_p = a[:5]
# Texture targets, sRGB. The reference forearm's skin averages (0.63, 0.43, 0.32), saturation 0.49; the studio
# render lifts and greys painted skin (a texture at the reference's mean rendered at (0.68, 0.52, 0.44), saturation
# 0.36), so the forearm texture aims darker and richer, chosen so the rendered forearm lands on the reference.
REF_FOREARM = np.array([0.54, 0.345, 0.225])
REF_FACE = np.array([0.559, 0.370, 0.276])     # collar skin: the reference face and neck mean


def match(rgb, w, target):
    sel = w > 0.5
    gain = target / np.maximum(rgb[sel].mean(0), 1e-4)
    return rgb * (1 - w[..., None]) + np.clip(rgb * gain, 0, 1) * w[..., None], gain
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)


def base_node(mat):
    return next(n for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image
                and any(lk.to_socket.name == "Base Color" for lk in n.outputs[0].links))


def pixels(img):
    px = np.empty(img.size[0] * img.size[1] * 4, np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(img.size[1], img.size[0], 4)


def replace(node, px, tag):
    W, H = node.image.size
    img = bpy.data.images.new(node.image.name + "-" + tag, W, H, alpha=False)
    img.pixels.foreach_set(px.ravel())
    path = f"{os.path.splitext(out)[0]}-{node.image.name}-{tag}.png"
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    node.image = bpy.data.images.load(path)      # a loaded file is what the exporter embeds


report = {}
# hand texture: skin by brightness
hand_mat = next(m for m in bpy.data.materials if m.node_tree and any(
    n.type == 'TEX_IMAGE' and n.image and n.image.name.startswith("raider-hand") for n in m.node_tree.nodes))
hn = base_node(hand_mat)
hp = pixels(hn.image)
w = skin_weight(hp[..., :3], value_floor=0.48)
hp[..., :3], gain = match(hp[..., :3], w, REF_FOREARM)
replace(hn, hp, "skin")
report["hand"] = {"texels_toned": int((w > 0.5).sum()), "gain": gain.round(3).tolist()}
# body texture: skin-labelled faces only
names = json.load(open(names_p))["parts"]
labels = np.load(parts_p)
vt, faces = [], []
for line in open(obj_p, encoding="utf-8", errors="ignore"):
    if line.startswith("vt "):
        vt.append([float(x) for x in line.split()[1:3]])
    elif line.startswith("f "):
        faces.append([int(c.split("/")[1]) - 1 for c in line.split()[1:]])
vt = np.array(vt)
bn = base_node(bpy.data.materials["painted"])
bp = pixels(bn.image)
H, W = bp.shape[:2]
mask = np.zeros((H, W), bool)
for fi in np.nonzero(labels == names.index("skin"))[0]:
    fill_polygon(mask, [(vt[i, 0] * W, vt[i, 1] * H) for i in faces[fi]])
w = skin_weight(bp[..., :3]) * mask
bp[..., :3], gain = match(bp[..., :3], w, REF_FACE)
replace(bn, bp, "skin")
report["body"] = {"texels_toned": int((w > 0.5).sum()), "gain": gain.round(3).tolist()}
print("SKIN", report)
bpy.ops.export_scene.gltf(filepath=out, export_format='GLB')
side = json.load(open(src + ".json")) if os.path.exists(src + ".json") else {}
side.update({"skin_tone": report})
json.dump(side, open(out + ".json", "w"), indent=2)
print("TONE_SKIN_OK")
