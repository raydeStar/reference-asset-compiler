"""Render a painted, conformed head with its hair shell for likeness review.

The likeness gate is visual: the painted head beside the approved picture,
from the same angles. Skin and hair use their baked textures; the eyeballs
are projected from the front picture (their own eye texture is a later
stage), so the irises are the painting's. Soft, mostly flat lighting keeps
the painted light the picture already carries.

Usage:
  blender -b --factory-startup --python scripts/blender/render_painted_head.py -- \
      <template.npz> <conform.npz> <conform.json> <hair_shell.npz> <head.png> <hair.png> \
      <front_picture.png> <out_dir> [--resolution 1024] [--views front three-quarter side back]
      [--expression name=weight ...] [--tag neutral]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

HELPERS = ("helper-l-eye", "helper-r-eye", "helper-upper-teeth", "helper-lower-teeth",
           "helper-tongue")
VIEWS = {"front": 0.0, "three-quarter": 35.0, "side": 90.0, "back": 180.0,
         "three-quarter-left": -35.0, "top": 0.0, "top-back": 180.0}
ELEVATION = {"top": 65.0, "top-back": 50.0}   # degrees above the horizon; the rest are level


def _args():
    argv = sys.argv[sys.argv.index("--") + 1:]
    p = argparse.ArgumentParser()
    for name in ("template", "conform", "receipt", "hair", "head_tex", "hair_tex", "front",
                 "out_dir"):
        p.add_argument(name)
    p.add_argument("--resolution", type=int, default=1024)
    p.add_argument("--views", nargs="*", default=["front", "three-quarter", "side"])
    p.add_argument("--expression", nargs="*", default=[])
    p.add_argument("--tag", default="neutral")
    p.add_argument("--samples", type=int, default=64)
    p.add_argument("--strands", help="grow_hair_groom.py NPZ: draw the hair as strands over its "
                   "scalp cap instead of the shell")
    p.add_argument("--device", choices=("GPU", "CPU"), default="GPU",
                   help="Cycles device (CPU when the GPU is reserved)")
    return p.parse_args(argv)


def mesh(name, verts, faces, uv=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts.tolist(), [], [list(map(int, f)) for f in faces])
    me.update()
    if uv is not None:
        layer = me.uv_layers.new(name="UVMap")
        layer.data.foreach_set("uv", uv.ravel())
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def material(name, image_path, emission=0.55, roughness=0.85, specular=0.15, darken=1.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(image_path)
    colour = tex.outputs["Color"]
    if darken != 1.0:
        mul = nt.nodes.new("ShaderNodeVectorMath")
        mul.operation = "SCALE"
        mul.inputs["Scale"].default_value = darken
        nt.links.new(colour, mul.inputs[0])
        colour = mul.outputs["Vector"]
    nt.links.new(colour, bsdf.inputs["Base Color"])
    nt.links.new(colour, bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = emission
    bsdf.inputs["Roughness"].default_value = roughness
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = specular
    return mat


def main():
    a = _args()
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    tz = np.load(a.template)
    z = np.load(a.conform)
    reg = json.loads(Path(a.receipt).read_text(encoding="utf-8"))["picture"]["registration"]
    hz = np.load(a.hair)

    verts = z["verts"].copy()
    mix = dict(item.split("=") for item in a.expression)
    for name, w in mix.items():
        verts += float(w) * z["ex__" + name]

    helper = np.zeros(len(verts), bool)
    eye = np.zeros(len(verts), bool)
    for g in HELPERS:
        if "vg__" + g in z.files:
            helper[z["vg__" + g]] = True
            if g.endswith("-eye"):
                eye[z["vg__" + g]] = True
    skin_faces, skin_uv, eye_faces = [], [], []
    for i in z["keep_polys"]:
        s, n = int(z["loop_starts"][i]), int(z["loop_totals"][i])
        lv = z["loops"][s:s + n]
        if eye[lv].all():
            eye_faces.append(lv)
        elif not helper[lv].any():
            skin_faces.append(lv)
            skin_uv.append(tz["loop_uv"][s:s + n])

    def compact(faces):
        used = np.unique(np.concatenate(faces))
        remap = -np.ones(len(verts), np.int64)
        remap[used] = np.arange(len(used))
        return verts[used], [remap[f] for f in faces], used

    sv, sf, _ = compact(skin_faces)
    head = mesh("head", sv, sf, np.concatenate(skin_uv))
    head.data.materials.append(material("skin", a.head_tex))

    # Eyeballs: planar UVs from the front picture's registration.
    ev, ef, _ = compact(eye_faces)
    img = bpy.data.images.load(a.front)
    w, h = img.size
    plane = np.stack([ev[:, 0], -ev[:, 2]], 1)
    px = reg["scale_px_per_m"] * plane @ np.array(reg["rotation"]).T + np.array(reg["translation_px"])
    loop_uv = []
    for f in ef:
        for vi in f:
            loop_uv.append((px[vi, 0] / w, 1.0 - px[vi, 1] / h))
    eyes = mesh("eyes", ev, ef, np.array(loop_uv))
    # The iris colour is the picture's: a strong cornea reflection of the grey surroundings
    # would wash brown eyes to blue-grey.
    eyes.data.materials.append(material("eyes", a.front, emission=0.9, roughness=0.35,
                                        specular=0.12))
    sub = eyes.modifiers.new("smooth", "SUBSURF")
    sub.levels = sub.render_levels = 2

    hv, ht = hz["verts"], hz["tris"]
    if not a.strands:
        hair = mesh("hair", hv, ht, hz["loop_uv"])
        hair.data.materials.append(material("hair", a.hair_tex, emission=0.5, roughness=0.9,
                                            specular=0.08))
    else:
        # Strands carry the hair; a dark scalp cap under them keeps skin from showing
        # between them (the dense under-layer real hair has).
        sz = np.load(a.strands)
        cap = mesh("scalp-cap", sz["cap_verts"], sz["cap_tris"])
        cm = bpy.data.materials.new("scalp-cap")
        cm.use_nodes = True
        cb = cm.node_tree.nodes["Principled BSDF"]
        cb.inputs["Base Color"].default_value = (*sz["cap_colour"].tolist(), 1.0)
        cb.inputs["Roughness"].default_value = 0.9
        cap.data.materials.append(cm)
        hv = sz["points"]
        curves = bpy.data.hair_curves.new("groom")
        curves.add_curves(sz["counts"].tolist())
        curves.attributes["position"].data.foreach_set("vector", sz["points"].astype(np.float32).ravel())
        rad = curves.attributes.get("radius") or curves.attributes.new("radius", "FLOAT", "POINT")
        rad.data.foreach_set("value", sz["radius"].astype(np.float32))
        col = curves.attributes.new("strand_colour", "FLOAT_COLOR", "POINT")
        rgba = np.c_[sz["colours"], np.ones(len(sz["colours"]))].astype(np.float32)
        col.data.foreach_set("color", rgba.ravel())
        groom = bpy.data.objects.new("groom", curves)
        bpy.context.scene.collection.objects.link(groom)
        hm = bpy.data.materials.new("strands")
        hm.use_nodes = True
        nt = hm.node_tree
        for node in list(nt.nodes):
            if node.type != "OUTPUT_MATERIAL":
                nt.nodes.remove(node)
        bsdf = nt.nodes.new("ShaderNodeBsdfHairPrincipled")
        bsdf.parametrization = "COLOR"
        bsdf.inputs["Roughness"].default_value = 0.35
        bsdf.inputs["Radial Roughness"].default_value = 0.4
        attr = nt.nodes.new("ShaderNodeAttribute")
        attr.attribute_name = "strand_colour"
        attr.attribute_type = "GEOMETRY"
        nt.links.new(attr.outputs["Color"], bsdf.inputs["Color"])
        mat_out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
        nt.links.new(bsdf.outputs[0], mat_out.inputs["Surface"])
        curves.materials.append(hm)

    # Light and camera.
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = a.samples
    scene.cycles.use_denoising = True
    scene.cycles.device = "CPU"
    if a.device == "GPU":
        try:
            prefs = bpy.context.preferences.addons["cycles"].preferences
            prefs.compute_device_type = "OPTIX"
            prefs.get_devices()
            for d in prefs.devices:
                d.use = True
            scene.cycles.device = "GPU"
        except Exception:
            pass
    scene.render.resolution_x = scene.render.resolution_y = a.resolution
    scene.view_settings.view_transform = "Standard"
    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.62, 0.6, 0.58, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35
    scene.world = world
    all_v = np.concatenate([sv, hv])
    centre = Vector(((all_v.min(0) + all_v.max(0)) / 2).tolist())
    height = float(all_v[:, 2].max() - all_v[:, 2].min())
    # Soft and modest: the paint already carries its own light.
    for name, loc, energy, size in (("key", (-0.6, -1.0, 0.6), 16.0, 1.2),
                                    ("fill", (0.8, -0.8, 0.1), 7.0, 1.5),
                                    ("rim", (0.3, 1.0, 0.5), 10.0, 0.8)):
        light = bpy.data.lights.new(name, "AREA")
        light.energy = energy
        light.size = size
        light.color = (1.0, 0.92, 0.82)
        lo = bpy.data.objects.new(name, light)
        lo.location = centre + Vector(loc)
        lo.rotation_euler = (centre - lo.location).to_track_quat("-Z", "Y").to_euler()
        scene.collection.objects.link(lo)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.lens = 85
    scene.collection.objects.link(cam)
    scene.camera = cam
    dist = height * 85 / 36 * 1.25
    for view in a.views:
        ang = math.radians(VIEWS[view])
        el = math.radians(ELEVATION.get(view, 0.0))
        d = Vector((math.sin(ang) * math.cos(el), -math.cos(ang) * math.cos(el), math.sin(el)))
        cam.location = centre + d * dist
        cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = str(out / "{}-{}.png".format(a.tag, view))
        bpy.ops.render.render(write_still=True)
    print("rendered", a.tag, a.views, "->", out)


main()
