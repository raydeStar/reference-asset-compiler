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
    p.add_argument("--scalp-cap", help="mesh hair: draw this cap (mesh_hair_scalp_cap.py NPZ) under the hair mesh")
    p.add_argument("--hair-normal", help="mesh hair: its tangent-space normal map (build_mesh_hair.py)")
    p.add_argument("--device", choices=("GPU", "CPU"), default="GPU",
                   help="Cycles device (CPU when the GPU is reserved)")
    p.add_argument("--subdivision", type=int, default=0)
    p.add_argument("--save-blend", help="save a packed editable character review with expression keys")
    p.add_argument("--oral-helpers", action="store_true", help="include the template's teeth and tongue")
    p.add_argument("--skin-emission", type=float, default=0.55)
    p.add_argument("--hair-tint", type=float, nargs=3, default=(1, 1, 1))
    p.add_argument("--hair-roughness", type=float, default=0.35)
    # The game look: strands as a game engine draws them, so gaps between locks show here as
    # they do in game (the NPZ's own radius and baked colours are more forgiving).
    p.add_argument("--strand-width", type=float, nargs=3, metavar=("CM", "ROOT", "TIP"),
                   help="draw strands this wide (cm) scaled from ROOT to TIP along each strand "
                        "(Unreal's hair_width, hair_root_scale, hair_tip_scale) instead of the NPZ radius")
    p.add_argument("--strand-gradient", type=float, nargs=6, metavar=("R0", "G0", "B0", "R1", "G1", "B1"),
                   help="linear root and tip colours blended along each strand (u^0.8, each strand "
                        "x0.7-1.3) as a game hair material does, instead of the NPZ colours")
    p.add_argument("--cap-colour", type=float, nargs=3, help="linear scalp cap colour (default: the NPZ's)")
    p.add_argument("--light", choices=("studio", "sun"), default="studio",
                   help="studio: soft area lights; sun: one hard low sun and a dim sky, as in game")
    p.add_argument("--hair-shader", choices=("principled", "diffuse"), default="principled",
                   help="diffuse: no light through the hair, so locks shade each other as game hair's "
                        "deep shadows do (Cycles' hair BSDF lights the inside of the hair)")
    p.add_argument("--id-pass", action="store_true",
                   help="also write <tag>-<view>-id.png: hair (strands or mesh) red, scalp cap green, skin blue")
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


