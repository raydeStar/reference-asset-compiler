"""Bring the Raider's face to the reference's look: eyes, skin tone and finish.

- Eyes: the CC0 MakeHuman eyes carried the pale grey texture; lit, the near-white iris read as glowing cyan. The
  reference iris is a darker grey-hazel, so the eye texture becomes a blend of MakeHuman's CC0 grey and
  light-brown eye textures (same layout: both irises at fixed circles), with the iris (the light-brown texture's
  saturated ring) darkened.
- Skin: the baked face skin ran redder and more saturated than the reference (hue 19 against 22 degrees,
  saturation 0.64 against about 0.50; the ears read orange). Skin-like texels (hue under 45 degrees, saturation
  over 0.3, value over 0.3) are desaturated by SKIN_SAT, turned SKIN_HUE degrees towards yellow and lifted by
  SKIN_VAL, each faded in by how skin-like the texel is; dark hair and beard are left alone.
- Inner lips: the bake had projected beard paint onto the lips' inner surfaces; they take the outer lips' colour,
  darkening with depth.
- Finish: the face material (skin and the baked hair) was roughness 0.6, which put a grey sheen on the dark hair
  at the back of the head; it is made matte.

  $B -b <rigged.blend> --python look_face.py -- <mpfb eyes/materials dir> <out.blend> <out.fbx> [brown_mix] [iris_dark]
"""
import bpy
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from skin_tone import skin_weight, tone  # noqa: E402
from uv_raster import fill_polygon  # noqa: E402

a = sys.argv[sys.argv.index("--") + 1:]
eyes_dir, out_blend, out_fbx = a[0], a[1], a[2]
MIX = float(a[3]) if len(a) > 3 else 0.55
DARK = float(a[4]) if len(a) > 4 else 0.7
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
w = skin_weight(px[..., :3])
px[..., :3] = tone(px[..., :3], w)

# inner lips: the bake projected beard paint onto the lip surfaces inside the mouth line (hidden when closed), which
# showed as a dark, ragged band whenever he spoke. Faces in a narrow band round the lip line that face up, down or
# back (the outer lips and moustache face the front), and the lower lip's top that the open mouth shows, take the
# outer lips' own colour, darker the more they turn in.
face = bpy.data.objects["face"]
FM = face.matrix_world
fk = face.data.shape_keys.key_blocks
F0 = np.array([(FM @ d.co)[:] for d in fk[0].data])
dz_open = np.array([(FM @ d.co)[2] for d in fk["mouth-open"].data]) - F0[:, 2]
mid = np.nonzero((np.abs(F0[:, 0]) < 0.006) & (F0[:, 1] < -0.105) & (np.abs(F0[:, 2] - 1.62) < 0.04))[0]
mid = mid[np.argsort(F0[mid, 2])]
j = int(np.argmax(dz_open[mid][1:] - dz_open[mid][:-1]))
lip_line = 0.5 * (F0[mid[j], 2] + F0[mid[j + 1], 2])          # as fix_mouth.py finds it
NR = FM.to_3x3()
F6 = F0 + 0.6 * (np.array([(FM @ d.co)[:] for d in fk["mouth-open"].data]) - F0)   # half open
uvd = face.data.uv_layers.active.data
skin_slot = next(i for i, m in enumerate(face.data.materials) if m and m.name == "FACE_skin")
outer, inner = [], []
for p in face.data.polygons:
    if p.material_index != skin_slot:
        continue
    c = F0[list(p.vertices)].mean(0)
    c6 = F6[list(p.vertices)].mean(0)
    # the lower lip's top tucks above the lip line, behind the upper lip, at rest; half open it shows between the
    # teeth and the lip's edge (some of its faces point backwards, so it is found by place, not facing)
    if abs(c6[0]) < 0.03 and lip_line - 0.018 < c6[2] < lip_line - 0.002 and c6[1] < -0.10 and c[2] > lip_line - 0.001:
        inner.append((p, 0.0))
        continue
    if abs(c[0]) > 0.03 or abs(c[2] - lip_line) > 0.01:
        continue
    ny = (NR @ p.normal).normalized()[1]                       # -1 faces the front (-Y)
    # inside the mouth line, and the lower lip's top, which tips forward (ny down to about -0.6) and showed the
    # beard paint whenever the jaw dropped; the outer lips' fronts are steeper
    if ny > -0.25 or (ny > -0.6 and abs(c[2] - lip_line) < 0.006):
        inner.append((p, ny))                                   # facing up, down or back: inside the mouth line
    elif ny < -0.7 and 0.002 < abs(c[2] - lip_line) < 0.007 and abs(c[0]) < 0.02:
        outer.append(p)
H_, W_ = px.shape[:2]


def texel_mask(poly):
    m = np.zeros((H_, W_), bool)
    fill_polygon(m, [(uvd[li].uv[0] * W_, uvd[li].uv[1] * H_) for li in poly.loop_indices])
    return m


lip_mask = np.zeros((H_, W_), bool)
for p in outer:
    lip_mask |= texel_mask(p)
if not lip_mask.any():
    raise SystemExit("no outer lip faces found to sample the lip colour")
lip_colour = np.median(px[lip_mask][:, :3], axis=0)
painted = 0
for p, ny in inner:
    m = texel_mask(p)
    shade = float(np.clip(0.95 - 0.4 * (ny + 0.6), 0.5, 0.95))       # darker the further it turns into the mouth
    px[m, :3] = lip_colour * shade
    painted += int(m.sum())
