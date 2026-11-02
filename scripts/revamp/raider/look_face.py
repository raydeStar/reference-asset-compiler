"""Bring the Raider's face to the reference's look: eyes, skin tone and finish.

- Eyes: the CC0 MakeHuman eyes carried the pale grey texture; lit, the near-white iris read as glowing cyan. The
  reference iris is a darker grey-hazel, so the eye texture becomes a blend of MakeHuman's CC0 grey and
  light-brown eye textures (same layout: both irises at fixed circles), with the iris (the light-brown texture's
  saturated ring) darkened.
- Skin: the baked face skin ran redder and more saturated than the reference (hue 19 against 22 degrees,
  saturation 0.64 against about 0.50; the ears read orange). Skin-like texels (hue under 45 degrees, saturation
  over 0.3, value over 0.3) are desaturated by SKIN_SAT, turned SKIN_HUE degrees towards yellow and lifted by
  SKIN_VAL, each faded in by how skin-like the texel is; dark hair and beard are left alone.
- Finish: the face material (skin and the baked hair) was roughness 0.6, which put a grey sheen on the dark hair
  at the back of the head; it is made matte.

  $B -b <rigged.blend> --python look_face.py -- <mpfb eyes/materials dir> <out.blend> <out.fbx> [brown_mix] [iris_dark]
"""
import bpy
import os
import sys

import numpy as np

a = sys.argv[sys.argv.index("--") + 1:]
eyes_dir, out_blend, out_fbx = a[0], a[1], a[2]
MIX = float(a[3]) if len(a) > 3 else 0.55
DARK = float(a[4]) if len(a) > 4 else 0.7
SKIN_SAT, SKIN_HUE, SKIN_VAL = 0.8, 3.0, 1.08
FACE_ROUGH, FACE_SPEC = 0.8, 0.35


def pixels(path):
    img = bpy.data.images.load(path)
    px = np.empty(img.size[0] * img.size[1] * 4, np.float32)
    img.pixels.foreach_get(px)
    return img, px.reshape(img.size[1], img.size[0], 4)


grey_img, grey = pixels(os.path.join(eyes_dir, "grey_eye.png"))
_, brown = pixels(os.path.join(eyes_dir, "brownlight_eye.png"))
rgb = brown[..., :3]
sat = (rgb.max(2) - rgb.min(2)) / np.maximum(rgb.max(2), 1e-4)
iris = np.clip((sat - 0.2) / 0.15, 0, 1)[..., None]
out = grey.copy()
out[..., :3] = (grey[..., :3] * (1 - MIX) + brown[..., :3] * MIX) * (1 - iris * (1 - DARK))
H, W = out.shape[:2]
path = os.path.splitext(out_blend)[0] + "-hazel_eye.png"
img = bpy.data.images.new("raider_hazel_eye", W, H, alpha=True)
img.pixels.foreach_set(out.ravel())
img.filepath_raw = path
img.file_format = 'PNG'
img.save()
hazel = bpy.data.images.load(path)
swapped = 0
for m in bpy.data.materials:
    if not m.node_tree:
        continue
    for n in m.node_tree.nodes:
        if n.type == 'TEX_IMAGE' and n.image and n.image.name.endswith("_eye.png"):
            n.image = hazel
            swapped += 1
print("EYES iris texels", int((iris[..., 0] > 0.5).sum()), "texture nodes swapped", swapped)
if not swapped:
    raise SystemExit("no eye texture node found")

# skin: tone the baked face skin texture towards the reference
face_mat = bpy.data.materials["FACE_skin"]
skin_node = next(n for n in face_mat.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image)
sk = skin_node.image
px = np.empty(sk.size[0] * sk.size[1] * 4, np.float32)
sk.pixels.foreach_get(px)
px = px.reshape(sk.size[1], sk.size[0], 4)
r, g, b = px[..., 0], px[..., 1], px[..., 2]
mx, mn = px[..., :3].max(2), px[..., :3].min(2)
val = mx
sat = np.where(mx > 1e-4, (mx - mn) / np.maximum(mx, 1e-4), 0)
d = np.maximum(mx - mn, 1e-6)
hue = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60
w = np.clip((45 - hue) / 10, 0, 1) * np.clip((sat - 0.3) / 0.1, 0, 1) * np.clip((val - 0.3) / 0.1, 0, 1)
hue2 = hue + SKIN_HUE * w
sat2 = sat * (1 - (1 - SKIN_SAT) * w)
val2 = np.clip(val * (1 + (SKIN_VAL - 1) * w), 0, 1)
c = val2 * sat2
x = c * (1 - np.abs((hue2 / 60) % 2 - 1))
m0 = val2 - c
hk = (hue2 // 60).astype(int) % 6
rgb = np.zeros(px.shape[:2] + (3,), np.float32)
for k, (rr, gg, bb) in enumerate(((c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x))):
    sel = hk == k
    for ch, comp in enumerate((rr, gg, bb)):
        rgb[..., ch][sel] = (comp[sel] if isinstance(comp, np.ndarray) else comp) + m0[sel]
px[..., :3] = np.where(w[..., None] > 0, rgb, px[..., :3])
spath = os.path.splitext(out_blend)[0] + "-face_skin.png"
simg = bpy.data.images.new("raider_face_skin", sk.size[0], sk.size[1], alpha=True)
simg.pixels.foreach_set(px.ravel())
simg.filepath_raw = spath
simg.file_format = 'PNG'
simg.save()
skin_node.image = bpy.data.images.load(spath)
print("SKIN toned texels", int((w > 0.5).sum()), "of", int(w.size))

# finish: matte face (skin and baked hair)
bsdf = next(n for n in face_mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
bsdf.inputs["Roughness"].default_value = FACE_ROUGH
bsdf.inputs["Specular IOR Level"].default_value = FACE_SPEC
bpy.ops.wm.save_as_mainfile(filepath=out_blend)
arm = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
for o in bpy.context.scene.objects:
    o.select_set(o.type in ('ARMATURE', 'MESH'))
bpy.context.view_layer.objects.active = arm
bpy.ops.export_scene.fbx(filepath=out_fbx, use_selection=True, object_types={'ARMATURE', 'MESH'}, apply_scale_options="FBX_SCALE_ALL",
                         axis_forward="-Y", axis_up="Z", global_scale=1.0, apply_unit_scale=True, bake_anim=False,
                         add_leaf_bones=False, primary_bone_axis="Y", secondary_bone_axis="X", mesh_smooth_type="FACE",
                         use_armature_deform_only=False, path_mode="COPY", embed_textures=True, use_mesh_modifiers=False)
print("LOOK_FACE_OK")