def material(name, image_path, emission=0.55, roughness=0.85, specular=0.15, darken=1.0, normal_map=None):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(Path(image_path).resolve()))
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
    if normal_map:
        image = nt.nodes.new("ShaderNodeTexImage")
        image.image = bpy.data.images.load(str(Path(normal_map).resolve()))
        image.image.colorspace_settings.name = "Non-Color"
        node = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(image.outputs["Color"], node.inputs["Color"])
        nt.links.new(node.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def scalp_cap(caps, colour=None):
    """The dark scalp cap under the hair (keys cap_verts, cap_tris, cap_colour), so skin never shows between
    locks or strands (the dense under-layer real hair has)."""
    # Keep only the vertices the cap's triangles use: a groom can hand over the whole template's vertex array,
    # and loose vertices far below the head (down to the feet) then poison every bounds-based measurement
    # downstream (the UE5 rig planner took "ground" from them).
    cap_tris = np.asarray(caps["cap_tris"]).astype(np.int64)
    used = np.unique(cap_tris)
    remap = -np.ones(len(caps["cap_verts"]), np.int64)
    remap[used] = np.arange(len(used))
    cap = mesh("scalp-cap", np.asarray(caps["cap_verts"])[used], remap[cap_tris])
    cm = bpy.data.materials.new("scalp-cap")
    cm.use_nodes = True
    cb = cm.node_tree.nodes["Principled BSDF"]
    cap_colour = colour if colour else caps["cap_colour"].tolist()
    cb.inputs["Base Color"].default_value = (*cap_colour, 1.0)
    cb.inputs["Roughness"].default_value = 0.9
    cap.data.materials.append(cm)
    return cap


def main():
    a = _args()
    out = Path(a.out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    tz = np.load(a.template)
    z = np.load(a.conform)
    reg = json.loads(Path(a.receipt).read_text(encoding="utf-8"))["picture"]["registration"]
    hz = np.load(a.hair)

    verts = z["verts"].copy()
    mix = dict(item.split("=") for item in a.expression)

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

    def expressions(ob, used):
        ob.shape_key_add(name="Basis")
        for name in z.files:
            if name.startswith("ex__"):
                key = ob.shape_key_add(name=name[4:])
                key.data.foreach_set("co", (verts[used] + z[name][used]).astype(np.float32).ravel())
                key.value = float(mix.get(name[4:], 0.0))

    sv, sf, skin_used = compact(skin_faces)
    head = mesh("head", sv, sf, np.concatenate(skin_uv))
    expressions(head, skin_used)
    head.data.materials.append(material("skin", a.head_tex, emission=a.skin_emission))
    if a.subdivision:
        sub = head.modifiers.new("continuous-skin", "SUBSURF")
        sub.levels = sub.render_levels = a.subdivision

    # Eyeballs: planar UVs from the front picture's registration.
    ev, ef, eye_used = compact(eye_faces)
    img = bpy.data.images.load(str(Path(a.front).resolve()))
    w, h = img.size
    texture_ev = z["texture_verts"][eye_used] if "texture_verts" in z else ev
    plane = np.stack([texture_ev[:, 0], -texture_ev[:, 2]], 1)
    px = reg["scale_px_per_m"] * plane @ np.array(reg["rotation"]).T + np.array(reg["translation_px"])
    loop_uv = []
    for f in ef:
        for vi in f:
            loop_uv.append((px[vi, 0] / w, 1.0 - px[vi, 1] / h))
    eyes = mesh("eyes", ev, ef, np.array(loop_uv))
    expressions(eyes, eye_used)
    # The iris colour is the picture's: a strong cornea reflection of the grey surroundings
    # would wash brown eyes to blue-grey.
    eyes.data.materials.append(material("eyes", a.front, emission=0.9, roughness=0.35,
                                        specular=0.12))
    sub = eyes.modifiers.new("smooth", "SUBSURF")
    sub.levels = sub.render_levels = 2

    if a.oral_helpers:
        for group in ("helper-upper-teeth", "helper-lower-teeth", "helper-tongue"):
            ids = z["vg__" + group]
            selected = np.zeros(len(verts), bool)
            selected[ids] = True
            faces = []
            for i in z["keep_polys"]:
                start, count = int(z["loop_starts"][i]), int(z["loop_totals"][i])
                face = z["loops"][start:start + count]
                if selected[face].all():
                    faces.append(face)
            if not faces:
                continue
            ov, of, used = compact(faces)
            ob = mesh(group, ov, of)
            expressions(ob, used)
            mat = bpy.data.materials.new(group)
            mat.diffuse_color = (0.32, 0.07, 0.06, 1.0) if group.endswith("tongue") else (0.7, 0.62, 0.46, 1.0)
            mat.use_nodes = True
            bsdf = mat.node_tree.nodes["Principled BSDF"]
            bsdf.inputs["Base Color"].default_value = mat.diffuse_color
            bsdf.inputs["Roughness"].default_value = 0.42
            ob.data.materials.append(mat)
            sub = ob.modifiers.new("smooth", "SUBSURF")
            sub.levels = sub.render_levels = 1

    hv, ht = hz["verts"], hz["tris"]
    if not a.strands:
        # The hair shell, or mesh hair (build_mesh_hair.py) over its own scalp cap.
        hair = mesh("hair", hv, ht, hz["loop_uv"])
        hair.data.materials.append(material("hair", a.hair_tex, emission=0.5, roughness=0.9,
                                            specular=0.08, normal_map=a.hair_normal))
        if a.scalp_cap:
            scalp_cap(np.load(a.scalp_cap), a.cap_colour)
    else:
        # Strands carry the hair over a dark scalp cap.
        sz = np.load(a.strands)
        scalp_cap(sz, a.cap_colour)
        hv = sz["points"]
        counts = sz["counts"]
        curves = bpy.data.hair_curves.new("groom")
        curves.add_curves(counts.tolist())
        curves.attributes["position"].data.foreach_set("vector", sz["points"].astype(np.float32).ravel())
        # Each point's place along its strand, 0 at the root and 1 at the tip.
        first = np.repeat(np.r_[0, np.cumsum(counts)[:-1]], counts)
        along = (np.arange(int(counts.sum())) - first) / np.repeat(np.maximum(counts - 1, 1), counts)
        radius = sz["radius"].astype(np.float32)
        if a.strand_width:
            cm_, root, tip = a.strand_width
            radius = (0.5 * cm_ / 100.0 * (root + (tip - root) * along)).astype(np.float32)
        rad = curves.attributes.get("radius") or curves.attributes.new("radius", "FLOAT", "POINT")
        rad.data.foreach_set("value", radius)
        col = curves.attributes.new("strand_colour", "FLOAT_COLOR", "POINT")
        colours = sz["colours"] * np.array(a.hair_tint)
        if a.strand_gradient:
            g = np.array(a.strand_gradient).reshape(2, 3)
            seed = np.random.default_rng(0).uniform(0.7, 1.3, len(counts))
            colours = (g[0] + (g[1] - g[0]) * (along ** 0.8)[:, None]) * np.repeat(seed, counts)[:, None]
        rgba = np.c_[colours, np.ones(len(colours))].astype(np.float32)
        col.data.foreach_set("color", rgba.ravel())
        groom = bpy.data.objects.new("groom", curves)
        bpy.context.scene.collection.objects.link(groom)
        hm = bpy.data.materials.new("strands")
        hm.use_nodes = True
        nt = hm.node_tree
        for node in list(nt.nodes):
            if node.type != "OUTPUT_MATERIAL":
                nt.nodes.remove(node)
        if a.hair_shader == "diffuse":
            # No light scattered through the hair: what lies under other hair is in its shadow.
            bsdf = nt.nodes.new("ShaderNodeBsdfDiffuse")
        else:
            bsdf = nt.nodes.new("ShaderNodeBsdfHairPrincipled")
            bsdf.parametrization = "COLOR"
            bsdf.inputs["Roughness"].default_value = a.hair_roughness
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
                d.use = d.type != "CPU"
            scene.cycles.device = "GPU"
        except Exception:
            pass
    scene.render.resolution_x = scene.render.resolution_y = a.resolution
    scene.view_settings.view_transform = "Standard"
    # The paint carries the pictures' own light; a quarter stop down matches their brightness.
    scene.view_settings.exposure = -0.25
    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.62, 0.6, 0.58, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35
    scene.world = world
    all_v = np.concatenate([sv, hv])
    centre = Vector(((all_v.min(0) + all_v.max(0)) / 2).tolist())
    height = float(all_v[:, 2].max() - all_v[:, 2].min())
    # Soft and modest: the paint already carries its own light.
    rig = (("key", (-0.6, -1.0, 0.6), 16.0, 1.2), ("fill", (0.8, -0.8, 0.1), 7.0, 1.5),
           ("rim", (0.3, 1.0, 0.5), 10.0, 0.8)) if a.light == "studio" else ()
    for name, loc, energy, size in rig:
        light = bpy.data.lights.new(name, "AREA")
        light.energy = energy
        light.size = size
        light.color = (1.0, 0.92, 0.82)
        lo = bpy.data.objects.new(name, light)
        lo.location = centre + Vector(loc)
        lo.rotation_euler = (centre - lo.location).to_track_quat("-Z", "Y").to_euler()
        scene.collection.objects.link(lo)
    if a.light == "sun":
        # A game's daylight: one hard sun high on the front-left and a dim sky, so hair under
        # other hair is in real shadow and a gap between locks reads dark, as it does in game.
        sun = bpy.data.lights.new("sun", "SUN")
        sun.energy = 3.0
        sun.angle = math.radians(1.0)
        sun.color = (1.0, 0.9, 0.78)
        so = bpy.data.objects.new("sun", sun)
        so.rotation_euler = Vector((0.5, 1.0, -1.0)).to_track_quat("-Z", "Y").to_euler()
        scene.collection.objects.link(so)
        world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.2
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.lens = 85
    scene.collection.objects.link(cam)
    scene.camera = cam
    dist = height * 85 / 36 * 1.25

    def aim(view):
        ang = math.radians(VIEWS[view])
        el = math.radians(ELEVATION.get(view, 0.0))
        d = Vector((math.sin(ang) * math.cos(el), -math.cos(ang) * math.cos(el), math.sin(el)))
        cam.location = centre + d * dist
        cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()

    for view in a.views:
        aim(view)
        scene.render.filepath = str(out / "{}-{}.png".format(a.tag, view))
        bpy.ops.render.render(write_still=True)
    if a.save_blend:
        bpy.ops.file.pack_all()
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(a.save_blend).resolve()))
    if a.id_pass:
        # Flat emission per surface, no light: a pixel's red, green and blue are the shares of
        # it covered by hair, scalp cap and skin (black: background).
        ids = {"groom": (1, 0, 0), "hair": (1, 0, 0), "scalp-cap": (0, 1, 0)}
        flat = {}
        for ob in scene.objects:
            if ob.type not in ("MESH", "CURVES"):
                continue
            colour = ids.get(ob.name, (0, 0, 1))
            if colour not in flat:
                m = bpy.data.materials.new("id-{}{}{}".format(*colour))
                m.use_nodes = True
                nt = m.node_tree
                for node in list(nt.nodes):
                    if node.type != "OUTPUT_MATERIAL":
                        nt.nodes.remove(node)
                em = nt.nodes.new("ShaderNodeEmission")
                em.inputs["Color"].default_value = (*colour, 1)
                nt.links.new(em.outputs[0], next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL").inputs[0])
                flat[colour] = m
            ob.data.materials.clear()
            ob.data.materials.append(flat[colour])
        for lo in [o for o in scene.objects if o.type == "LIGHT"]:
            bpy.data.objects.remove(lo, do_unlink=True)
        world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.0
        scene.view_settings.exposure = 0.0
        scene.cycles.use_denoising = False
        scene.cycles.samples = 16
        scene.cycles.max_bounces = 0
        for view in a.views:
            aim(view)
            scene.render.filepath = str(out / "{}-{}-id.png".format(a.tag, view))
            bpy.ops.render.render(write_still=True)
    print("rendered", a.tag, a.views, "->", out)


main()