print("LIPS lip line", round(lip_line, 4), "outer faces", len(outer), "inner faces", len(inner), "texels", painted,
      "colour", lip_colour.round(3).tolist())

# neck: the bake left it flat and pale with a hard light band under the beard; the reference's neck darkens under
# the jaw and towards its sides, and a dark grey-teal T-shirt shows at the bottom of the open collar about 10 cm
# below the chin. Neck faces get a shading multiplier (smoothed so the faces do not show) and, below the neckline,
# the reference's T-shirt colour.
TSHIRT, NECKLINE_DROP, NECKLINE_SOFT = np.array([0.231, 0.263, 0.259]), 0.10, 0.012
under_jaw = [F0[list(p.vertices)].mean(0)[2] for p in face.data.polygons
             if (NR @ p.normal).normalized()[2] < -0.5 and abs(F0[list(p.vertices)].mean(0)[0]) < 0.03
             and F0[list(p.vertices)].mean(0)[1] < -0.04
             and F0[list(p.vertices)].mean(0)[2] < lip_line - 0.02]        # below the lips (not the nose's underside)
chin_z = float(np.median(under_jaw)) if under_jaw else lip_line - 0.06
shade_map = np.ones((H_, W_), np.float32)
shirt_map = np.zeros((H_, W_), np.float32)
neck_mask = np.zeros((H_, W_), bool)
for p in face.data.polygons:
    if p.material_index != skin_slot:
        continue
    c = F0[list(p.vertices)].mean(0)
    if c[2] > chin_z + 0.012:          # up to the jaw line: the bake left a light, ragged band right under the beard
        continue
    n = (NR @ p.normal).normalized()
    front = float(np.clip(-n[1], 0, 1))
    jaw = float(np.clip((chin_z + 0.012 - c[2]) / 0.045, 0, 1))  # 0 at the jaw line, 1 4.5 cm down
    m = texel_mask(p)
    shade_map[m] = (0.7 + 0.3 * front ** 1.5) * (0.64 + 0.36 * jaw)
    shirt_map[m] = float(np.clip((chin_z - NECKLINE_DROP - c[2] + abs(c[0]) * 0.3) / NECKLINE_SOFT + 0.5, 0, 1))
    neck_mask |= m


def box_blur(a, r):
    """Separable box blur by cumulative sums (numpy only)."""
    for axis in (0, 1):
        c = np.cumsum(np.pad(a, [(r + 1, r) if i == axis else (0, 0) for i in range(2)], mode="edge"), axis=axis)
        a = (np.take(c, range(2 * r + 1, c.shape[axis]), axis=axis) - np.take(c, range(0, c.shape[axis] - 2 * r - 1), axis=axis)) / (2 * r + 1)
    return a


shade_map = np.where(neck_mask, box_blur(box_blur(shade_map, 6), 6), 1.0)
shirt_map = np.where(neck_mask, box_blur(shirt_map, 4), 0.0)
px[..., :3] = px[..., :3] * shade_map[..., None]
px[..., :3] = px[..., :3] * (1 - shirt_map[..., None]) + TSHIRT * shirt_map[..., None]
print("NECK chin", round(chin_z, 4), "neck texels", int(neck_mask.sum()), "shirt texels", int((shirt_map > 0.5).sum()))

# below about 1.50 m the open collar shows the body's own painted chest skin: its skin-coloured texels in the V
# below the neckline take the T-shirt colour, keeping their light and shade
body = bpy.data.objects["raider"]
BM_ = body.matrix_world
bmat = bpy.data.materials["painted"]
bnode = next(n for n in bmat.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image
             and any(lk.to_socket.name == "Base Color" for lk in n.outputs[0].links))
BW, BH = bnode.image.size
bpx = np.empty(BW * BH * 4, np.float32)
bnode.image.pixels.foreach_get(bpx)
bpx = bpx.reshape(BH, BW, 4)
buv = body.data.uv_layers.active.data
neckline = chin_z - NECKLINE_DROP
v_mask = np.zeros((BH, BW), bool)
bslot = next(i for i, m in enumerate(body.data.materials) if m == bmat)
for p in body.data.polygons:
    if p.material_index != bslot:
        continue
    c = np.array((BM_ @ p.center)[:])
    if abs(c[0]) > 0.09 or not (neckline - 0.08 < c[2] < neckline + 0.015 - abs(c[0]) * 0.3) or c[1] > -0.02:
        continue
    fill_polygon(v_mask, [(buv[li].uv[0] * BW, buv[li].uv[1] * BH) for li in p.loop_indices])
vrgb = bpx[v_mask][:, :3]
vskin = skin_weight(vrgb) > 0.3
if vskin.any():
    lum = vrgb[vskin].mean(1)
    rel = np.clip(lum / max(float(lum.mean()), 1e-4), 0.5, 1.5) ** 0.6
    vrgb[vskin] = np.clip(np.outer(rel, TSHIRT), 0, 1)
    bpx[v_mask, :3] = vrgb
    bpath = os.path.splitext(out_blend)[0] + "-body.png"
    bimg = bpy.data.images.new("raider_body_shirt", BW, BH, alpha=False)
    bimg.pixels.foreach_set(bpx.ravel())
    bimg.filepath_raw = bpath
    bimg.file_format = 'PNG'
    bimg.save()
    bnode.image = bpy.data.images.load(bpath)
print("SHIRT body texels", int(vskin.sum()), "neckline", round(neckline, 4))
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
